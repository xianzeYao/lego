#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
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
import torch
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

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
    brick_pose_for_placement,
    build_colored_mesh_actor,
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
    build_frame_markers,
    invert_transform,
    pose_to_matrix,
    set_frame,
    shifted_pose,
    tcp_pose_from_contact,
    twist_about_local_pivot,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brick-key", default="lego_1x4")
    parser.add_argument("--press-side", type=int, default=2)
    parser.add_argument("--press-offset", type=int, default=1)
    parser.add_argument("--initial-grid", type=int, nargs=4, default=None)
    parser.add_argument("--target-grid", type=int, nargs=4, default=[14, 15, 1, 0])
    parser.add_argument("--contact-offset", type=float, nargs=3, default=CONTACT_OFFSET_TCP)
    parser.add_argument("--pre-height", type=float, default=0.06)
    parser.add_argument("--press-depth", type=float, default=0.0)
    parser.add_argument("--use-apex-grab-offset", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pick-attack-dir", type=int, choices=[-1, 1], default=1)
    parser.add_argument("--pick-twist-deg", type=float, default=-APEX_TWIST_DEG)
    parser.add_argument("--pick-up-height", type=float, default=0.035)
    parser.add_argument("--transfer-up-height", type=float, default=0.08)
    parser.add_argument("--include-pick", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--held-brick-offset", type=float, nargs=3, default=[0.0, 0.0, 0.018])
    parser.add_argument("--held-brick-yaw-deg", type=float, default=0.0)
    parser.add_argument("--place-attack-dir", type=int, choices=[-1, 1], default=1)
    parser.add_argument("--place-press-depth", type=float, default=0.0)
    parser.add_argument("--place-twist-deg", type=float, default=APEX_TWIST_DEG)
    parser.add_argument("--place-up-height", type=float, default=0.035)
    parser.add_argument("--steps-per-segment", type=int, default=80)
    parser.add_argument("--twist-ik-steps", type=int, default=14)
    parser.add_argument("--hold-steps", type=int, default=30)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--wait-at-end", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-dir", default="outputs/stage6_place_apex_offsets")
    parser.add_argument("--run-name", default=None)
    return parser.parse_args()


def pose_to_matrix_any(pose) -> np.ndarray:
    mat = np.eye(4, dtype=np.float64)
    if hasattr(pose, "to_transformation_matrix"):
        raw = as_numpy(pose.to_transformation_matrix())
        if raw.ndim == 3:
            raw = raw[0]
        mat[:3, :3] = raw[:3, :3]
    else:
        q = as_numpy(pose.q).reshape(-1)[:4]
        mat[:3, :3] = Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_matrix()
    mat[:3, 3] = as_numpy(pose.p).reshape(-1)[:3]
    return mat


def matrix_position(mat: np.ndarray) -> list[float]:
    return np.round(mat[:3, 3], 6).tolist()


def held_contact_t_brick(offset, yaw_deg: float) -> np.ndarray:
    pose = translation_matrix(offset)
    flip = np.eye(4, dtype=np.float64)
    yaw = Rotation.from_euler("z", yaw_deg, degrees=True).as_matrix()
    z_flip = Rotation.from_euler("x", 180.0, degrees=True).as_matrix()
    flip[:3, :3] = yaw @ z_flip
    return pose @ flip


def main() -> int:
    args = parse_args()
    run_name = args.run_name or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_pid{os.getpid()}"
    run_dir = Path(args.output_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
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

    placement = stage2_placement_by_key(args.brick_key)
    if args.initial_grid is not None:
        placement = replace(placement, grid=LegoGridPose(*args.initial_grid))

    target_grid = LegoGridPose(*args.target_grid)
    target_pose = apex_brick_actor_pose(
        PLATE_TOP_POS,
        PLATE_SIZE_XY,
        placement.brick,
        target_grid,
        PLATE_YAW,
    )
    target_marker = build_colored_mesh_actor(
        base_env.scene,
        name=f"stage6_target_{placement.key}_marker",
        mesh_path=placement.brick.mesh_path,
        color=[0.1, 0.9, 0.15, 0.28],
        pose=target_pose,
        body_type="kinematic",
    )
    _ = target_marker

    brick_actor = base_env.bricks[placement.key]
    initial_brick_mat = pose_to_matrix_any(brick_pose_for_placement(placement))
    brick_actor.set_pose(matrix_to_sapien_pose(initial_brick_mat))
    target_brick_mat = pose_to_matrix_any(target_pose)

    pick = pick_target_from_press_side(
        plate_top_pos=PLATE_TOP_POS,
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
    pick_attach_contact = shifted_pose(
        pick_twist_contact,
        np.array([0.0, 0.0, args.pick_up_height], dtype=np.float64),
    )
    pick_upright_contact = shifted_pose(
        pick_down_contact,
        np.array([0.0, 0.0, args.pick_up_height], dtype=np.float64),
    )

    home_contact_mat = pose_to_matrix_any(base_env.agent.tcp.pose) @ translation_matrix(contact_offset)
    if args.include_pick:
        # Attach at first contact, then keep the brick attached through the pry twist.
        contact_t_brick = invert_transform(pick_down_contact) @ initial_brick_mat
        place_contact = target_brick_mat @ invert_transform(contact_t_brick)
    else:
        contact_t_brick = held_contact_t_brick(args.held_brick_offset, args.held_brick_yaw_deg)
        initial_brick_mat = home_contact_mat @ contact_t_brick
        brick_actor.set_pose(matrix_to_sapien_pose(initial_brick_mat))
        place_contact = target_brick_mat @ invert_transform(contact_t_brick)

    place_offset = np.asarray(APEX_PLACE_BRICK_OFFSET, dtype=np.float64).copy()
    place_offset[1] *= float(args.place_attack_dir)
    pre_place_contact = place_contact @ translation_matrix([
        float(place_offset[0]),
        float(place_offset[1]),
        float(place_offset[2] - abs(place_offset[2])),
    ])
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
        "pre_pick": pick_contact @ translation_matrix([
            float(grab_offset[0]),
            float(grab_offset[1]),
            float(grab_offset[2] - abs(grab_offset[2])),
        ]) if args.use_apex_grab_offset else pick_contact @ translation_matrix([0.0, 0.0, -args.pre_height]),
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
    target_tcp_poses = {
        name: tcp_pose_from_contact(contact_pose, contact_offset)
        for name, contact_pose in contact_poses.items()
    }

    frame_markers = {}
    for name in ["pick_attach", "pick_upright", "transfer", "pre_place", "drop_up", "place_down", "place_twist", "place_up"]:
        frame_markers.update(build_frame_markers(
            base_env.scene,
            f"stage6_{name}",
            axis_length=0.032,
            thickness=0.001,
        ))
        set_frame(frame_markers, f"stage6_{name}", matrix_to_sapien_pose(contact_poses[name]))

    pin_model = base_env.agent.robot.create_pinocchio_model()
    tcp_link_index = int(as_numpy(base_env.agent.tcp.index).reshape(-1)[0])
    q_home = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float64)

    def solve_one(target_pose_in: sapien.Pose, q_seed: np.ndarray):
        target_mat = pose_to_matrix(target_pose_in)
        q_seed = np.asarray(q_seed, dtype=np.float64)

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
            return q_sol, success, np.concatenate([pos_err, rot_err])
        q_pin, pin_success, pin_err = pin_model.compute_inverse_kinematics(
            tcp_link_index,
            target_pose_in,
            initial_qpos=q_seed,
            eps=1e-4,
            max_iterations=2000,
            dt=0.1,
            damp=1e-6,
        )
        return np.asarray(q_pin, dtype=np.float64), bool(pin_success), np.asarray(pin_err, dtype=np.float64)

    q_targets: dict[str, np.ndarray] = {}
    ik_success: dict[str, bool] = {}
    ik_errors: dict[str, list[float]] = {}
    q_seed = q_home.copy()
    twist_path = []
    if args.include_pick:
        for name in ["pre_pick", "pick_down"]:
            q_sol, success, err = solve_one(target_tcp_poses[name], q_seed)
            q_targets[name] = q_sol.astype(np.float32)
            ik_success[name] = success
            ik_errors[name] = np.round(err, 6).tolist()
            q_seed = q_sol

        twist_success = True
        twist_err = np.zeros(6, dtype=np.float64)
        for deg in np.linspace(0.0, args.pick_twist_deg, max(1, args.twist_ik_steps) + 1)[1:]:
            twist_pose = twist_about_local_pivot(
                pick_down_contact,
                RM75_TOOL_DISASSEMBLE_OFFSET_BLACK,
                float(deg),
            )
            q_sol, success, err = solve_one(tcp_pose_from_contact(twist_pose, contact_offset), q_seed)
            twist_path.append(q_sol.astype(np.float32))
            twist_success &= success
            twist_err = err
            q_seed = q_sol
        q_targets["pick_twist"] = twist_path[-1]
        ik_success["pick_twist"] = twist_success
        ik_errors["pick_twist"] = np.round(twist_err, 6).tolist()

        q_sol, success, err = solve_one(target_tcp_poses["pick_attach"], q_seed)
        q_targets["pick_attach"] = q_sol.astype(np.float32)
        ik_success["pick_attach"] = success
        ik_errors["pick_attach"] = np.round(err, 6).tolist()
        q_seed = q_sol

        q_sol, success, err = solve_one(target_tcp_poses["pick_upright"], q_seed)
        q_targets["pick_upright"] = q_sol.astype(np.float32)
        ik_success["pick_upright"] = success
        ik_errors["pick_upright"] = np.round(err, 6).tolist()
        q_seed = q_sol

    for name in ["transfer", "pre_place", "drop_up", "place_down", "place_press", "place_twist", "place_up"]:
        q_sol, success, err = solve_one(target_tcp_poses[name], q_seed)
        q_targets[name] = q_sol.astype(np.float32)
        ik_success[name] = success
        ik_errors[name] = np.round(err, 6).tolist()
        q_seed = q_sol

    print("stage6 fake-attached brick:", args.brick_key)
    print("mode:", "pick_then_place" if args.include_pick else "home_held_place")
    print("initial grid[x,y,z,ori]:", [placement.grid.x, placement.grid.y, placement.grid.z, placement.grid.ori])
    print("target grid[x,y,z,ori]:", args.target_grid)
    print("press_side/press_offset:", args.press_side, args.press_offset)
    print("contact_offset_tcp:", contact_offset.tolist())
    print("APEX grab offset:", grab_offset.tolist())
    print("use_apex_grab_offset:", bool(args.use_apex_grab_offset))
    print("held_brick_offset_contact:", np.asarray(args.held_brick_offset, dtype=np.float64).tolist())
    print("held_brick_yaw_deg:", args.held_brick_yaw_deg)
    print("APEX place offset:", place_offset.tolist())
    print("pick/place twist deg:", args.pick_twist_deg, args.place_twist_deg)
    print("initial brick p:", matrix_position(initial_brick_mat))
    print("target brick p:", matrix_position(target_brick_mat))
    print("pick_attach contact p:", matrix_position(pick_attach_contact))
    print("pick_upright contact p:", matrix_position(pick_upright_contact))
    print("pre_place/place_offset contact p:", matrix_position(pre_place_contact))
    print("drop_up contact p:", matrix_position(drop_up_contact))
    print("place_down contact p:", matrix_position(place_contact))
    print("place_twist contact p:", matrix_position(place_twist_contact))
    print("place_up contact p:", matrix_position(place_up_contact))
    print_names = ["transfer", "pre_place", "drop_up", "place_down", "place_press", "place_twist", "place_up"]
    if args.include_pick:
        print_names = ["pre_pick", "pick_down", "pick_twist", "pick_attach", "pick_upright"] + print_names
    for name in print_names:
        print(name, "tcp target p:", np.round(np.asarray(target_tcp_poses[name].p), 6).tolist())
        print(name, "ik success:", ik_success[name], "err:", ik_errors[name])

    if not all(ik_success.values()):
        env.close()
        raise RuntimeError(f"IK failed: {ik_success}")

    attached = False
    released = False

    def current_contact_mat() -> np.ndarray:
        tcp_mat = pose_to_matrix_any(base_env.agent.tcp.pose)
        return tcp_mat @ translation_matrix(contact_offset)

    def update_fake_attach():
        if attached and not released:
            brick_actor.set_pose(matrix_to_sapien_pose(current_contact_mat() @ contact_t_brick))

    def render_step():
        update_fake_attach()
        base_env.update_markers()
        if args.render:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)

    def step_to(q_target, steps: int, tag: str):
        q_start = as_numpy(base_env.agent.robot.get_qpos()).reshape(-1)
        print(f"[move] {tag}")
        for alpha in np.linspace(0.0, 1.0, max(1, steps)):
            q = (1.0 - alpha) * q_start + alpha * q_target
            env.step(q.astype(np.float32))
            render_step()

    def hold(steps: int, tag: str):
        print(f"[hold] {tag}")
        q = as_numpy(base_env.agent.robot.get_qpos()).reshape(-1).astype(np.float32)
        for _ in range(steps):
            env.step(q)
            render_step()

    if not args.include_pick:
        attached = True
        brick_actor.set_pose(matrix_to_sapien_pose(home_contact_mat @ contact_t_brick))
        print("[attach] fake attach at home contact frame")

    step_to(q_home.astype(np.float32), args.hold_steps, "home")
    if args.include_pick:
        step_to(q_targets["pre_pick"], args.steps_per_segment, "pre_pick")
        step_to(q_targets["pick_down"], args.steps_per_segment, "pick_down")
        attached = True
        update_fake_attach()
        print("[attach] fake attach at pick_down contact frame")
        for idx, q_twist in enumerate(twist_path, start=1):
            step_to(q_twist, max(2, args.steps_per_segment // max(1, args.twist_ik_steps)), f"pick_twist_{idx:02d}")
        step_to(q_targets["pick_attach"], args.steps_per_segment, "pick_attach")
        step_to(q_targets["pick_upright"], args.steps_per_segment, "pick_upright")

    hold(args.hold_steps, "attached_hold")
    step_to(q_targets["transfer"], args.steps_per_segment, "transfer")
    step_to(q_targets["pre_place"], args.steps_per_segment, "pre_place")
    step_to(q_targets["drop_up"], max(2, args.steps_per_segment // 2), "drop_up")
    step_to(q_targets["place_down"], args.steps_per_segment, "place_down")
    step_to(q_targets["place_press"], max(2, args.steps_per_segment // 2), "place_press")
    released = True
    brick_actor.set_pose(matrix_to_sapien_pose(target_brick_mat))
    print("[release] snap fake-attached brick to target grid pose before place_twist")
    step_to(q_targets["place_twist"], args.steps_per_segment, "place_twist")
    hold(args.hold_steps, "released_hold")
    step_to(q_targets["place_up"], args.steps_per_segment, "place_up")

    final_brick_mat = pose_to_matrix_any(brick_actor.pose)
    final_error = float(np.linalg.norm(final_brick_mat[:3, 3] - target_brick_mat[:3, 3]))
    print("final brick p:", matrix_position(final_brick_mat))
    print("final target position error:", round(final_error, 8))
    summary = {
        "command": " ".join(sys.argv),
        "run_dir": str(run_dir),
        "brick_key": args.brick_key,
        "mode": "pick_then_place" if args.include_pick else "home_held_place",
        "initial_grid": [placement.grid.x, placement.grid.y, placement.grid.z, placement.grid.ori],
        "target_grid": list(args.target_grid),
        "press_side": args.press_side,
        "press_offset": args.press_offset,
        "contact_offset_tcp": contact_offset.tolist(),
        "use_apex_grab_offset": bool(args.use_apex_grab_offset),
        "apex_grab_offset": grab_offset.tolist(),
        "apex_place_offset": place_offset.tolist(),
        "pick_twist_deg": float(args.pick_twist_deg),
        "place_twist_deg": float(args.place_twist_deg),
        "pick_twist_pivot_offset_black": RM75_TOOL_DISASSEMBLE_OFFSET_BLACK.tolist(),
        "place_twist_pivot_offset_black": RM75_TOOL_ASSEMBLE_OFFSET_BLACK.tolist(),
        "contact_targets": {
            name: np.round(contact_poses[name][:3, 3], 6).tolist()
            for name in contact_poses
        },
        "ik_success": {name: bool(value) for name, value in ik_success.items()},
        "ik_errors": ik_errors,
        "final_brick_p": matrix_position(final_brick_mat),
        "target_brick_p": matrix_position(target_brick_mat),
        "final_target_position_error": round(final_error, 8),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("PASS: stage6 fake-attached place motion trend")
    if args.wait_at_end:
        input("Press Enter to close the ManiSkill viewer...")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
