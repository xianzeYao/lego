#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    LEGO_BRICK_SPECS,
    LegoGridPose,
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


def parse_args():
    parser = argparse.ArgumentParser(description="Render RM75 task_ladder robot motion from config/settings.json + task.json.")
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
    parser.add_argument("--hold-steps", type=int, default=30)
    parser.add_argument("--render", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--wait-at-end", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--auto-continue-pauses", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--robot-ip", type=str, default=None)
    parser.add_argument("--real-control-hz", type=float, default=10.0)
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
        np.clip(q_seed, JOINT_LOWER, JOINT_UPPER),
        bounds=(JOINT_LOWER, JOINT_UPPER),
        max_nfev=260,
        xtol=1e-10,
        ftol=1e-10,
        gtol=1e-10,
    )
    q_sol = np.asarray(result.x, dtype=np.float64)
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
    return np.asarray(q_pin, dtype=np.float64), bool(pin_success), np.asarray(pin_err, dtype=np.float64)


def interpolate_transform_path(start_mat: np.ndarray, end_mat: np.ndarray, step_size: float) -> list[np.ndarray]:
    start_mat = np.asarray(start_mat, dtype=np.float64).reshape(4, 4)
    end_mat = np.asarray(end_mat, dtype=np.float64).reshape(4, 4)
    distance = float(np.linalg.norm(end_mat[:3, 3] - start_mat[:3, 3]))
    if step_size <= 0.0 or distance <= 1e-9:
        return [end_mat.copy()]
    num_steps = max(1, int(np.ceil(distance / step_size)))
    key_rots = Rotation.from_matrix(np.stack([start_mat[:3, :3], end_mat[:3, :3]], axis=0))
    slerp = Slerp([0.0, 1.0], key_rots)
    out = []
    for alpha in np.linspace(0.0, 1.0, num_steps + 1, dtype=np.float64)[1:]:
        mat = np.eye(4, dtype=np.float64)
        mat[:3, 3] = (1.0 - alpha) * start_mat[:3, 3] + alpha * end_mat[:3, 3]
        mat[:3, :3] = slerp([float(alpha)]).as_matrix()[0]
        out.append(mat)
    return out


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
            name=f"task_ladder_robot_{brick_cfg.id}",
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

    last_contact_pose: np.ndarray | None = None

    def solve_contact_path(contact_pose: np.ndarray, tag: str) -> np.ndarray:
        nonlocal q_seed
        nonlocal last_contact_pose
        contact_pose = np.asarray(contact_pose, dtype=np.float64).reshape(4, 4)
        contact_path = [contact_pose]
        if last_contact_pose is not None:
            contact_path = interpolate_transform_path(last_contact_pose, contact_pose, float(args.cartesian_step_size))
        q_path = []
        for idx, contact_mat in enumerate(contact_path, start=1):
            tcp_pose = tcp_pose_from_contact(contact_mat, contact_offset)
            q_seed, success, err = _solve_ik(pin_model, tcp_link_index, tcp_pose, q_seed)
            if not success:
                suffix = "" if len(contact_path) == 1 else f" segment {idx}/{len(contact_path)}"
                raise RuntimeError(f"IK failed for {tag}{suffix}: err={np.round(err, 6).tolist()}")
            q_path.append(q_seed.astype(np.float32))
        last_contact_pose = contact_pose
        return np.stack(q_path, axis=0)

    if not run_q_path_stage(
        label="home",
        q_path=q_seed.astype(np.float32),
        steps=max(1, int(args.hold_steps)),
        **runner_kwargs,
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
            press_offset=int(op.pick.press_offset),
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
        ref_contact_t_object = invert_transform(pick_down_contact) @ current_mats[reference_id]
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

        if not run_q_path_stage(
            label=f"{op.name}/pre_pick",
            q_path=solve_contact_path(pre_pick_contact, f"{op.name}/pre_pick"),
            **runner_kwargs,
        ):
            return 1
        if not run_q_path_stage(
            label=f"{op.name}/pick_down",
            q_path=solve_contact_path(pick_down_contact, f"{op.name}/pick_down"),
            **runner_kwargs,
        ):
            return 1

        attached_ids = object_ids
        contact_t_object = {
            brick_id: invert_transform(pick_down_contact) @ current_mats[brick_id]
            for brick_id in object_ids
        }
        released = False
        update_attached()
        print(f"[attach] {object_ids}")

        twist_steps = TWIST_IK_STEPS
        for twist_idx, deg in enumerate(np.linspace(0.0, args.pick_twist_deg, twist_steps + 1)[1:], start=1):
            twist_pose = twist_about_local_pivot(pick_down_contact, RM75_TOOL_DISASSEMBLE_OFFSET_BLACK, float(deg))
            twist_label = f"{op.name}/pick_twist_{twist_idx:02d}"
            if not run_q_path_stage(
                label=twist_label,
                q_path=solve_contact_path(twist_pose, twist_label),
                **runner_kwargs,
            ):
                return 1
        if not run_q_path_stage(
            label=f"{op.name}/pick_attach",
            q_path=solve_contact_path(pick_attach_contact, f"{op.name}/pick_attach"),
            **runner_kwargs,
        ):
            return 1
        if not run_q_path_stage(
            label=f"{op.name}/pick_upright",
            q_path=solve_contact_path(pick_upright_contact, f"{op.name}/pick_upright"),
            **runner_kwargs,
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
            if not run_q_path_stage(
                label=stage_label,
                q_path=solve_contact_path(contact_pose, stage_label),
                steps=steps,
                **runner_kwargs,
            ):
                return 1

        released = True
        for brick_id in object_ids:
            cfg = brick_cfgs_by_id[brick_id]
            target_mat = pose_to_matrix(_brick_pose_from_grid(plate_top, cfg.type, op.place.target_grids[brick_id]))
            current_mats[brick_id] = target_mat
            actors_by_id[brick_id].set_pose(matrix_to_sapien_pose(target_mat))
        print(f"[release] snap {object_ids} to target grids")
        if not run_q_path_stage(
            label=f"{op.name}/place_twist",
            q_path=solve_contact_path(place_twist_contact, f"{op.name}/place_twist"),
            **runner_kwargs,
        ):
            return 1
        hold(f"{op.name}/released_hold")
        if not run_q_path_stage(
            label=f"{op.name}/place_up",
            q_path=solve_contact_path(place_up_contact, f"{op.name}/place_up"),
            **runner_kwargs,
        ):
            return 1

        if op.place.pause_after:
            print(f"[pause] {op.place.pause_after}")
            if args.auto_continue_pauses:
                print("[pause] auto-continue enabled")
            else:
                input("Press Enter to continue...")

    if not run_q_path_stage(
        label="home_end",
        q_path=RM75LegoTool.keyframes["neutral"].qpos.astype(np.float32),
        **runner_kwargs,
    ):
        return 1
    print("PASS: task_ladder robot motion preview")
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
