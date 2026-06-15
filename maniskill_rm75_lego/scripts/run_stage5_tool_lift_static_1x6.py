#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import gymnasium as gym
import imageio.v2 as imageio
import numpy as np
import sapien
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

import maniskill_rm75_lego.envs  # noqa: F401
from maniskill_rm75_lego.agents.rm75_lego_tool import RM75LegoTool
from maniskill_rm75_lego.envs.rm75_lego_pick_place import (
    PLATE_SIZE_XY,
    PLATE_TOP_POS,
    PLATE_YAW,
    stage2_placement_by_key,
)
from maniskill_rm75_lego.envs.rm75_lego_smoke import CONTACT_OFFSET_TCP
from maniskill_rm75_lego.lego_grid import matrix_to_sapien_pose, pick_target_from_press_side, translation_matrix
from maniskill_rm75_lego.scripts.run_stage4_pick_2x4 import (
    JOINT_LOWER,
    JOINT_UPPER,
    apex_pick_contact_pose,
    as_numpy,
    pose_to_matrix,
    rot_y_matrix,
    tcp_pose_from_contact,
)
from maniskill_rm75_lego.scripts.run_stage5_pick_dynamic_1x6 import (
    BRICK_DENSITY_MASS,
    build_baseplate_collision,
    build_dynamic_brick,
    create_physical_material,
    pose_to_matrix_any,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brick-key", default="lego_1x6")
    parser.add_argument("--press-side", type=int, default=2)
    parser.add_argument("--press-offset", type=int, default=2)
    parser.add_argument("--contact-offset", type=float, nargs=3, default=CONTACT_OFFSET_TCP)
    parser.add_argument("--press-depth", type=float, default=0.003)
    parser.add_argument("--twist-before-lift-deg", type=float, default=0.0)
    parser.add_argument("--lift-height", type=float, default=0.08)
    parser.add_argument("--steps-to-down", type=int, default=80)
    parser.add_argument("--settle-steps", type=int, default=20)
    parser.add_argument("--lift-steps", type=int, default=120)
    parser.add_argument("--hold-steps", type=int, default=60)
    parser.add_argument("--with-baseplate-collision", action="store_true")
    parser.add_argument("--brick-collision-mode", choices=["hollow", "solid"], default="hollow")
    parser.add_argument("--brick-mass", type=float, default=BRICK_DENSITY_MASS)
    parser.add_argument("--initial-clearance", type=float, default=0.0)
    parser.add_argument("--static-friction", type=float, default=1.8)
    parser.add_argument("--dynamic-friction", type=float, default=1.4)
    parser.add_argument("--restitution", type=float, default=0.0)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.02)
    parser.add_argument("--save-video", action="store_true")
    parser.add_argument("--video-fps", type=int, default=30)
    parser.add_argument("--video-stride", type=int, default=2)
    parser.add_argument("--wait-at-end", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-dir", default="outputs/stage5_tool_lift_static_1x6")
    parser.add_argument("--lift-threshold", type=float, default=0.04)
    parser.add_argument("--drop-threshold", type=float, default=0.015)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.output_dir) / f"{datetime.now().strftime('run_%Y%m%d_%H%M%S_%f')}_pid{os.getpid()}"
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
    if placement.key != "lego_1x6":
        raise ValueError("This static lift test is scoped to lego_1x6")

    phys_material = create_physical_material(
        base_env.scene,
        args.static_friction,
        args.dynamic_friction,
        args.restitution,
    )

    pick = pick_target_from_press_side(
        plate_top_pos=PLATE_TOP_POS,
        plate_size_xy=PLATE_SIZE_XY,
        brick=placement.brick,
        grid=placement.grid,
        press_side=args.press_side,
        press_offset=args.press_offset,
        plate_yaw=PLATE_YAW,
    )
    apex_contact_pose = apex_pick_contact_pose(pick)
    contact_offset = np.asarray(args.contact_offset, dtype=np.float64)

    down_contact = apex_contact_pose @ translation_matrix([0.0, 0.0, args.press_depth])
    twist_contact = down_contact @ rot_y_matrix(args.twist_before_lift_deg)
    lift_contact = twist_contact.copy()
    lift_contact[:3, 3] += np.array([0.0, 0.0, args.lift_height], dtype=np.float64)
    target_tcp_poses = {
        "pick_down": tcp_pose_from_contact(down_contact, contact_offset),
        "twist": tcp_pose_from_contact(twist_contact, contact_offset),
        "lift_up": tcp_pose_from_contact(lift_contact, contact_offset),
    }

    pin_model = base_env.agent.robot.create_pinocchio_model()
    tcp_link_index = int(as_numpy(base_env.agent.tcp.index).reshape(-1)[0])
    q_home = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float64)

    def solve_one_regularized(target_pose: sapien.Pose, q_seed: np.ndarray):
        target_mat = pose_to_matrix(target_pose)
        q_seed = np.asarray(q_seed, dtype=np.float64)

        def residual(q):
            pin_model.compute_forward_kinematics(q)
            cur_mat = pose_to_matrix(pin_model.get_link_pose(tcp_link_index))
            pos_err = target_mat[:3, 3] - cur_mat[:3, 3]
            rot_err = Rotation.from_matrix(target_mat[:3, :3] @ cur_mat[:3, :3].T).as_rotvec()
            return np.concatenate([pos_err * 80.0, rot_err * 1.4, (q - q_seed) * 0.18])

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
        return q_sol.astype(np.float32), success, np.concatenate([pos_err, rot_err])

    def solve_one(target_pose: sapien.Pose, q_seed: np.ndarray):
        q_sol, success, err = solve_one_regularized(target_pose, q_seed)
        if success:
            return q_sol, success, err
        q_pin, pin_success, pin_err = pin_model.compute_inverse_kinematics(
            tcp_link_index,
            target_pose,
            initial_qpos=q_seed,
            eps=1e-4,
            max_iterations=2000,
            dt=0.1,
            damp=1e-6,
        )
        return np.asarray(q_pin, dtype=np.float32), bool(pin_success), np.asarray(pin_err, dtype=np.float64)

    q_down, down_success, down_err = solve_one(target_tcp_poses["pick_down"], q_home)
    q_twist, twist_success, twist_err = solve_one(target_tcp_poses["twist"], q_down)
    q_lift, lift_success, lift_err = solve_one(target_tcp_poses["lift_up"], q_twist)
    if not (down_success and twist_success and lift_success):
        env.close()
        raise RuntimeError({
            "pick_down": [down_success, np.round(down_err, 7).tolist()],
            "twist": [twist_success, np.round(twist_err, 7).tolist()],
            "lift_up": [lift_success, np.round(lift_err, 7).tolist()],
        })

    frames = []
    rows = []
    render_count = 0
    dynamic_brick = None

    def maybe_render():
        nonlocal render_count
        base_env.update_markers()
        if args.render or args.save_video:
            frame = env.render()
            if args.save_video and render_count % max(1, args.video_stride) == 0:
                frame_np = as_numpy(frame)
                if frame_np.ndim == 4:
                    frame_np = frame_np[0]
                frames.append(frame_np[..., :3].astype(np.uint8))
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)
        render_count += 1

    def step_to(q_target, steps: int, tag: str):
        q_start = as_numpy(base_env.agent.robot.get_qpos()).reshape(-1)
        print(f"[move] {tag}")
        for i, alpha in enumerate(np.linspace(0.0, 1.0, max(1, steps))):
            q = (1.0 - alpha) * q_start + alpha * q_target
            env.step(q.astype(np.float32))
            if dynamic_brick is not None:
                record(tag, i)
            maybe_render()

    def hold(q_target, steps: int, tag: str):
        print(f"[hold] {tag}")
        for i in range(steps):
            env.step(q_target.astype(np.float32))
            record(tag, i)
            maybe_render()

    print("[setup] moving robot to pick_down before spawning dynamic LEGO")
    step_to(q_down, args.steps_to_down, "robot_to_pick_down_no_brick")

    # Remove the original kinematic visual duplicate; this test uses a dynamic brick spawned into the tool.
    base_env.bricks[placement.key].set_pose(sapien.Pose(p=[0.0, 0.0, -1.0]))
    dynamic_brick = build_dynamic_brick(
        base_env.scene,
        placement,
        color=[0.1, 0.45, 0.95, 1.0],
        mass=args.brick_mass,
        collision_mode=args.brick_collision_mode,
        initial_clearance=args.initial_clearance,
        phys_material=phys_material,
    )
    baseplate_collision = None
    if args.with_baseplate_collision:
        baseplate_collision = build_baseplate_collision(
            base_env.scene,
            patch_center_xy=(placement.grid.x, placement.grid.y),
            patch_radius=5,
            phys_material=phys_material,
        )

    initial_brick_mat = pose_to_matrix_any(dynamic_brick.pose)
    initial_brick_z = float(initial_brick_mat[2, 3])
    tool_link = base_env.agent.robot.find_link_by_name("lego_tool_link")

    def impulse_norm(obj1, obj2) -> float:
        if obj2 is None:
            return 0.0
        try:
            impulse = base_env.scene.get_pairwise_contact_impulses(obj1, obj2)
        except Exception:
            return 0.0
        return float(np.linalg.norm(as_numpy(impulse).reshape(-1)))

    def record(tag: str, step_idx: int):
        brick_mat = pose_to_matrix_any(dynamic_brick.pose)
        tcp_mat = pose_to_matrix_any(base_env.agent.tcp.pose)
        rows.append({
            "tag": tag,
            "step": step_idx,
            "brick_x": float(brick_mat[0, 3]),
            "brick_y": float(brick_mat[1, 3]),
            "brick_z": float(brick_mat[2, 3]),
            "tcp_x": float(tcp_mat[0, 3]),
            "tcp_y": float(tcp_mat[1, 3]),
            "tcp_z": float(tcp_mat[2, 3]),
            "brick_lift": float(brick_mat[2, 3] - initial_brick_z),
            "brick_tool_impulse": impulse_norm(dynamic_brick, tool_link),
            "brick_baseplate_impulse": impulse_norm(dynamic_brick, baseplate_collision),
        })

    hold(q_down, args.settle_steps, "settle_aligned")
    if abs(args.twist_before_lift_deg) > 1.0e-6:
        step_to(q_twist, max(10, args.lift_steps // 4), "twist_before_lift")
    step_to(q_lift, args.lift_steps, "lift_up")
    hold(q_lift, args.hold_steps, "hold_lift")

    csv_path = run_dir / "trajectory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    video_path = None
    if args.save_video and frames:
        video_path = run_dir / "run.mp4"
        imageio.mimsave(video_path, frames, fps=args.video_fps)

    final = rows[-1]
    max_lift = max(r["brick_lift"] for r in rows)
    final_lift = final["brick_lift"]
    lift_loss = max_lift - final_lift
    success = max_lift >= args.lift_threshold and lift_loss <= args.drop_threshold
    summary = {
        "success": success,
        "run_dir": str(run_dir),
        "video_path": str(video_path) if video_path else None,
        "brick": args.brick_key,
        "grid": [placement.grid.x, placement.grid.y, placement.grid.z, placement.grid.ori],
        "press_side": args.press_side,
        "press_offset": args.press_offset,
        "contact_offset_tcp": contact_offset.tolist(),
        "press_depth": args.press_depth,
        "twist_before_lift_deg": args.twist_before_lift_deg,
        "lift_height": args.lift_height,
        "with_baseplate_collision": args.with_baseplate_collision,
        "brick_collision_mode": args.brick_collision_mode,
        "initial_brick_z": initial_brick_z,
        "max_lift_m": max_lift,
        "final_lift_m": final_lift,
        "lift_loss_m": lift_loss,
        "max_contact_impulse": {
            "brick_tool": max(r["brick_tool_impulse"] for r in rows),
            "brick_baseplate": max(r["brick_baseplate_impulse"] for r in rows),
        },
        "ik_success": {
            "pick_down": down_success,
            "twist": twist_success,
            "lift_up": lift_success,
        },
        "ik_errors": {
            "pick_down": np.round(down_err, 7).tolist(),
            "twist": np.round(twist_err, 7).tolist(),
            "lift_up": np.round(lift_err, 7).tolist(),
        },
        "selected_stud_centers": np.round(pick.selected_stud_centers, 6).tolist(),
        "pick_contact_target": np.round(pick.contact_point, 6).tolist(),
        "outward_normal": np.round(pick.outward_normal, 6).tolist(),
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print("PASS" if success else "FAIL", "stage5 static tool lift test")
    print("wrote:", summary_path)
    if args.wait_at_end:
        input("Press Enter to close the ManiSkill viewer...")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
