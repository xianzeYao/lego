#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import select
import sys
import time
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
    build_colored_mesh_actor,
    grid_origin_axis_pose,
)
from maniskill_rm75_lego.envs.rm75_lego_smoke import CONTACT_OFFSET_TCP
from maniskill_rm75_lego.lego_grid import (
    BRICK_BODY_HEIGHT,
    LEGO_BRICK_SPECS,
    LegoGridPose,
    STUD_HEIGHT,
    STUD_PITCH,
    apex_brick_actor_pose,
    matrix_to_sapien_pose,
    pick_target_from_press_side,
    translation_matrix,
)
from maniskill_rm75_lego.lego_task_parser import LegoTaskDefinition, load_task_json
from maniskill_rm75_lego.realman_step_runner import load_realman_executor, run_q_path_stage
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


BRICK_BY_NAME = {spec.name: spec for spec in LEGO_BRICK_SPECS}
TWIST_IK_STEPS = 1
DEFAULT_REALMAN_BASE = REPO_ROOT / "third_party" / "lerobot-realman"
DEFAULT_REALMAN_FOUNDATIONPOSE_SCRIPT = (
    DEFAULT_REALMAN_BASE / "pick_jiaobang" / "rm75_jiaobang_pick_real_with_foundationpose.py"
)
DEFAULT_LEROBOT_ROOT = DEFAULT_REALMAN_BASE
DEFAULT_LEROBOT_SIM2REAL_ROOT = DEFAULT_REALMAN_BASE / "lerobot-sim2real"
PERIODIC_JOINT_INDICES = (6,)
IK_JOINT_LOWER = JOINT_LOWER.copy()
IK_JOINT_UPPER = JOINT_UPPER.copy()
IK_JOINT_LOWER[6] = -np.pi
IK_JOINT_UPPER[6] = np.pi


def _nearest_periodic_angle(angle: float, reference: float, lower: float, upper: float) -> float:
    period = 2.0 * np.pi
    base = reference + ((float(angle) - float(reference) + np.pi) % period - np.pi)
    candidates = [base + period * k for k in range(-2, 3)]
    valid = [value for value in candidates if lower <= value <= upper]
    if valid:
        return min(valid, key=lambda value: abs(value - reference))
    return float(np.clip(base, lower, upper))


def _normalize_periodic_joints(q: np.ndarray, reference: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64).copy()
    reference = np.asarray(reference, dtype=np.float64).reshape(-1)
    for joint_idx in PERIODIC_JOINT_INDICES:
        q[joint_idx] = _nearest_periodic_angle(
            q[joint_idx],
            reference[joint_idx],
            IK_JOINT_LOWER[joint_idx],
            IK_JOINT_UPPER[joint_idx],
        )
    return q


