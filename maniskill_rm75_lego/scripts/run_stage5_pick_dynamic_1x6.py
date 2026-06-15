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
import torch
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

import maniskill_rm75_lego.envs  # noqa: F401
from maniskill_rm75_lego.agents.rm75_lego_tool import RM75LegoTool
from maniskill_rm75_lego.apex_mr_reference import APEX_TWIST_DEG
from maniskill_rm75_lego.envs.rm75_lego_pick_place import (
    PLATE_SIZE_XY,
    PLATE_TOP_POS,
    PLATE_YAW,
    brick_pose_for_placement,
    stage2_placement_by_key,
)
from maniskill_rm75_lego.envs.rm75_lego_smoke import CONTACT_OFFSET_TCP
from maniskill_rm75_lego.lego_grid import (
    BRICK_BODY_HEIGHT,
    BASEPLATE_HALF_THICKNESS,
    STUD_HEIGHT,
    STUD_PITCH,
    apex_brick_bottom_pose,
    matrix_to_sapien_pose,
    pick_target_from_press_side,
    plate_grid_point_world,
    translation_matrix,
)
from maniskill_rm75_lego.scripts.run_stage4_pick_2x4 import (
    JOINT_LOWER,
    JOINT_UPPER,
    apex_pick_contact_pose,
    as_numpy,
    invert_transform,
    pose_to_matrix,
    rot_y_matrix,
    tcp_pose_from_contact,
)


STUD_RADIUS = 0.0024
STUD_HALF_HEIGHT = STUD_HEIGHT / 2.0
BRICK_DENSITY_MASS = 0.006


def create_physical_material(scene, static_friction: float, dynamic_friction: float, restitution: float):
    candidates = [scene]
    candidates.extend(getattr(scene, "sub_scenes", []))
    for candidate in candidates:
        if hasattr(candidate, "create_physical_material"):
            return candidate.create_physical_material(
                float(static_friction),
                float(dynamic_friction),
                float(restitution),
            )
    return None


def pose_to_matrix_any(pose) -> np.ndarray:
    mat = np.eye(4, dtype=np.float64)
    if hasattr(pose, "to_transformation_matrix"):
        raw = pose.to_transformation_matrix()
        raw = as_numpy(raw)
        if raw.ndim == 3:
            raw = raw[0]
        mat[:3, :3] = raw[:3, :3]
    else:
        q = as_numpy(pose.q).reshape(-1)[:4]
        mat[:3, :3] = Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_matrix()
    mat[:3, 3] = as_numpy(pose.p).reshape(-1)[:3]
    return mat


def mat_rel(a_world: np.ndarray, b_world: np.ndarray) -> np.ndarray:
    return invert_transform(a_world) @ b_world


