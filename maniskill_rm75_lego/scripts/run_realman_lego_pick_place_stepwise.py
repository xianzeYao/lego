#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import gymnasium as gym
import numpy as np
import sapien
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation, Slerp

import maniskill_rm75_lego.envs  # noqa: F401
from maniskill_rm75_lego.agents.rm75_lego_tool import RM75LegoTool
from maniskill_rm75_lego.apex_mr_reference import (
    APEX_GRAB_BRICK_OFFSET,
    APEX_PLACE_BRICK_OFFSET,
    APEX_TWIST_DEG,
    RM75_TOOL_ASSEMBLE_OFFSET_BLACK,
    RM75_TOOL_DISASSEMBLE_OFFSET_BLACK,
)
from maniskill_rm75_lego.envs.rm75_lego_pick_place import (
    PLATE_SIZE_XY,
    PLATE_TOP_POS,
    PLATE_YAW,
    baseplate_origin_from_top,
    stage2_placement_by_key,
)
from maniskill_rm75_lego.envs.rm75_lego_smoke import CONTACT_OFFSET_TCP
from maniskill_rm75_lego.lego_grid import (
    LegoGridPose,
    apex_brick_actor_pose,
    matrix_to_sapien_pose,
    pick_target_from_press_side,
    translation_matrix,
)
from maniskill_rm75_lego.scripts.run_stage4_pick_2x4 import (
    JOINT_LOWER,
    JOINT_UPPER,
    apex_pick_contact_pose,
    as_numpy,
    invert_transform,
    pose_to_matrix,
    shifted_pose,
    tcp_pose_from_contact,
    twist_about_local_pivot,
)