def parse_args():
    parser = argparse.ArgumentParser(description="Render RM75 LEGO robot motion from config/settings.json + task.json.")
    parser.add_argument("--task-config", default="config/ladder")
    parser.add_argument("--plate-z-offset", type=float, default=0.0)
    parser.add_argument("--contact-offset", type=float, nargs=3, default=CONTACT_OFFSET_TCP)
    parser.add_argument("--pick-press-depth", "--press-depth", dest="pick_press_depth", type=float, default=0.0)
    parser.add_argument("--place-press-depth", type=float, default=0.0)
    parser.add_argument("--pick-twist-deg", type=float, default=-APEX_TWIST_DEG)
    parser.add_argument("--place-twist-deg", type=float, default=APEX_TWIST_DEG)
    parser.add_argument("--pick-up-height", type=float, default=0.035)
    parser.add_argument("--transfer-up-height", type=float, default=0.08)
    parser.add_argument("--place-up-height", type=float, default=0.035)
    parser.add_argument("--steps-per-segment", type=int, default=80)
    parser.add_argument("--cartesian-step-size", type=float, default=0.005)
    parser.add_argument("--cartesian-rot-step-deg", type=float, default=2.0)
    parser.add_argument("--hold-steps", type=int, default=30)
    parser.add_argument("--audit-dense-path", action="store_true")
    parser.add_argument("--audit-collisions", action="store_true")
    parser.add_argument("--collision-log", default=None)
    parser.add_argument("--collision-overlap-tol", type=float, default=5.0e-4)
    parser.add_argument("--collision-z-overlap-tol", type=float, default=STUD_HEIGHT * 1.35)
    parser.add_argument(
        "--audit-tool-collisions",
        action="store_true",
        help="Audit a conservative tool clearance box against non-attached LEGO bricks.",
    )
    parser.add_argument(
        "--tool-collision-scope",
        choices=["placed", "all"],
        default="placed",
        help="Which bricks the tool clearance box is checked against.",
    )
    parser.add_argument(
        "--tool-audit-box",
        type=float,
        nargs=6,
        default=[0.0, 0.0, 0.0, 0.105, 0.030, 0.018],
        metavar=("CX", "CY", "CZ", "SX", "SY", "SZ"),
        help="Tool audit box in contact-frame meters: center xyz then full size xyz.",
    )
    parser.add_argument("--render", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--wait-at-end", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--auto-continue-pauses", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--robot-ip", type=str, default=None)
    parser.add_argument("--real-control-hz", type=float, default=20.0)
    parser.add_argument("--real-max-delta-per-step", type=float, default=0.025)
    parser.add_argument("--real-hold-steps", type=int, default=2)
    parser.add_argument("--step", action="store_true", help="Pause before each motion stage; Enter runs, s skips, q aborts.")
    parser.set_defaults(
        lerobot_root=DEFAULT_LEROBOT_ROOT,
        lerobot_sim2real_root=DEFAULT_LEROBOT_SIM2REAL_ROOT,
        realman_foundationpose_script=DEFAULT_REALMAN_FOUNDATIONPOSE_SCRIPT,
        real_execution_thread=False,
        real_shadow_render_hz=None,
        real_gripper_command_repeats=2,
        real_gripper_command_hz=10.0,
    )
    return parser.parse_args()


def _hide_default_scene_bricks(base_env) -> None:
    for actor in getattr(base_env, "bricks", {}).values():
        actor.set_pose(sapien.Pose(p=[0.0, 0.0, -1.0]))
    goal = getattr(base_env, "goal_marker", None)
    if goal is not None:
        goal.set_pose(sapien.Pose(p=[0.0, 0.0, -1.0]))


def _plate_top_pos(plate_z_offset: float) -> np.ndarray:
    plate_top = np.asarray(PLATE_TOP_POS, dtype=np.float64).copy()
    plate_top[2] += float(plate_z_offset)
    return plate_top


def _brick_pose_from_grid(plate_top: np.ndarray, brick_type: str, grid_values: list[int]) -> sapien.Pose:
    return apex_brick_actor_pose(
        plate_top,
        PLATE_SIZE_XY,
        BRICK_BY_NAME[brick_type],
        LegoGridPose(*grid_values),
        PLATE_YAW,
    )


def _pose_to_matrix_any(pose) -> np.ndarray:
    raw = pose.to_transformation_matrix()
    raw = as_numpy(raw)
    if raw.ndim == 3:
        raw = raw[0]
    mat = np.eye(4, dtype=np.float64)
    mat[:3, :3] = raw[:3, :3]
    mat[:3, 3] = raw[:3, 3]
    return mat


def _solve_ik(pin_model, tcp_link_index: int, target_pose: sapien.Pose, q_seed: np.ndarray):
    target_mat = pose_to_matrix(target_pose)
    q_seed = np.asarray(q_seed, dtype=np.float64).reshape(-1)

    def residual(q):
        pin_model.compute_forward_kinematics(q)
        cur_mat = pose_to_matrix(pin_model.get_link_pose(tcp_link_index))
        pos_err = target_mat[:3, 3] - cur_mat[:3, 3]
        rot_err = Rotation.from_matrix(target_mat[:3, :3] @ cur_mat[:3, :3].T).as_rotvec()
        reg_err = q - q_seed
        return np.concatenate([pos_err * 80.0, rot_err * 1.4, reg_err * 0.18])

    result = least_squares(
        residual,
        np.clip(q_seed, IK_JOINT_LOWER, IK_JOINT_UPPER),
        bounds=(IK_JOINT_LOWER, IK_JOINT_UPPER),
        max_nfev=260,
        xtol=1e-10,
        ftol=1e-10,
        gtol=1e-10,
    )
    q_sol = _normalize_periodic_joints(np.asarray(result.x, dtype=np.float64), q_seed)
    pin_model.compute_forward_kinematics(q_sol)
    cur_mat = pose_to_matrix(pin_model.get_link_pose(tcp_link_index))
    pos_err = target_mat[:3, 3] - cur_mat[:3, 3]
    rot_err = Rotation.from_matrix(target_mat[:3, :3] @ cur_mat[:3, :3].T).as_rotvec()
    success = bool(result.success and np.linalg.norm(pos_err) < 2.0e-4 and np.linalg.norm(rot_err) < 2.0e-3)
    if success:
        return q_sol, True, np.concatenate([pos_err, rot_err])
    q_pin, pin_success, pin_err = pin_model.compute_inverse_kinematics(
        tcp_link_index,
        target_pose,
        initial_qpos=q_seed,
        eps=1e-4,
        max_iterations=2000,
        dt=0.1,
        damp=1e-6,
    )
    q_pin = _normalize_periodic_joints(np.asarray(q_pin, dtype=np.float64), q_seed)
    return q_pin, bool(pin_success), np.asarray(pin_err, dtype=np.float64)


def interpolate_transform_path(
    start_mat: np.ndarray,
    end_mat: np.ndarray,
    step_size: float,
    rot_step_deg: float,
) -> list[np.ndarray]:
    start_mat = np.asarray(start_mat, dtype=np.float64).reshape(4, 4)
    end_mat = np.asarray(end_mat, dtype=np.float64).reshape(4, 4)
    distance = float(np.linalg.norm(end_mat[:3, 3] - start_mat[:3, 3]))
    rot_delta = Rotation.from_matrix(end_mat[:3, :3] @ start_mat[:3, :3].T)
    angle = float(np.linalg.norm(rot_delta.as_rotvec()))
    if step_size <= 0.0 and rot_step_deg <= 0.0:
        return [end_mat.copy()]
    trans_steps = 0 if step_size <= 0.0 else int(np.ceil(distance / step_size))
    rot_step_rad = np.deg2rad(rot_step_deg) if rot_step_deg > 0.0 else 0.0
    rot_steps = 0 if rot_step_rad <= 0.0 else int(np.ceil(angle / rot_step_rad))
    num_steps = max(1, trans_steps, rot_steps)
    key_rots = Rotation.from_matrix(np.stack([start_mat[:3, :3], end_mat[:3, :3]], axis=0))
    slerp = Slerp([0.0, 1.0], key_rots)
    out = []
    for alpha in np.linspace(0.0, 1.0, num_steps + 1, dtype=np.float64)[1:]:
        mat = np.eye(4, dtype=np.float64)
        mat[:3, 3] = (1.0 - alpha) * start_mat[:3, 3] + alpha * end_mat[:3, 3]
        mat[:3, :3] = slerp([float(alpha)]).as_matrix()[0]
        out.append(mat)
    return out


def _pose_path_stats(mats: list[np.ndarray] | np.ndarray) -> tuple[float, float, float]:
    mats = np.asarray(mats, dtype=np.float64)
    if mats.ndim == 2:
        mats = mats[None, :, :]
    positions = mats[:, :3, 3]
    xy_span_m = float(np.max(np.linalg.norm(positions[:, :2] - positions[0, :2], axis=1))) if len(positions) else 0.0
    z_span_m = float(np.max(positions[:, 2]) - np.min(positions[:, 2])) if len(positions) else 0.0
    if len(mats) <= 1:
        return xy_span_m, z_span_m, 0.0
    r0 = mats[0, :3, :3]
    rot_span_rad = max(
        float(np.linalg.norm(Rotation.from_matrix(mat[:3, :3] @ r0.T).as_rotvec()))
        for mat in mats
    )
    return xy_span_m, z_span_m, rot_span_rad


def _brick_aabb_from_mat(brick, mat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mat = np.asarray(mat, dtype=np.float64).reshape(4, 4)
    hx = brick.studs_x * STUD_PITCH / 2.0
    hy = brick.studs_y * STUD_PITCH / 2.0
    corners = np.array(
        [
            [sx * hx, sy * hy, z, 1.0]
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
            for z in (-BRICK_BODY_HEIGHT, STUD_HEIGHT)
        ],
        dtype=np.float64,
    )
    world = (mat @ corners.T).T[:, :3]
    return world.min(axis=0), world.max(axis=0)


def _box_aabb_from_mat(box_mat: np.ndarray, size_xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    box_mat = np.asarray(box_mat, dtype=np.float64).reshape(4, 4)
    half = np.asarray(size_xyz, dtype=np.float64).reshape(3) / 2.0
    corners = np.array(
        [
            [sx * half[0], sy * half[1], sz * half[2], 1.0]
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
            for sz in (-1.0, 1.0)
        ],
        dtype=np.float64,
    )
    world = (box_mat @ corners.T).T[:, :3]
    return world.min(axis=0), world.max(axis=0)


class BrickCollisionAuditor:
    def __init__(
        self,
        brick_cfgs_by_id: dict,
        current_mats: dict,
        overlap_tol: float,
        z_overlap_tol: float,
    ):
        self.brick_cfgs_by_id = brick_cfgs_by_id
        self.current_mats = current_mats
        self.overlap_tol = float(overlap_tol)
        self.z_overlap_tol = float(z_overlap_tol)
        self.records: list[dict] = []
        self.summary: dict[tuple[str, str], dict] = {}

    def _record(self, stage: str, row: dict) -> None:
        record = {"stage": stage, **row}
        self.records.append(record)
        key = tuple(sorted((row["a"], row["b"])))
        entry = self.summary.setdefault(
            key,
            {
                "a": key[0],
                "b": key[1],
                "count": 0,
                "max_volume_m3": 0.0,
                "max_overlap_m": [0.0, 0.0, 0.0],
                "stages": {},
            },
        )
        entry["count"] += 1
        entry["max_volume_m3"] = max(entry["max_volume_m3"], row["volume_m3"])
        entry["max_overlap_m"] = np.maximum(entry["max_overlap_m"], row["overlap_m"]).tolist()
        entry["stages"][stage] = entry["stages"].get(stage, 0) + 1

    def _brick_overlaps(self) -> list[dict]:
        ids = sorted(self.brick_cfgs_by_id)
        aabbs = {}
        for brick_id in ids:
            cfg = self.brick_cfgs_by_id[brick_id]
            aabbs[brick_id] = _brick_aabb_from_mat(BRICK_BY_NAME[cfg.type], self.current_mats[brick_id])
        rows = []
        for i, a_id in enumerate(ids):
            a_min, a_max = aabbs[a_id]
            for b_id in ids[i + 1:]:
                b_min, b_max = aabbs[b_id]
                overlap = np.minimum(a_max, b_max) - np.maximum(a_min, b_min)
                if np.all(overlap > self.overlap_tol) and overlap[2] > self.z_overlap_tol:
                    rows.append(
                        {
                            "a": a_id,
                            "b": b_id,
                            "overlap_m": np.round(overlap, 7).tolist(),
                            "volume_m3": float(np.prod(overlap)),
                        }
                    )
        return rows

    def sample(self, stage: str) -> None:
        for row in self._brick_overlaps():
            self._record(stage, row)

    def sample_tool(
        self,
        stage: str,
        tool_box_mat: np.ndarray,
        tool_box_size: np.ndarray,
        ignore_ids: set[str] | None = None,
        include_ids: set[str] | None = None,
    ) -> None:
        ignore_ids = set(ignore_ids or ())
        include_ids = set(include_ids) if include_ids is not None else None
        tool_min, tool_max = _box_aabb_from_mat(tool_box_mat, tool_box_size)
        for brick_id, cfg in self.brick_cfgs_by_id.items():
            if include_ids is not None and brick_id not in include_ids:
                continue
            if brick_id in ignore_ids:
                continue
            brick_min, brick_max = _brick_aabb_from_mat(BRICK_BY_NAME[cfg.type], self.current_mats[brick_id])
            overlap = np.minimum(tool_max, brick_max) - np.maximum(tool_min, brick_min)
            if np.all(overlap > self.overlap_tol):
                self._record(
                    stage,
                    {
                        "a": "tool",
                        "b": brick_id,
                        "overlap_m": np.round(overlap, 7).tolist(),
                        "volume_m3": float(np.prod(overlap)),
                    },
                )

    def print_summary(self, limit: int = 20) -> None:
        rows = sorted(
            self.summary.values(),
            key=lambda row: (row["count"], row["max_volume_m3"]),
            reverse=True,
        )
        print(f"[collision audit] overlap_records={len(self.records)} unique_pairs={len(rows)}")
        for row in rows[:limit]:
            top_stages = sorted(row["stages"].items(), key=lambda item: item[1], reverse=True)[:4]
            print(
                "[collision audit] "
                f"{row['a']} <-> {row['b']} count={row['count']} "
                f"max_overlap_m={np.round(row['max_overlap_m'], 6).tolist()} "
                f"top_stages={top_stages}"
            )

    def write_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted(
            self.summary.values(),
            key=lambda row: (row["count"], row["max_volume_m3"]),
            reverse=True,
        )
        with path.open("w") as f:
            json.dump({"summary": rows, "records": self.records}, f, indent=2)
            f.write("\n")


def main() -> int:
    args = parse_args()
    if args.render and args.execute_real and args.real_shadow_render_hz is None:
        args.real_shadow_render_hz = float(args.real_control_hz)
    if args.real_shadow_render_hz is None:
        args.real_shadow_render_hz = 0.0
    task = load_task_json(args.task_config)
    plate_top = _plate_top_pos(args.plate_z_offset)
    env = gym.make(
        "RM75LegoPickPlace-v1",
        obs_mode="none",
        reward_mode="none",
        control_mode="pd_joint_pos",
        render_mode="human" if args.render else "rgb_array",
        num_envs=1,
    )
    env.reset(seed=args.seed)
    base_env = env.unwrapped
    if hasattr(base_env, "baseplate"):
        base_env.baseplate.set_pose(sapien.Pose(p=baseplate_origin_from_top(plate_top).tolist()))
    if all(hasattr(base_env, name) for name in ("grid_origin_axis_x", "grid_origin_axis_y", "grid_origin_axis_z")):
        origin_axis_pose = grid_origin_axis_pose(plate_top)
        base_env.grid_origin_axis_x.set_pose(origin_axis_pose)
        base_env.grid_origin_axis_y.set_pose(origin_axis_pose)
        base_env.grid_origin_axis_z.set_pose(origin_axis_pose)
        print("[grid origin axes] RGB at plate grid (0, 0):", np.round(origin_axis_pose.p, 6).tolist())
    _hide_default_scene_bricks(base_env)

    actors_by_id = {}
    brick_cfgs_by_id = {}
    current_mats = {}
    for brick_cfg in task.bricks:
        pose = _brick_pose_from_grid(plate_top, brick_cfg.type, brick_cfg.grid)
        actor = build_colored_mesh_actor(
            base_env.scene,
            name=f"task_lego_robot_{brick_cfg.id}",
            mesh_path=BRICK_BY_NAME[brick_cfg.type].mesh_path,
            color=brick_cfg.color,
            pose=pose,
            body_type="kinematic",
        )
        actors_by_id[brick_cfg.id] = actor
        brick_cfgs_by_id[brick_cfg.id] = brick_cfg
        current_mats[brick_cfg.id] = pose_to_matrix(pose)
        print(f"{brick_cfg.id}: {brick_cfg.type} grid={brick_cfg.grid}")

    contact_offset = np.asarray(args.contact_offset, dtype=np.float64)
    grab_offset = np.asarray(APEX_GRAB_BRICK_OFFSET, dtype=np.float64).copy()
    place_offset = np.asarray(APEX_PLACE_BRICK_OFFSET, dtype=np.float64).copy()
    pin_model = base_env.agent.robot.create_pinocchio_model()
    tcp_link_index = int(as_numpy(base_env.agent.tcp.index).reshape(-1)[0])
    q_seed = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float64)
    real_exec = None
    if args.execute_real:
        RealmanJointExecutor = load_realman_executor(args.realman_foundationpose_script)
        real_exec = RealmanJointExecutor(args)
    else:
        print("[dry-run] --execute-real not set; no hardware commands will be sent.")

    attached_ids: list[str] = []
    contact_t_object: dict[str, np.ndarray] = {}
    released = True
    active_stage = "init"
    placed_ids: set[str] = set()
    tool_audit_box = np.asarray(args.tool_audit_box, dtype=np.float64)
    tool_audit_box_center = tool_audit_box[:3]
    tool_audit_box_size = tool_audit_box[3:]
    collision_auditor = (
        BrickCollisionAuditor(
            brick_cfgs_by_id,
            current_mats,
            args.collision_overlap_tol,
            args.collision_z_overlap_tol,
        )
        if args.audit_collisions
        else None
    )
    if collision_auditor is not None:
        collision_auditor.sample("initial")

    def current_contact_mat() -> np.ndarray:
        return _pose_to_matrix_any(base_env.agent.tcp.pose) @ translation_matrix(contact_offset)

    def update_attached() -> None:
        if released:
            return
        contact_mat = current_contact_mat()
        for brick_id in attached_ids:
            mat = contact_mat @ contact_t_object[brick_id]
            current_mats[brick_id] = mat
            actors_by_id[brick_id].set_pose(matrix_to_sapien_pose(mat))

    def render_step() -> None:
        update_attached()
        if collision_auditor is not None:
            collision_auditor.sample(active_stage)
            if args.audit_tool_collisions:
                tool_box_mat = current_contact_mat() @ translation_matrix(tool_audit_box_center)
                include_ids = placed_ids if args.tool_collision_scope == "placed" else None
                collision_auditor.sample_tool(
                    active_stage,
                    tool_box_mat,
                    tool_audit_box_size,
                    ignore_ids=set(attached_ids),
                    include_ids=include_ids,
                )
        base_env.update_markers()
        if args.render:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)

    def hold(tag: str) -> None:
        print(f"[hold] {tag}")
        q = as_numpy(base_env.agent.robot.get_qpos()).reshape(-1).astype(np.float32)
        for _ in range(max(0, int(args.hold_steps))):
            env.step(q)
            render_step()

    runner_kwargs = {
        "args": args,
        "env": env,
        "render_step": render_step,
        "get_qpos": lambda: as_numpy(base_env.agent.robot.get_qpos()).reshape(-1),
        "real_exec": real_exec,
    }

    def run_stage(label: str, q_path: np.ndarray, steps: int | None = None) -> bool:
        nonlocal active_stage
        active_stage = label
        return run_q_path_stage(
            label=label,
            q_path=q_path,
            steps=steps,
            **runner_kwargs,
        )

    last_contact_pose: np.ndarray | None = None

    def audit_contact_path(tag: str, target_contact_path: list[np.ndarray], q_path: np.ndarray) -> None:
        if not args.audit_dense_path:
            return
        target_contact_path = [np.asarray(mat, dtype=np.float64).reshape(4, 4) for mat in target_contact_path]
        q_path = np.asarray(q_path, dtype=np.float64)
        fk_contact_path = []
        pos_errs = []
        rot_errs = []
        for target_contact, q in zip(target_contact_path, q_path):
            pin_model.compute_forward_kinematics(q)
            tcp_mat = pose_to_matrix(pin_model.get_link_pose(tcp_link_index))
            fk_contact = tcp_mat @ translation_matrix(contact_offset)
            fk_contact_path.append(fk_contact)
            pos_errs.append(float(np.linalg.norm(target_contact[:3, 3] - fk_contact[:3, 3])))
            rot_errs.append(float(np.linalg.norm(
                Rotation.from_matrix(target_contact[:3, :3] @ fk_contact[:3, :3].T).as_rotvec()
            )))
        target_xy, target_z, target_rot = _pose_path_stats(target_contact_path)
        fk_xy, fk_z, fk_rot = _pose_path_stats(fk_contact_path)
        if len(q_path) > 1:
            dq = np.diff(q_path, axis=0)
            max_joint_step = float(np.max(np.abs(dq)))
            max_joint_accel = float(np.max(np.abs(np.diff(dq, axis=0)))) if len(q_path) > 2 else 0.0
        else:
            max_joint_step = 0.0
            max_joint_accel = 0.0
        max_pos_err = max(pos_errs, default=0.0)
        max_rot_err = max(rot_errs, default=0.0)
        print(
            f"[audit {tag}] n={len(q_path)} "
            f"target_xy={target_xy * 1000:.3f}mm target_z={target_z * 1000:.3f}mm "
            f"target_rot={np.rad2deg(target_rot):.4f}deg"
        )
        print(
            f"[audit {tag}] fk_xy={fk_xy * 1000:.3f}mm fk_z={fk_z * 1000:.3f}mm "
            f"fk_rot={np.rad2deg(fk_rot):.4f}deg "
            f"max_pos_err={max_pos_err * 1000:.3f}mm max_rot_err={np.rad2deg(max_rot_err):.4f}deg"
        )
        print(
            f"[audit {tag}] max_joint_step={max_joint_step:.6f}rad "
            f"max_joint_accel={max_joint_accel:.6f}rad"
        )

    def solve_contact_path(contact_pose: np.ndarray, tag: str) -> np.ndarray:
        nonlocal q_seed
        nonlocal last_contact_pose
        contact_pose = np.asarray(contact_pose, dtype=np.float64).reshape(4, 4)
        contact_path = [contact_pose]
        if last_contact_pose is not None:
            contact_path = interpolate_transform_path(
                last_contact_pose,
                contact_pose,
                float(args.cartesian_step_size),
                float(args.cartesian_rot_step_deg),
            )
        q_path = []
        for idx, contact_mat in enumerate(contact_path, start=1):
            tcp_pose = tcp_pose_from_contact(contact_mat, contact_offset)
            q_seed, success, err = _solve_ik(pin_model, tcp_link_index, tcp_pose, q_seed)
            if not success:
                suffix = "" if len(contact_path) == 1 else f" segment {idx}/{len(contact_path)}"
                raise RuntimeError(f"IK failed for {tag}{suffix}: err={np.round(err, 6).tolist()}")
            q_path.append(q_seed.astype(np.float32))
        last_contact_pose = contact_pose
        q_path_arr = np.stack(q_path, axis=0)
        audit_contact_path(tag, contact_path, q_path_arr)
        return q_path_arr

    if not run_stage(
        "home",
        q_seed.astype(np.float32),
        steps=max(1, int(args.hold_steps)),
    ):
        return 1

    for op_index, op in enumerate(task.operations, start=1):
        object_ids = list(op.pick.object_ids)
        reference_id = op.pick.reference_id
        ref_cfg = brick_cfgs_by_id[reference_id]
        pick_grid = op.pick.grid or list(ref_cfg.grid)
        print(f"[op {op_index:02d}] {op.name}: pick {object_ids}, ref={reference_id}, grid={pick_grid}")
        last_contact_pose = None

        pick = pick_target_from_press_side(
            plate_top_pos=plate_top,
            plate_size_xy=PLATE_SIZE_XY,
            brick=BRICK_BY_NAME[ref_cfg.type],
            grid=LegoGridPose(*pick_grid),
            press_side=int(op.pick.press_side),
            press_offset=op.pick.press_offset,
            plate_yaw=PLATE_YAW,
        )
        pick_contact = apex_pick_contact_pose(pick)
        pick_down_contact = pick_contact @ translation_matrix([0.0, 0.0, args.pick_press_depth])
        pick_attach_contact = shifted_pose(
            twist_about_local_pivot(pick_down_contact, RM75_TOOL_DISASSEMBLE_OFFSET_BLACK, args.pick_twist_deg),
            [0.0, 0.0, args.pick_up_height],
        )
        pick_upright_contact = shifted_pose(pick_down_contact, [0.0, 0.0, args.pick_up_height])

        target_ref_grid = op.place.target_grids[reference_id]
        target_ref_mat = pose_to_matrix(_brick_pose_from_grid(plate_top, ref_cfg.type, target_ref_grid))
        ref_contact_t_object = invert_transform(pick_contact) @ current_mats[reference_id]
        place_contact = target_ref_mat @ invert_transform(ref_contact_t_object)
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
        pre_pick_contact = pick_contact @ translation_matrix(
            [
                float(grab_offset[0]),
                float(grab_offset[1]),
                float(grab_offset[2] - abs(grab_offset[2])),
            ]
        )

        if not run_stage(
            f"{op.name}/pre_pick",
            solve_contact_path(pre_pick_contact, f"{op.name}/pre_pick"),
        ):
            return 1
        if not run_stage(
            f"{op.name}/pick_down",
            solve_contact_path(pick_down_contact, f"{op.name}/pick_down"),
        ):
            return 1

        attached_ids = object_ids
        contact_t_object = {
            brick_id: invert_transform(pick_contact) @ current_mats[brick_id]
            for brick_id in object_ids
        }
        released = False
        update_attached()
        print(f"[attach] {object_ids}")

        twist_steps = TWIST_IK_STEPS
        for twist_idx, deg in enumerate(np.linspace(0.0, args.pick_twist_deg, twist_steps + 1)[1:], start=1):
            twist_pose = twist_about_local_pivot(pick_down_contact, RM75_TOOL_DISASSEMBLE_OFFSET_BLACK, float(deg))
            twist_label = f"{op.name}/pick_twist_{twist_idx:02d}"
            if not run_stage(
                twist_label,
                solve_contact_path(twist_pose, twist_label),
            ):
                return 1
        if not run_stage(
            f"{op.name}/pick_attach",
            solve_contact_path(pick_attach_contact, f"{op.name}/pick_attach"),
        ):
            return 1
        if not run_stage(
            f"{op.name}/pick_upright",
            solve_contact_path(pick_upright_contact, f"{op.name}/pick_upright"),
        ):
            return 1
        hold(f"{op.name}/attached_hold")
        for stage, contact_pose, steps in [
            ("transfer", transfer_contact, None),
            ("pre_place", pre_place_contact, None),
            ("drop_up", drop_up_contact, max(2, args.steps_per_segment // 2)),
            ("place_down", place_contact, None),
            ("place_press", place_press_contact, max(2, args.steps_per_segment // 2)),
        ]:
            stage_label = f"{op.name}/{stage}"
            if not run_stage(
                stage_label,
                solve_contact_path(contact_pose, stage_label),
                steps=steps,
            ):
                return 1

        released = True
        for brick_id in object_ids:
            cfg = brick_cfgs_by_id[brick_id]
            target_mat = pose_to_matrix(_brick_pose_from_grid(plate_top, cfg.type, op.place.target_grids[brick_id]))
            current_mats[brick_id] = target_mat
            actors_by_id[brick_id].set_pose(matrix_to_sapien_pose(target_mat))
        placed_ids.update(object_ids)
        print(f"[release] snap {object_ids} to target grids")
        if not run_stage(
            f"{op.name}/place_twist",
            solve_contact_path(place_twist_contact, f"{op.name}/place_twist"),
        ):
            return 1
        hold(f"{op.name}/released_hold")
        if not run_stage(
            f"{op.name}/place_up",
            solve_contact_path(place_up_contact, f"{op.name}/place_up"),
        ):
            return 1

        if op.place.pause_after:
            print(f"[pause] {op.place.pause_after}")
            if args.auto_continue_pauses:
                print("[pause] auto-continue enabled")
            else:
                input("Press Enter to continue...")

    if not run_stage(
        "home_end",
        RM75LegoTool.keyframes["neutral"].qpos.astype(np.float32),
    ):
        return 1
    if collision_auditor is not None:
        collision_auditor.sample("final")
        collision_auditor.print_summary()
        if args.collision_log:
            collision_auditor.write_json(args.collision_log)
            print(f"[collision audit] wrote {args.collision_log}")
    print("PASS: LEGO robot motion preview")
    if args.render and args.wait_at_end:
        print("Preview is running. Press Enter or type 'q' then Enter to close.")
        while True:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)
            readable, _, _ = select.select([sys.stdin], [], [], 0.0)
            if readable:
                text = sys.stdin.readline().strip().lower()
                if text in ("", "q", "quit", "exit"):
                    break
    env.close()
    if real_exec is not None:
        real_exec.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