def rel_error(reference: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    delta = invert_transform(reference) @ current
    trans = float(np.linalg.norm(delta[:3, 3]))
    rot = float(np.linalg.norm(Rotation.from_matrix(delta[:3, :3]).as_rotvec()))
    return trans, np.rad2deg(rot)


def build_dynamic_brick(
    scene,
    placement,
    color,
    mass: float,
    collision_mode: str,
    initial_clearance: float,
    phys_material=None,
):
    brick = placement.brick
    length = brick.studs_x * STUD_PITCH
    width = brick.studs_y * STUD_PITCH
    builder = scene.create_actor_builder()
    material = sapien.render.RenderMaterial(base_color=color)

    body_pose = sapien.Pose(p=[0.0, 0.0, -BRICK_BODY_HEIGHT / 2.0])
    body_half = [length / 2.0, width / 2.0, BRICK_BODY_HEIGHT / 2.0]
    if collision_mode == "solid":
        builder.add_box_collision(pose=body_pose, half_size=body_half, material=phys_material)
    elif collision_mode == "hollow":
        wall = 0.0012
        top = 0.0014
        side_height = BRICK_BODY_HEIGHT - top
        side_z = -top - side_height / 2.0
        builder.add_box_collision(
            pose=sapien.Pose(p=[0.0, 0.0, -top / 2.0]),
            half_size=[length / 2.0, width / 2.0, top / 2.0],
            material=phys_material,
        )
        builder.add_box_collision(
            pose=sapien.Pose(p=[0.0, width / 2.0 - wall / 2.0, side_z]),
            half_size=[length / 2.0, wall / 2.0, side_height / 2.0],
            material=phys_material,
        )
        builder.add_box_collision(
            pose=sapien.Pose(p=[0.0, -width / 2.0 + wall / 2.0, side_z]),
            half_size=[length / 2.0, wall / 2.0, side_height / 2.0],
            material=phys_material,
        )
        builder.add_box_collision(
            pose=sapien.Pose(p=[length / 2.0 - wall / 2.0, 0.0, side_z]),
            half_size=[wall / 2.0, width / 2.0, side_height / 2.0],
            material=phys_material,
        )
        builder.add_box_collision(
            pose=sapien.Pose(p=[-length / 2.0 + wall / 2.0, 0.0, side_z]),
            half_size=[wall / 2.0, width / 2.0, side_height / 2.0],
            material=phys_material,
        )
    else:
        raise ValueError(f"Unsupported brick collision mode: {collision_mode}")
    builder.add_box_visual(pose=body_pose, half_size=body_half, material=material)

    for ix in range(brick.studs_x):
        for iy in range(brick.studs_y):
            x = -length / 2.0 + (ix + 0.5) * STUD_PITCH
            y = -width / 2.0 + (iy + 0.5) * STUD_PITCH
            stud_pose = sapien.Pose(p=[float(x), float(y), STUD_HALF_HEIGHT])
            builder.add_cylinder_collision(
                pose=stud_pose,
                radius=STUD_RADIUS,
                half_length=STUD_HALF_HEIGHT,
                material=phys_material,
            )
            builder.add_cylinder_visual(
                pose=stud_pose,
                radius=STUD_RADIUS,
                half_length=STUD_HALF_HEIGHT,
                material=material,
            )

    inertia = [
        mass * (width**2 + BRICK_BODY_HEIGHT**2) / 12.0,
        mass * (length**2 + BRICK_BODY_HEIGHT**2) / 12.0,
        mass * (length**2 + width**2) / 12.0,
    ]
    builder.set_mass_and_inertia(
        float(mass),
        sapien.Pose(p=[0.0, 0.0, -BRICK_BODY_HEIGHT / 2.0]),
        inertia,
    )
    initial_pose = brick_pose_for_placement(placement)
    initial_pose.set_p(initial_pose.p + np.array([0.0, 0.0, initial_clearance], dtype=np.float32))
    builder.set_initial_pose(initial_pose)
    actor = builder.build(name=f"stage5_dynamic_{placement.key}")
    return actor


def build_baseplate_collision(scene, patch_center_xy=None, patch_radius: int | None = None, phys_material=None):
    builder = scene.create_actor_builder()
    builder.set_initial_pose(sapien.Pose())
    builder.add_box_collision(
        pose=sapien.Pose(p=[
            float(PLATE_TOP_POS[0]),
            float(PLATE_TOP_POS[1]),
            float(PLATE_TOP_POS[2] - BASEPLATE_HALF_THICKNESS),
        ]),
        half_size=[PLATE_SIZE_XY[0] * STUD_PITCH / 2.0, PLATE_SIZE_XY[1] * STUD_PITCH / 2.0, BASEPLATE_HALF_THICKNESS],
        material=phys_material,
    )

    if patch_center_xy is None or patch_radius is None:
        xs = range(PLATE_SIZE_XY[0])
        ys = range(PLATE_SIZE_XY[1])
    else:
        cx, cy = patch_center_xy
        xs = range(max(0, cx - patch_radius), min(PLATE_SIZE_XY[0], cx + patch_radius + 1))
        ys = range(max(0, cy - patch_radius), min(PLATE_SIZE_XY[1], cy + patch_radius + 1))

    for x in xs:
        for y in ys:
            p = plate_grid_point_world(PLATE_TOP_POS, PLATE_SIZE_XY, x, y, 0, PLATE_YAW)
            p[2] = float(PLATE_TOP_POS[2] + STUD_HALF_HEIGHT)
            builder.add_cylinder_collision(
                pose=sapien.Pose(p=p.tolist()),
                radius=STUD_RADIUS,
                half_length=STUD_HALF_HEIGHT,
                material=phys_material,
            )
    return builder.build_static(name="stage5_baseplate_collision")


def build_tool_proxy(scene, stud_local_points: np.ndarray, initial_pose: sapien.Pose, phys_material=None):
    builder = scene.create_actor_builder()
    builder.set_initial_pose(initial_pose)
    material = sapien.render.RenderMaterial(base_color=[1.0, 0.2, 0.2, 0.35])
    wall = 0.0010
    cup_radius = 0.0031
    height = 0.0060
    z = height / 2.0
    for idx, point in enumerate(stud_local_points):
        cx, cy = float(point[0]), float(point[1])
        pieces = [
            ([cx - cup_radius, cy, z], [wall / 2.0, cup_radius + wall, height / 2.0]),
            ([cx + cup_radius, cy, z], [wall / 2.0, cup_radius + wall, height / 2.0]),
            ([cx, cy - cup_radius, z], [cup_radius + wall, wall / 2.0, height / 2.0]),
            ([cx, cy + cup_radius, z], [cup_radius + wall, wall / 2.0, height / 2.0]),
        ]
        for piece_idx, (pos, half_size) in enumerate(pieces):
            pose = sapien.Pose(p=pos)
            builder.add_box_collision(pose=pose, half_size=half_size, material=phys_material)
            builder.add_box_visual(pose=pose, half_size=half_size, material=material)
        builder.add_cylinder_visual(
            pose=sapien.Pose(p=[cx, cy, z]),
            radius=STUD_RADIUS,
            half_length=height / 2.0,
            material=sapien.render.RenderMaterial(base_color=[1.0, 1.0, 0.0, 0.25]),
        )
    return builder.build_kinematic(name="stage5_tool_contact_proxy")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brick-key", default="lego_1x6")
    parser.add_argument("--press-side", type=int, default=2)
    parser.add_argument("--press-offset", type=int, default=2)
    parser.add_argument("--contact-offset", type=float, nargs=3, default=CONTACT_OFFSET_TCP)
    parser.add_argument("--pre-height", type=float, default=0.06)
    parser.add_argument("--press-depth", type=float, default=0.005)
    parser.add_argument("--twist-up-height", type=float, default=0.015)
    parser.add_argument("--pick-twist-deg", type=float, default=-APEX_TWIST_DEG)
    parser.add_argument("--verify-up", type=float, default=0.025)
    parser.add_argument("--verify-x", type=float, default=0.02)
    parser.add_argument("--verify-y", type=float, default=-0.015)
    parser.add_argument("--steps-per-segment", type=int, default=80)
    parser.add_argument("--twist-ik-steps", type=int, default=14)
    parser.add_argument("--hold-steps", type=int, default=30)
    parser.add_argument("--settle-steps", type=int, default=40)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.02)
    parser.add_argument("--save-video", action="store_true")
    parser.add_argument("--video-fps", type=int, default=30)
    parser.add_argument("--video-stride", type=int, default=1)
    parser.add_argument("--wait-at-end", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--brick-mass", type=float, default=BRICK_DENSITY_MASS)
    parser.add_argument("--brick-collision-mode", choices=["hollow", "solid"], default="hollow")
    parser.add_argument("--initial-clearance", type=float, default=0.001)
    parser.add_argument("--static-friction", type=float, default=1.8)
    parser.add_argument("--dynamic-friction", type=float, default=1.4)
    parser.add_argument("--restitution", type=float, default=0.0)
    parser.add_argument("--local-stud-patch-radius", type=int, default=5)
    parser.add_argument("--full-baseplate-studs", action="store_true")
    parser.add_argument("--tool-proxy", action="store_true")
    parser.add_argument("--output-dir", default="outputs/stage5_pick_dynamic_1x6")
    parser.add_argument("--drift-threshold", type=float, default=0.005)
    parser.add_argument("--rot-threshold-deg", type=float, default=10.0)
    parser.add_argument("--lift-threshold", type=float, default=0.005)
    parser.add_argument("--strict-exit-code", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_dir)
    run_id = f"{datetime.now().strftime('run_%Y%m%d_%H%M%S_%f')}_pid{os.getpid()}"
    run_dir = output_root / run_id
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
        raise ValueError("Stage 5 first pass is scoped to lego_1x6")
    phys_material = create_physical_material(
        base_env.scene,
        args.static_friction,
        args.dynamic_friction,
        args.restitution,
    )

    # Move the kinematic visual duplicate away; the dynamic primitive brick is the tested object.
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

    if args.full_baseplate_studs:
        baseplate_collision = build_baseplate_collision(base_env.scene, phys_material=phys_material)
        stud_patch = "full"
    else:
        patch_center = (placement.grid.x, placement.grid.y)
        baseplate_collision = build_baseplate_collision(
            base_env.scene,
            patch_center_xy=patch_center,
            patch_radius=args.local_stud_patch_radius,
            phys_material=phys_material,
        )
        stud_patch = {
            "center": list(patch_center),
            "radius": args.local_stud_patch_radius,
        }

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
    selected_stud_local = []
    inv_apex_contact_pose = invert_transform(apex_contact_pose)
    for stud in pick.selected_stud_centers:
        local = inv_apex_contact_pose @ np.array([stud[0], stud[1], stud[2], 1.0], dtype=np.float64)
        selected_stud_local.append(local[:3])
    selected_stud_local = np.asarray(selected_stud_local, dtype=np.float64)
    tool_proxy_actor = None
    if args.tool_proxy:
        tool_proxy_actor = build_tool_proxy(
            base_env.scene,
            selected_stud_local,
            matrix_to_sapien_pose(apex_contact_pose),
            phys_material=phys_material,
        )

    pin_model = base_env.agent.robot.create_pinocchio_model()
    tcp_link_index = int(as_numpy(base_env.agent.tcp.index).reshape(-1)[0])
    q_home = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float64)

    def contact_waypoint_poses() -> dict[str, np.ndarray]:
        pre_contact = apex_contact_pose @ translation_matrix([0.0, 0.0, -args.pre_height])
        down_contact = apex_contact_pose @ translation_matrix([0.0, 0.0, args.press_depth])
        twist_contact = down_contact @ rot_y_matrix(args.pick_twist_deg)
        twist_up_contact = twist_contact.copy()
        twist_up_contact[:3, 3] += np.array([0.0, 0.0, args.twist_up_height], dtype=np.float64)
        verify_1 = twist_up_contact.copy()
        verify_1[:3, 3] += np.array([0.0, 0.0, args.verify_up], dtype=np.float64)
        verify_2 = verify_1.copy()
        verify_2[:3, 3] += np.array([args.verify_x, 0.0, 0.0], dtype=np.float64)
        verify_3 = verify_2.copy()
        verify_3[:3, 3] += np.array([0.0, args.verify_y, 0.0], dtype=np.float64)
        return {
            "pre_pick": pre_contact,
            "pick_down": down_contact,
            "pick_twist": twist_contact,
            "pick_twist_up": twist_up_contact,
            "verify_up": verify_1,
            "verify_x": verify_2,
            "verify_y": verify_3,
        }

    contact_poses = contact_waypoint_poses()
    target_tcp_poses = {
        name: tcp_pose_from_contact(contact_pose, contact_offset)
        for name, contact_pose in contact_poses.items()
    }

    def solve_one_regularized(target_pose: sapien.Pose, q_seed: np.ndarray):
        target_mat = pose_to_matrix(target_pose)
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
            max_nfev=240,
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
        return q_sol, success, np.concatenate([pos_err, rot_err])

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
        return np.asarray(q_pin, dtype=np.float64), bool(pin_success), np.asarray(pin_err, dtype=np.float64)

    q_targets: dict[str, np.ndarray] = {}
    ik_success: dict[str, bool] = {}
    ik_errors: dict[str, list[float]] = {}
    q_seed = q_home.copy()
    for name in ["pre_pick", "pick_down"]:
        q_sol, success, err = solve_one(target_tcp_poses[name], q_seed)
        q_targets[name] = q_sol.astype(np.float32)
        ik_success[name] = success
        ik_errors[name] = np.round(err, 7).tolist()
        q_seed = q_sol

    for name in ["pick_twist", "pick_twist_up", "verify_up", "verify_x", "verify_y"]:
        q_sol, success, err = solve_one(target_tcp_poses[name], q_seed)
        q_targets[name] = q_sol.astype(np.float32)
        ik_success[name] = success
        ik_errors[name] = np.round(err, 7).tolist()
        q_seed = q_sol

    if not all(ik_success.values()):
        env.close()
        raise RuntimeError(f"IK failed: {ik_success}")

    rows = []
    video_frames = []
    render_step_count = 0
    initial_brick_mat = pose_to_matrix_any(dynamic_brick.pose)
    initial_brick_z = float(initial_brick_mat[2, 3])
    attach_rel_reference = None
    tool_link = base_env.agent.robot.find_link_by_name("lego_tool_link")
    tcp_link = base_env.agent.robot.find_link_by_name("lego_tool_tcp")

    def impulse_norm(obj1, obj2) -> float:
        try:
            impulse = base_env.scene.get_pairwise_contact_impulses(obj1, obj2)
        except Exception:
            return 0.0
        arr = as_numpy(impulse)
        return float(np.linalg.norm(arr.reshape(-1)))

    def current_contact_mat() -> np.ndarray:
        tcp_mat = pose_to_matrix_any(base_env.agent.tcp.pose)
        return tcp_mat @ translation_matrix(contact_offset)

    def record(tag: str, step_idx: int):
        nonlocal attach_rel_reference
        brick_mat = pose_to_matrix_any(dynamic_brick.pose)
        tcp_mat = pose_to_matrix_any(base_env.agent.tcp.pose)
        contact_mat = tcp_mat @ translation_matrix(contact_offset)
        rel = mat_rel(contact_mat, brick_mat)
        if attach_rel_reference is None and tag == "pick_twist_up":
            attach_rel_reference = rel.copy()
        if attach_rel_reference is None:
            drift, rot_drift = 0.0, 0.0
        else:
            drift, rot_drift = rel_error(attach_rel_reference, rel)
        rows.append({
            "tag": tag,
            "step": step_idx,
            "brick_x": float(brick_mat[0, 3]),
            "brick_y": float(brick_mat[1, 3]),
            "brick_z": float(brick_mat[2, 3]),
            "tcp_x": float(tcp_mat[0, 3]),
            "tcp_y": float(tcp_mat[1, 3]),
            "tcp_z": float(tcp_mat[2, 3]),
            "contact_x": float(contact_mat[0, 3]),
            "contact_y": float(contact_mat[1, 3]),
            "contact_z": float(contact_mat[2, 3]),
            "brick_lift": float(brick_mat[2, 3] - initial_brick_z),
            "rel_drift_m": drift,
            "rel_rot_drift_deg": rot_drift,
            "brick_tool_impulse": impulse_norm(dynamic_brick, tool_link),
            "brick_tcp_impulse": impulse_norm(dynamic_brick, tcp_link),
            "brick_tool_proxy_impulse": (
                impulse_norm(dynamic_brick, tool_proxy_actor)
                if tool_proxy_actor is not None
                else 0.0
            ),
            "brick_baseplate_impulse": impulse_norm(dynamic_brick, baseplate_collision),
        })

    def render_step():
        nonlocal render_step_count
        if tool_proxy_actor is not None:
            tool_proxy_actor.set_pose(matrix_to_sapien_pose(current_contact_mat()))
        base_env.update_markers()
        if args.render or args.save_video:
            frame = env.render()
            if args.save_video and render_step_count % max(1, args.video_stride) == 0:
                frame_np = as_numpy(frame)
                if frame_np.ndim == 4:
                    frame_np = frame_np[0]
                video_frames.append(frame_np[..., :3].astype(np.uint8))
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)
        render_step_count += 1

    def step_to(q_target, steps: int, tag: str):
        q_start = as_numpy(base_env.agent.robot.get_qpos()).reshape(-1)
        print(f"[move] {tag}")
        for i, alpha in enumerate(np.linspace(0.0, 1.0, max(1, steps))):
            if tool_proxy_actor is not None:
                tool_proxy_actor.set_pose(matrix_to_sapien_pose(current_contact_mat()))
            q = (1.0 - alpha) * q_start + alpha * q_target
            env.step(q.astype(np.float32))
            record(tag, i)
            render_step()

    def hold(steps: int, tag: str):
        q = as_numpy(base_env.agent.robot.get_qpos()).reshape(-1).astype(np.float32)
        print(f"[hold] {tag}")
        for i in range(steps):
            if tool_proxy_actor is not None:
                tool_proxy_actor.set_pose(matrix_to_sapien_pose(current_contact_mat()))
            env.step(q)
            record(tag, i)
            render_step()

    for _ in range(args.settle_steps):
        if tool_proxy_actor is not None:
            tool_proxy_actor.set_pose(matrix_to_sapien_pose(current_contact_mat()))
        env.step(q_home.astype(np.float32))
        render_step()
    record("initial", 0)

    step_to(q_home.astype(np.float32), args.hold_steps, "home")
    step_to(q_targets["pre_pick"], args.steps_per_segment, "pre_pick")
    step_to(q_targets["pick_down"], args.steps_per_segment, "pick_down")
    step_to(q_targets["pick_twist"], args.steps_per_segment, "pick_twist")
    hold(args.hold_steps, "twist_hold")
    step_to(q_targets["pick_twist_up"], args.steps_per_segment, "pick_twist_up")
    hold(args.hold_steps, "picked_hold")
    step_to(q_targets["verify_up"], args.steps_per_segment, "verify_up")
    step_to(q_targets["verify_x"], args.steps_per_segment, "verify_x")
    step_to(q_targets["verify_y"], args.steps_per_segment, "verify_y")
    hold(args.hold_steps, "verify_hold")

    csv_path = run_dir / "trajectory.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    video_path = None
    if args.save_video and video_frames:
        video_path = run_dir / "run.mp4"
        imageio.mimsave(video_path, video_frames, fps=args.video_fps)

    verify_rows = [r for r in rows if r["tag"] in {"picked_hold", "verify_up", "verify_x", "verify_y", "verify_hold"}]
    final = rows[-1]
    max_lift = max(r["brick_lift"] for r in rows)
    final_lift = final["brick_lift"]
    max_drift = max((r["rel_drift_m"] for r in verify_rows), default=0.0)
    max_rot_drift = max((r["rel_rot_drift_deg"] for r in verify_rows), default=0.0)
    max_tool_impulse = max(r["brick_tool_impulse"] for r in rows)
    max_tcp_impulse = max(r["brick_tcp_impulse"] for r in rows)
    max_tool_proxy_impulse = max(r["brick_tool_proxy_impulse"] for r in rows)
    max_baseplate_impulse = max(r["brick_baseplate_impulse"] for r in rows)
    success = (
        final_lift > args.lift_threshold
        and max_lift > args.lift_threshold
        and max_drift < args.drift_threshold
        and max_rot_drift < args.rot_threshold_deg
    )

    summary = {
        "success": success,
        "run_dir": str(run_dir),
        "brick": args.brick_key,
        "grid": [placement.grid.x, placement.grid.y, placement.grid.z, placement.grid.ori],
        "press_side": args.press_side,
        "press_offset": args.press_offset,
        "contact_offset_tcp": contact_offset.tolist(),
        "pre_height": args.pre_height,
        "press_depth": args.press_depth,
        "pick_twist_deg": args.pick_twist_deg,
        "twist_up_height": args.twist_up_height,
        "baseplate_studs": stud_patch,
        "tool_proxy": args.tool_proxy,
        "video_path": str(video_path) if video_path is not None else None,
        "physics": {
            "brick_mass": args.brick_mass,
            "brick_collision_mode": args.brick_collision_mode,
            "initial_clearance": args.initial_clearance,
            "static_friction": args.static_friction,
            "dynamic_friction": args.dynamic_friction,
            "restitution": args.restitution,
        },
        "initial_brick_z": initial_brick_z,
        "final_lift_m": final_lift,
        "max_lift_m": max_lift,
        "max_verify_rel_drift_m": max_drift,
        "max_verify_rel_rot_drift_deg": max_rot_drift,
        "max_contact_impulse": {
            "brick_tool": max_tool_impulse,
            "brick_tcp": max_tcp_impulse,
            "brick_tool_proxy": max_tool_proxy_impulse,
            "brick_baseplate": max_baseplate_impulse,
        },
        "thresholds": {
            "lift_m": args.lift_threshold,
            "rel_drift_m": args.drift_threshold,
            "rel_rot_deg": args.rot_threshold_deg,
        },
        "ik_success": ik_success,
        "ik_errors": ik_errors,
        "selected_stud_centers": np.round(pick.selected_stud_centers, 6).tolist(),
        "selected_stud_local_in_contact_frame": np.round(selected_stud_local, 6).tolist(),
        "pick_contact_target": np.round(pick.contact_point, 6).tolist(),
        "outward_normal": np.round(pick.outward_normal, 6).tolist(),
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print("PASS" if success else "FAIL", f"stage5 dynamic pick check for {args.brick_key}")
    print("wrote:", summary_path)

    if args.wait_at_end:
        input("Press Enter to close the ManiSkill viewer...")
    env.close()
    return 0 if success or not args.strict_exit_code else 2


if __name__ == "__main__":
    raise SystemExit(main())