DEFAULT_REALMAN_BASE = REPO_ROOT / "third_party" / "lerobot-realman"
DEFAULT_REALMAN_FOUNDATIONPOSE_SCRIPT = (
    DEFAULT_REALMAN_BASE / "pick_jiaobang" / "rm75_jiaobang_pick_real_with_foundationpose.py"
)
DEFAULT_LEROBOT_ROOT = DEFAULT_REALMAN_BASE
DEFAULT_LEROBOT_SIM2REAL_ROOT = DEFAULT_REALMAN_BASE / "lerobot-sim2real"
TWIST_IK_STEPS = 1


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate the current LEGO pick-place stage6 joint waypoints and execute them "
            "step-by-step on a RealMan RM75 after pressing Enter for each stage."
        )
    )
    parser.add_argument("--brick-key", default="lego_1x4")
    parser.add_argument("--press-side", type=int, default=2)
    parser.add_argument("--press-offset", type=int, default=1)
    parser.add_argument("--initial-grid", type=int, nargs=4, default=None)
    parser.add_argument("--target-grid", type=int, nargs=4, default=[14, 15, 1, 0])
    parser.add_argument("--contact-offset", type=float, nargs=3, default=CONTACT_OFFSET_TCP)
    parser.add_argument(
        "--plate-z-offset",
        type=float,
        default=0.0,
        help="Unified real-world plate height correction in meters; positive moves the whole LEGO scene up.",
    )
    parser.add_argument("--press-depth", type=float, default=0.0)
    parser.add_argument("--place-press-depth", type=float, default=0.0)
    parser.add_argument("--pick-attack-dir", type=int, choices=[-1, 1], default=1)
    parser.add_argument("--place-attack-dir", type=int, choices=[-1, 1], default=1)
    parser.add_argument("--pick-twist-deg", type=float, default=-APEX_TWIST_DEG)
    parser.add_argument("--place-twist-deg", type=float, default=APEX_TWIST_DEG)
    parser.add_argument("--pick-up-height", type=float, default=0.035)
    parser.add_argument("--transfer-up-height", type=float, default=0.08)
    parser.add_argument("--place-up-height", type=float, default=0.035)
    parser.add_argument(
        "--cartesian-step-size",
        type=float,
        default=0.005,
        help="Maximum TCP/contact Cartesian spacing in meters for short linear primitives. Set <=0 to disable.",
    )
    parser.add_argument(
        "--include-home",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include a confirmed home waypoint before the LEGO motion.",
    )
    parser.add_argument(
        "--return-home",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include a confirmed home waypoint after the LEGO motion.",
    )
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--robot-ip", type=str, default=None)
    parser.add_argument("--lerobot-root", type=Path, default=DEFAULT_LEROBOT_ROOT)
    parser.add_argument("--lerobot-sim2real-root", type=Path, default=DEFAULT_LEROBOT_SIM2REAL_ROOT)
    parser.add_argument("--realman-foundationpose-script", type=Path, default=DEFAULT_REALMAN_FOUNDATIONPOSE_SCRIPT)
    parser.add_argument("--real-control-hz", type=float, default=10.0)
    parser.add_argument("--real-max-delta-per-step", type=float, default=0.025)
    parser.add_argument("--real-hold-steps", type=int, default=2)
    parser.add_argument("--real-gripper-pos", type=float, default=None)
    parser.add_argument("--real-gripper-command-repeats", type=int, default=2)
    parser.add_argument("--real-gripper-command-hz", type=float, default=10.0)
    parser.add_argument("--real-execution-thread", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--real-shadow-render-hz", type=float, default=None)
    parser.add_argument("--eef-log-hz", type=float, default=30.0)
    parser.add_argument("--eef-log-dir", type=Path, default=Path("outputs/realman_eef_logs"))
    parser.add_argument("--assume-aligned", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run-no-prompts", action="store_true")
    return parser.parse_args()


def load_realman_executor(script_path: Path):
    script_path = script_path.expanduser().resolve()
    module_dir = script_path.parent
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    spec = importlib.util.spec_from_file_location("rm75_foundationpose_real_exec", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load RealMan script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.RealmanJointExecutor


def matrix_to_pose(mat: np.ndarray) -> sapien.Pose:
    return matrix_to_sapien_pose(mat)


def pose_position(pose: sapien.Pose) -> np.ndarray:
    return np.asarray(pose.p, dtype=np.float64).reshape(3)


def solve_ik_regularized(pin_model, tcp_link_index: int, target_pose: sapien.Pose, q_seed: np.ndarray):
    target_mat = pose_to_matrix(target_pose)
    q_seed = np.asarray(q_seed, dtype=np.float64).reshape(-1)

    def residual(q):
        pin_model.compute_forward_kinematics(q)
        cur_mat = pose_to_matrix(pin_model.get_link_pose(tcp_link_index))
        pos_err = target_mat[:3, 3] - cur_mat[:3, 3]
        rot_err = Rotation.from_matrix(target_mat[:3, :3] @ cur_mat[:3, :3].T).as_rotvec()
        reg_err = q - q_seed
        return np.concatenate([pos_err * 80.0, rot_err * 1.4, reg_err * 0.18])

    res = least_squares(
        residual,
        np.clip(q_seed, JOINT_LOWER, JOINT_UPPER),
        bounds=(JOINT_LOWER, JOINT_UPPER),
        xtol=1e-10,
        ftol=1e-10,
        gtol=1e-10,
        max_nfev=260,
    )
    q_sol = res.x.astype(np.float64)
    pin_model.compute_forward_kinematics(q_sol)
    cur_mat = pose_to_matrix(pin_model.get_link_pose(tcp_link_index))
    pos_err = target_mat[:3, 3] - cur_mat[:3, 3]
    rot_err = Rotation.from_matrix(target_mat[:3, :3] @ cur_mat[:3, :3].T).as_rotvec()
    err = np.concatenate([pos_err, rot_err])
    success = bool(res.success and np.linalg.norm(pos_err) < 2.0e-4 and np.linalg.norm(rot_err) < 2.0e-3)
    if success:
        return q_sol, True, err
    q_pin, pin_success, pin_err = pin_model.compute_inverse_kinematics(
        tcp_link_index,
        target_pose,
        initial_qpos=q_seed,
        eps=1e-4,
        max_iterations=2000,
        dt=0.1,
        damp=1e-6,
    )
    return np.asarray(q_pin, dtype=np.float64), bool(pin_success), np.asarray(pin_err, dtype=np.float64)


def interpolate_transform_path(start_mat: np.ndarray, end_mat: np.ndarray, step_size: float) -> list[np.ndarray]:
    start_mat = np.asarray(start_mat, dtype=np.float64).reshape(4, 4)
    end_mat = np.asarray(end_mat, dtype=np.float64).reshape(4, 4)
    distance = float(np.linalg.norm(end_mat[:3, 3] - start_mat[:3, 3]))
    if step_size <= 0.0 or distance <= 1e-9:
        return [end_mat.copy()]
    num_steps = max(1, int(np.ceil(distance / step_size)))
    key_times = [0.0, 1.0]
    key_rots = Rotation.from_matrix(np.stack([start_mat[:3, :3], end_mat[:3, :3]], axis=0))
    slerp = Slerp(key_times, key_rots)
    out = []
    for alpha in np.linspace(0.0, 1.0, num_steps + 1, dtype=np.float64)[1:]:
        mat = np.eye(4, dtype=np.float64)
        mat[:3, 3] = (1.0 - alpha) * start_mat[:3, 3] + alpha * end_mat[:3, 3]
        mat[:3, :3] = slerp([float(alpha)]).as_matrix()[0]
        out.append(mat)
    return out


def build_waypoints(args):
    env = gym.make(
        "RM75LegoPickPlace-v1",
        obs_mode="none",
        reward_mode="none",
        control_mode="pd_joint_pos",
        render_mode="human" if args.render else "rgb_array",
        num_envs=1,
    )
    env.reset(seed=0)
    base_env = env.unwrapped
    plate_top_pos = np.asarray(PLATE_TOP_POS, dtype=np.float64).copy()
    plate_top_pos[2] += float(args.plate_z_offset)
    if abs(float(args.plate_z_offset)) > 0.0 and hasattr(base_env, "baseplate"):
        base_env.baseplate.set_pose(sapien.Pose(p=baseplate_origin_from_top(plate_top_pos).tolist()))

    placement = stage2_placement_by_key(args.brick_key)
    if args.initial_grid is not None:
        placement = replace(placement, grid=LegoGridPose(*args.initial_grid))
    brick_actor = base_env.bricks[placement.key]
    initial_pose = apex_brick_actor_pose(
        plate_top_pos,
        PLATE_SIZE_XY,
        placement.brick,
        placement.grid,
        PLATE_YAW,
    )
    initial_brick_mat = pose_to_matrix(initial_pose)
    brick_actor.set_pose(matrix_to_pose(initial_brick_mat))

    target_grid = LegoGridPose(*args.target_grid)
    target_pose = apex_brick_actor_pose(
        plate_top_pos,
        PLATE_SIZE_XY,
        placement.brick,
        target_grid,
        PLATE_YAW,
    )
    target_brick_mat = pose_to_matrix(target_pose)

    pick = pick_target_from_press_side(
        plate_top_pos=plate_top_pos,
        plate_size_xy=PLATE_SIZE_XY,
        brick=placement.brick,
        grid=placement.grid,
        press_side=args.press_side,
        press_offset=args.press_offset,
        plate_yaw=PLATE_YAW,
    )
    pick_contact = apex_pick_contact_pose(pick)
    contact_offset = np.asarray(args.contact_offset, dtype=np.float64)
    grab_offset = np.asarray(APEX_GRAB_BRICK_OFFSET, dtype=np.float64).copy()
    grab_offset[1] *= float(args.pick_attack_dir)

    pick_down_contact = pick_contact @ translation_matrix([0.0, 0.0, args.press_depth])
    pick_twist_contact = twist_about_local_pivot(
        pick_down_contact,
        RM75_TOOL_DISASSEMBLE_OFFSET_BLACK,
        args.pick_twist_deg,
    )
    pick_attach_contact = shifted_pose(pick_twist_contact, [0.0, 0.0, args.pick_up_height])
    pick_upright_contact = shifted_pose(pick_down_contact, [0.0, 0.0, args.pick_up_height])

    contact_t_brick = invert_transform(pick_down_contact) @ initial_brick_mat
    place_contact = target_brick_mat @ invert_transform(contact_t_brick)
    place_offset = np.asarray(APEX_PLACE_BRICK_OFFSET, dtype=np.float64).copy()
    place_offset[1] *= float(args.place_attack_dir)

    pre_place_contact = place_contact @ translation_matrix(
        [float(place_offset[0]), float(place_offset[1]), float(place_offset[2] - abs(place_offset[2]))]
    )
    transfer_contact = shifted_pose(pre_place_contact, [0.0, 0.0, args.transfer_up_height])
    drop_up_contact = place_contact @ translation_matrix([0.0, 0.0, float(place_offset[2])])
    place_press_contact = place_contact @ translation_matrix([0.0, 0.0, args.place_press_depth])
    place_twist_contact = twist_about_local_pivot(
        place_press_contact,
        RM75_TOOL_ASSEMBLE_OFFSET_BLACK,
        args.place_twist_deg,
    )
    place_up_contact = shifted_pose(place_twist_contact, [0.0, 0.0, args.place_up_height])

    contact_poses = {
        "pre_pick": pick_contact
        @ translation_matrix(
            [
                float(grab_offset[0]),
                float(grab_offset[1]),
                float(grab_offset[2] - abs(grab_offset[2])),
            ]
        ),
        "pick_down": pick_down_contact,
        "pick_twist": pick_twist_contact,
        "pick_attach": pick_attach_contact,
        "pick_upright": pick_upright_contact,
        "transfer": transfer_contact,
        "pre_place": pre_place_contact,
        "drop_up": drop_up_contact,
        "place_down": place_contact,
        "place_press": place_press_contact,
        "place_twist": place_twist_contact,
        "place_up": place_up_contact,
    }

    pin_model = base_env.agent.robot.create_pinocchio_model()
    tcp_link_index = int(as_numpy(base_env.agent.tcp.index).reshape(-1)[0])
    q_seed = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float64)

    linear_cartesian_stages = {
        "pick_down",
        "pick_attach",
        "pick_upright",
        "drop_up",
        "place_down",
        "place_press",
        "place_up",
    }
    cartesian_step_size = float(args.cartesian_step_size)

    waypoints: list[tuple[str, np.ndarray, np.ndarray]] = []
    if args.include_home:
        waypoints.append(("home_start", q_seed[None, :].astype(np.float32), np.eye(4, dtype=np.float64)))

    last_contact_pose: np.ndarray | None = None

    def append_contact_stage(name: str, contact_pose: np.ndarray) -> None:
        nonlocal q_seed, last_contact_pose
        contact_path = [np.asarray(contact_pose, dtype=np.float64)]
        if name in linear_cartesian_stages and last_contact_pose is not None:
            contact_path = interpolate_transform_path(last_contact_pose, contact_pose, cartesian_step_size)

        q_path = []
        for idx, contact_mat in enumerate(contact_path, start=1):
            pose = tcp_pose_from_contact(contact_mat, contact_offset)
            q_seed, success, err = solve_ik_regularized(pin_model, tcp_link_index, pose, q_seed)
            if not success:
                suffix = "" if len(contact_path) == 1 else f" segment {idx}/{len(contact_path)}"
                raise RuntimeError(f"IK failed for {name}{suffix}: err={np.round(err, 6).tolist()}")
            q_path.append(q_seed.astype(np.float32))
        waypoints.append((name, np.stack(q_path, axis=0), contact_pose))
        last_contact_pose = np.asarray(contact_pose, dtype=np.float64)

    for name in ["pre_pick", "pick_down"]:
        append_contact_stage(name, contact_poses[name])

    twist_steps = TWIST_IK_STEPS
    for idx, deg in enumerate(np.linspace(0.0, args.pick_twist_deg, twist_steps + 1)[1:], start=1):
        twist_pose = twist_about_local_pivot(
            pick_down_contact,
            RM75_TOOL_DISASSEMBLE_OFFSET_BLACK,
            float(deg),
        )
        pose = tcp_pose_from_contact(twist_pose, contact_offset)
        q_seed, success, err = solve_ik_regularized(pin_model, tcp_link_index, pose, q_seed)
        if not success:
            raise RuntimeError(f"IK failed for pick_twist_{idx:02d}: err={np.round(err, 6).tolist()}")
        waypoints.append((f"pick_twist_{idx:02d}", q_seed[None, :].astype(np.float32), twist_pose))
        last_contact_pose = np.asarray(twist_pose, dtype=np.float64)

    for name in [
        "pick_attach",
        "pick_upright",
        "transfer",
        "pre_place",
        "drop_up",
        "place_down",
        "place_press",
        "place_twist",
        "place_up",
    ]:
        append_contact_stage(name, contact_poses[name])

    if args.return_home:
        waypoints.append(("home_end", RM75LegoTool.keyframes["neutral"].qpos[None, :].astype(np.float32), np.eye(4, dtype=np.float64)))

    return env, waypoints


def render_shadow_step(env, q_target: np.ndarray, args) -> None:
    if not args.render:
        return
    env.step(np.asarray(q_target, dtype=np.float32))
    env.render()
    if args.render_sleep > 0 and not args.execute_real:
        time.sleep(args.render_sleep)


def make_shadow_callback(env, args):
    if not args.render:
        return None

    def _callback(q_cmd: np.ndarray) -> None:
        render_shadow_step(env, q_cmd, args)

    return _callback


def move_shadow_linear(env, q_start: np.ndarray, q_target: np.ndarray, args, label: str) -> np.ndarray:
    q_start = np.asarray(q_start, dtype=np.float32).reshape(-1)
    q_target = np.asarray(q_target, dtype=np.float32).reshape(-1)
    q_delta = (q_target - q_start + np.pi) % (2 * np.pi) - np.pi
    q_target_short = q_start + q_delta
    max_delta = float(np.max(np.abs(q_delta))) if q_delta.size > 0 else 0.0
    num_steps = max(1, int(np.ceil(max_delta / max(float(args.real_max_delta_per_step), 1e-6))))
    print(f"[shadow {label}] render_linear num_steps={num_steps}")
    for alpha in np.linspace(0.0, 1.0, num_steps + 1, dtype=np.float32)[1:]:
        render_shadow_step(env, (1.0 - alpha) * q_start + alpha * q_target_short, args)
    return q_target_short.astype(np.float32)


def joint_limit_report(q: np.ndarray, margin_warn: float = 0.05) -> str:
    q = np.asarray(q, dtype=np.float64).reshape(-1)
    lower = JOINT_LOWER[: q.size]
    upper = JOINT_UPPER[: q.size]
    below = q - lower
    above = upper - q
    problems = []
    for idx, (lo_margin, hi_margin, value, lo, hi) in enumerate(zip(below, above, q, lower, upper), start=1):
        if lo_margin < 0.0:
            problems.append(f"J{idx} below by {-lo_margin:.3f} rad (q={value:.3f}, lower={lo:.3f})")
        elif hi_margin < 0.0:
            problems.append(f"J{idx} above by {-hi_margin:.3f} rad (q={value:.3f}, upper={hi:.3f})")
        elif min(lo_margin, hi_margin) < margin_warn:
            side = "lower" if lo_margin < hi_margin else "upper"
            problems.append(f"J{idx} near {side}, margin={min(lo_margin, hi_margin):.3f} rad (q={value:.3f})")
    if problems:
        return " | ".join(problems)
    return ""


class RealmanEefLogger:
    def __init__(self, real_exec, args):
        self.real_exec = real_exec
        self.hz = float(max(args.eef_log_hz, 0.0))
        self.out_dir = Path(args.eef_log_dir)
        self.rows: list[dict] = []
        self.stage = "idle"
        self.target_contact = np.full(3, np.nan, dtype=np.float64)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = 0.0

    def set_stage(self, stage: str, contact_pose: np.ndarray | None = None) -> None:
        target = np.full(3, np.nan, dtype=np.float64)
        if contact_pose is not None and not np.allclose(contact_pose, np.eye(4), atol=1e-9):
            target = np.asarray(contact_pose[:3, 3], dtype=np.float64)
        with self._lock:
            self.stage = stage
            self.target_contact = target

    def start(self) -> None:
        if self.hz <= 0.0:
            return
        self._t0 = time.perf_counter()
        self._thread = threading.Thread(target=self._loop, name="realman-eef-logger", daemon=True)
        self._thread.start()
        print(f"[eef-log] recording controller EEF state at {self.hz:.1f} Hz")

    def stop_and_save(self) -> Path | None:
        if self._thread is None:
            return None
        self._stop.set()
        self._thread.join(timeout=2.0)
        return self._save()

    def _loop(self) -> None:
        period = 1.0 / max(self.hz, 1e-3)
        next_t = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            if now < next_t:
                time.sleep(min(next_t - now, 0.01))
                continue
            self._sample(now)
            next_t += period

    def _sample(self, now: float) -> None:
        with self._lock:
            stage = self.stage
            target = self.target_contact.copy()
        row = {
            "t": now - self._t0,
            "wall_time": time.time(),
            "stage": stage,
            "target_contact_x": float(target[0]),
            "target_contact_y": float(target[1]),
            "target_contact_z": float(target[2]),
        }
        try:
            arm = getattr(self.real_exec.real_robot, "arm", None)
            if arm is None:
                row["ok"] = 0
                row["error"] = "missing_real_robot_arm"
            else:
                with self.real_exec._io_lock:
                    ret, state = arm.rm_get_current_arm_state()
                row["ok"] = int(ret == 0 and state is not None)
                row["ret"] = int(ret)
                if ret == 0 and state is not None:
                    pose = np.asarray(state.get("pose", [np.nan] * 6), dtype=np.float64).reshape(-1)
                    joint = np.asarray(state.get("joint", []), dtype=np.float64).reshape(-1)
                    for idx, name in enumerate(["x", "y", "z", "rx", "ry", "rz"]):
                        row[f"eef_{name}"] = float(pose[idx]) if idx < pose.size else float("nan")
                    for idx in range(7):
                        row[f"joint{idx + 1}_deg"] = float(joint[idx]) if idx < joint.size else float("nan")
                else:
                    row["error"] = "rm_get_current_arm_state_failed"
        except Exception as exc:
            row["ok"] = 0
            row["error"] = repr(exc)
        self.rows.append(row)

    def _save(self) -> Path | None:
        if not self.rows:
            print("[eef-log] no samples captured")
            return None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = self.out_dir / f"realman_eef_{stamp}.csv"
        json_path = self.out_dir / f"realman_eef_{stamp}_summary.json"
        fields = [
            "t", "wall_time", "stage", "ok", "ret", "error",
            "eef_x", "eef_y", "eef_z", "eef_rx", "eef_ry", "eef_rz",
            "target_contact_x", "target_contact_y", "target_contact_z",
        ] + [f"joint{i}_deg" for i in range(1, 8)]
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.rows)
        summary = self._summary(csv_path)
        with json_path.open("w") as f:
            json.dump(summary, f, indent=2)
        print(f"[eef-log] saved {len(self.rows)} samples to {csv_path}")
        print(f"[eef-log] summary: {json_path}")
        return csv_path

    def _summary(self, csv_path: Path) -> dict:
        summary = {"csv_path": str(csv_path), "num_samples": len(self.rows), "stages": {}}
        stage_names = sorted({str(row.get("stage", "")) for row in self.rows})
        for stage in stage_names:
            samples = [
                row for row in self.rows
                if row.get("stage") == stage and int(row.get("ok", 0)) == 1
            ]
            if not samples:
                continue
            xyz = np.array(
                [[row.get("eef_x", np.nan), row.get("eef_y", np.nan), row.get("eef_z", np.nan)] for row in samples],
                dtype=np.float64,
            )
            xyz = xyz[np.all(np.isfinite(xyz), axis=1)]
            if xyz.size == 0:
                continue
            start = xyz[0]
            end = xyz[-1]
            span = np.nanmax(xyz, axis=0) - np.nanmin(xyz, axis=0)
            xy_from_line = _xy_deviation_from_line(xyz)
            summary["stages"][stage] = {
                "num_samples": int(len(xyz)),
                "start_xyz": np.round(start, 6).tolist(),
                "end_xyz": np.round(end, 6).tolist(),
                "delta_xyz": np.round(end - start, 6).tolist(),
                "span_xyz": np.round(span, 6).tolist(),
                "span_xy_mm": np.round(span[:2] * 1000.0, 3).tolist(),
                "max_xy_deviation_from_line_mm": round(float(xy_from_line) * 1000.0, 3),
            }
        return summary


def _xy_deviation_from_line(xyz: np.ndarray) -> float:
    if len(xyz) < 3:
        return 0.0
    xy = np.asarray(xyz[:, :2], dtype=np.float64)
    a = xy[0]
    b = xy[-1]
    ab = b - a
    denom = float(np.dot(ab, ab))
    if denom < 1e-12:
        return float(np.max(np.linalg.norm(xy - a, axis=1)))
    t = np.clip(((xy - a) @ ab) / denom, 0.0, 1.0)
    proj = a + t[:, None] * ab
    return float(np.max(np.linalg.norm(xy - proj, axis=1)))


def stage_final_q(q_path: np.ndarray) -> np.ndarray:
    q_path = np.asarray(q_path, dtype=np.float32)
    if q_path.ndim == 1:
        return q_path
    return q_path[-1]


def confirm(label: str, q_path: np.ndarray, args) -> str:
    q_path = np.asarray(q_path, dtype=np.float32)
    q_target = stage_final_q(q_path)
    print(f"\n[next] {label}")
    if q_path.ndim == 2 and q_path.shape[0] > 1:
        print("subwaypoints:", int(q_path.shape[0]))
    print("final q(rad):", np.round(np.asarray(q_target, dtype=np.float64), 5).tolist())
    if args.dry_run_no_prompts:
        return "run"
    text = input("Press Enter to execute this stage, 's' to skip, or 'q' to abort: ").strip().lower()
    if text == "q":
        return "abort"
    if text == "s":
        return "skip"
    return "run"


def main() -> int:
    args = parse_args()
    if args.render and args.execute_real:
        if args.real_shadow_render_hz is None:
            args.real_shadow_render_hz = float(args.real_control_hz)
        if bool(args.real_execution_thread):
            print("[render] forcing --no-real-execution-thread so real sends and shadow rendering stay synchronized")
            args.real_execution_thread = False
    if args.real_shadow_render_hz is None:
        args.real_shadow_render_hz = 0.0

    env, waypoints = build_waypoints(args)
    print(f"[plan] generated {len(waypoints)} LEGO waypoints")
    for idx, (label, q_path, contact_pose) in enumerate(waypoints, start=1):
        q_final = stage_final_q(q_path)
        substeps = int(np.asarray(q_path).shape[0]) if np.asarray(q_path).ndim == 2 else 1
        pos = np.round(contact_pose[:3, 3], 6).tolist()
        print(
            f"[plan] {idx:02d} {label:16s} substeps={substeps:02d} "
            f"contact_p={pos} q_final={np.round(q_final, 5).tolist()}"
        )
        limit_warning = joint_limit_report(q_final)
        if limit_warning:
            print(f"[limit] {label}: {limit_warning}")

    real_exec = None
    eef_logger = None
    if args.execute_real:
        if not bool(args.assume_aligned):
            print("[warning] --no-assume-aligned was set; still executing raw generated waypoints step-by-step.")
        RealmanJointExecutor = load_realman_executor(args.realman_foundationpose_script)
        real_exec = RealmanJointExecutor(args)
        eef_logger = RealmanEefLogger(real_exec, args)
        eef_logger.start()
    else:
        print("[dry-run] --execute-real not set; no hardware commands will be sent.")

    shadow_q = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float32)
    try:
        if args.render:
            render_shadow_step(env, shadow_q, args)
        for label, q_path, _contact_pose in waypoints:
            q_path = np.asarray(q_path, dtype=np.float32)
            if q_path.ndim == 1:
                q_path = q_path[None, :]
            decision = confirm(label, q_path, args)
            if decision == "abort":
                print("[abort] user aborted before stage", label)
                return 1
            if decision == "skip":
                print("[skip]", label)
                continue
            if eef_logger is not None:
                eef_logger.set_stage(label, _contact_pose)
            if real_exec is None:
                for sub_idx, q_target in enumerate(q_path, start=1):
                    sub_label = label if len(q_path) == 1 else f"{label}_{sub_idx:02d}"
                    if args.render:
                        shadow_q = move_shadow_linear(env, shadow_q, q_target, args, sub_label)
                    else:
                        shadow_q = np.asarray(q_target, dtype=np.float32)
                continue
            t0 = time.perf_counter()
            for sub_idx, q_target in enumerate(q_path, start=1):
                sub_label = label if len(q_path) == 1 else f"{label}_{sub_idx:02d}"
                hold_steps = args.real_hold_steps if sub_idx == len(q_path) else 0
                real_exec.move_linear(
                    q_target,
                    gripper_pos=args.real_gripper_pos,
                    max_delta_per_step=args.real_max_delta_per_step,
                    hz=args.real_control_hz,
                    hold_steps=hold_steps,
                    label=sub_label,
                    shadow_callback=make_shadow_callback(env, args),
                )
                shadow_q = np.asarray(q_target, dtype=np.float32)
            print(f"[real] {label} done in {time.perf_counter() - t0:.2f}s")
    finally:
        if eef_logger is not None:
            try:
                eef_logger.set_stage("finished", None)
                eef_logger.stop_and_save()
            except Exception as exc:
                print(f"[eef-log] failed to save EEF log: {exc!r}")
        if real_exec is not None:
            try:
                real_exec.close()
            except Exception:
                pass
        env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
