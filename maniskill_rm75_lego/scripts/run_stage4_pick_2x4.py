#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import replace
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
from maniskill_rm75_lego.envs.rm75_lego_pick_place import (
    PLATE_SIZE_XY,
    PLATE_TOP_POS,
    PLATE_YAW,
    brick_pose_for_placement,
    stage2_placement_by_key,
)
from maniskill_rm75_lego.envs.rm75_lego_smoke import CONTACT_OFFSET_TCP
from maniskill_rm75_lego.lego_grid import (
    LegoGridPose,
    matrix_to_sapien_pose,
    pick_target_from_press_side,
    translation_matrix,
)
from maniskill_rm75_lego.apex_mr_reference import APEX_TWIST_DEG


JOINT_LOWER = np.array([-3.106, -2.2689, -3.106, -2.356, -3.106, -2.234, -6.28], dtype=np.float64)
JOINT_UPPER = np.array([3.106, 2.2689, 3.106, 2.356, 3.106, 2.234, 6.28], dtype=np.float64)
STACKED_2X4_GRID = LegoGridPose(x=15, y=13, z=1, ori=0)
STACKED_2X4_SUPPORT_KEY = "lego_2x6"


def as_numpy(x):
    if torch.is_tensor(x):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def pose_pos_np(pose) -> np.ndarray:
    return as_numpy(pose.p).reshape(-1)[:3]


def pose_to_matrix(pose: sapien.Pose) -> np.ndarray:
    mat = np.eye(4, dtype=np.float64)
    mat[:3, :3] = pose.to_transformation_matrix()[:3, :3]
    mat[:3, 3] = np.asarray(pose.p, dtype=np.float64)
    return mat


def invert_transform(mat: np.ndarray) -> np.ndarray:
    inv = np.eye(4, dtype=np.float64)
    inv[:3, :3] = mat[:3, :3].T
    inv[:3, 3] = -inv[:3, :3] @ mat[:3, 3]
    return inv


def rot_y_matrix(deg: float) -> np.ndarray:
    mat = np.eye(4, dtype=np.float64)
    mat[:3, :3] = Rotation.from_euler("y", deg, degrees=True).as_matrix()
    return mat


def apex_pick_contact_pose(pick) -> np.ndarray:
    """APEX-MR-style tool frame at the LEGO pick contact point.

    The working/tool-wall side points along local +X, matching the brick
    outward normal. The local +Z axis follows the RM75 LEGO TCP press
    direction, which points down in the world frame at the current home pose.
    """
    z_axis = np.array([0.0, 0.0, -1.0], dtype=np.float64)
    x_axis = np.asarray(pick.outward_normal, dtype=np.float64)
    x_axis = x_axis / np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    y_axis = y_axis / np.linalg.norm(y_axis)

    pose = np.eye(4, dtype=np.float64)
    pose[:3, 0] = x_axis
    pose[:3, 1] = y_axis
    pose[:3, 2] = z_axis
    pose[:3, 3] = pick.contact_point
    return pose


def tcp_pose_from_contact(contact_pose: np.ndarray, contact_offset_tcp) -> sapien.Pose:
    tcp_t_contact = translation_matrix(contact_offset_tcp)
    tcp_pose = contact_pose @ invert_transform(tcp_t_contact)
    return matrix_to_sapien_pose(tcp_pose)


def shifted_pose(mat: np.ndarray, shift) -> np.ndarray:
    out = mat.copy()
    out[:3, 3] = out[:3, 3] + np.asarray(shift, dtype=np.float64)
    return out


def build_sphere(scene, name: str, radius: float, color, pose: sapien.Pose):
    builder = scene.create_actor_builder()
    builder.add_sphere_visual(
        radius=radius,
        material=sapien.render.RenderMaterial(base_color=color),
    )
    builder.set_initial_pose(pose)
    return builder.build_kinematic(name=name)


def build_axis(scene, name: str, axis: str, length: float, thickness: float, color):
    builder = scene.create_actor_builder()
    material = sapien.render.RenderMaterial(base_color=color)
    if axis == "x":
        pose = sapien.Pose(p=[length / 2.0, 0.0, 0.0])
        half_size = [length / 2.0, thickness, thickness]
    elif axis == "y":
        pose = sapien.Pose(p=[0.0, length / 2.0, 0.0])
        half_size = [thickness, length / 2.0, thickness]
    elif axis == "z":
        pose = sapien.Pose(p=[0.0, 0.0, length / 2.0])
        half_size = [thickness, thickness, length / 2.0]
    else:
        raise ValueError(axis)
    builder.add_box_visual(pose=pose, half_size=half_size, material=material)
    builder.set_initial_pose(sapien.Pose())
    return builder.build_kinematic(name=name)


def build_vector_marker(scene, name: str, origin, vector, length: float, thickness: float, color):
    vector = np.asarray(vector, dtype=np.float64)
    vector = vector / np.linalg.norm(vector)
    rot = Rotation.align_vectors([vector], [[1.0, 0.0, 0.0]])[0].as_matrix()
    pose_mat = np.eye(4, dtype=np.float64)
    pose_mat[:3, :3] = rot
    pose_mat[:3, 3] = np.asarray(origin, dtype=np.float64)
    return build_axis(scene, name, "x", length, thickness, color), matrix_to_sapien_pose(pose_mat)


def build_frame_markers(scene, prefix: str, axis_length: float = 0.035, thickness: float = 0.0012):
    return {
        f"{prefix}_x": build_axis(scene, f"{prefix}_axis_x", "x", axis_length, thickness, [1.0, 0.0, 0.0, 0.85]),
        f"{prefix}_y": build_axis(scene, f"{prefix}_axis_y", "y", axis_length, thickness, [0.0, 1.0, 0.0, 0.85]),
        f"{prefix}_z": build_axis(scene, f"{prefix}_axis_z", "z", axis_length, thickness, [0.0, 0.2, 1.0, 0.85]),
    }


def set_frame(markers, prefix: str, pose: sapien.Pose):
    markers[f"{prefix}_x"].set_pose(pose)
    markers[f"{prefix}_y"].set_pose(pose)
    markers[f"{prefix}_z"].set_pose(pose)


def parse_args(
    default_brick_key: str = "lego_2x4",
    default_press_side: int = 1,
    default_press_offset: int = 0,
):
    parser = argparse.ArgumentParser()
    parser.add_argument("--brick-key", default=default_brick_key)
    parser.add_argument("--press-side", type=int, default=default_press_side)
    parser.add_argument("--press-offset", type=int, default=default_press_offset)
    parser.add_argument("--contact-offset", type=float, nargs=3, default=CONTACT_OFFSET_TCP)
    parser.add_argument("--pre-height", type=float, default=0.06)
    parser.add_argument("--press-depth", type=float, default=0.005)
    parser.add_argument("--twist-up-height", type=float, default=0.015)
    parser.add_argument("--pick-twist-deg", type=float, default=-APEX_TWIST_DEG)
    parser.add_argument("--tcp-orientation", choices=["apex", "home", "legacy-contact"], default="apex")
    parser.add_argument("--ik-mode", choices=["regularized", "pinocchio"], default="regularized")
    parser.add_argument("--ik-regularization", type=float, default=0.18)
    parser.add_argument("--no-ik-fallback", action="store_true")
    parser.add_argument(
        "--use-stage2-placement",
        action="store_true",
        help="Use the original flat stage2 placement instead of stacking the default 2x4 on another brick.",
    )
    parser.add_argument("--steps-per-segment", type=int, default=80)
    parser.add_argument("--twist-ik-steps", type=int, default=14)
    parser.add_argument("--hold-steps", type=int, default=30)
    parser.add_argument("--marker-scale", type=float, default=1.35)
    parser.add_argument("--show-tcp-frames", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--wait-at-end", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main(
    default_brick_key: str = "lego_2x4",
    default_press_side: int = 1,
    default_press_offset: int = 0,
) -> int:
    args = parse_args(
        default_brick_key=default_brick_key,
        default_press_side=default_press_side,
        default_press_offset=default_press_offset,
    )

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
    support_key = None
    if args.brick_key == "lego_2x4" and not args.use_stage2_placement:
        placement = replace(placement, grid=STACKED_2X4_GRID)
        support_key = STACKED_2X4_SUPPORT_KEY
        base_env.bricks[placement.key].set_pose(brick_pose_for_placement(placement))

    pick = pick_target_from_press_side(
        plate_top_pos=PLATE_TOP_POS,
        plate_size_xy=PLATE_SIZE_XY,
        brick=placement.brick,
        grid=placement.grid,
        press_side=args.press_side,
        press_offset=args.press_offset,
        plate_yaw=PLATE_YAW,
    )

    pin_model = base_env.agent.robot.create_pinocchio_model()
    tcp_link_index = int(as_numpy(base_env.agent.tcp.index).reshape(-1)[0])
    q_home = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float64)
    pin_model.compute_forward_kinematics(q_home)
    home_tcp_pose = pin_model.get_link_pose(tcp_link_index)
    home_tcp_rot = pose_to_matrix(home_tcp_pose)[:3, :3]
    apex_contact_pose = apex_pick_contact_pose(pick)

    def with_tcp_orientation(contact_pose: np.ndarray, mode: str) -> np.ndarray:
        if mode == "apex":
            out = contact_pose.copy()
            out[:3, :3] = apex_contact_pose[:3, :3]
            return out
        if mode == "legacy-contact":
            return contact_pose
        out = contact_pose.copy()
        out[:3, :3] = home_tcp_rot
        return out

    contact_offset = np.asarray(args.contact_offset, dtype=np.float64)

    def contact_waypoint_poses() -> dict[str, np.ndarray]:
        pre_contact = apex_contact_pose @ translation_matrix([0.0, 0.0, -args.pre_height])
        down_contact = apex_contact_pose @ translation_matrix([0.0, 0.0, args.press_depth])
        twist_contact = down_contact @ rot_y_matrix(args.pick_twist_deg)
        twist_up_contact = shifted_pose(
            twist_contact,
            np.array([0.0, 0.0, args.twist_up_height], dtype=np.float64),
        )
        return {
            "pre_pick_contact": pre_contact,
            "pick_down_contact": down_contact,
            "pick_twist_contact": twist_contact,
            "pick_twist_up_contact": twist_up_contact,
        }

    contact_poses = contact_waypoint_poses()
    twist_visual_pose = shifted_pose(
        contact_poses["pick_twist_contact"],
        pick.outward_normal * 0.018 + np.array([0.0, 0.0, 0.006]),
    )

    def target_poses_for_mode(mode: str) -> dict[str, sapien.Pose]:
        pre_contact = with_tcp_orientation(
            contact_poses["pre_pick_contact"],
            mode,
        )
        down_contact = with_tcp_orientation(
            contact_poses["pick_down_contact"],
            mode,
        )
        twist_contact = down_contact @ rot_y_matrix(args.pick_twist_deg)
        twist_up_contact = shifted_pose(
            twist_contact,
            np.array([0.0, 0.0, args.twist_up_height], dtype=np.float64),
        )
        return {
            "pre_pick": tcp_pose_from_contact(pre_contact, contact_offset),
            "pick_down": tcp_pose_from_contact(down_contact, contact_offset),
            "pick_twist": tcp_pose_from_contact(twist_contact, contact_offset),
            "pick_twist_up": tcp_pose_from_contact(twist_up_contact, contact_offset),
        }

    target_tcp_poses = target_poses_for_mode(args.tcp_orientation)

    def twist_tcp_pose_for_mode(mode: str, twist_deg: float, up_height: float = 0.0) -> sapien.Pose:
        down_contact = with_tcp_orientation(
            contact_poses["pick_down_contact"],
            mode,
        )
        twist_contact = down_contact @ rot_y_matrix(twist_deg)
        if up_height:
            twist_contact = shifted_pose(
                twist_contact,
                np.array([0.0, 0.0, up_height], dtype=np.float64),
            )
        return tcp_pose_from_contact(twist_contact, contact_offset)

    markers = {}
    marker_scale = float(args.marker_scale)
    for idx, p in enumerate(pick.selected_stud_centers):
        markers[f"stud_{idx}"] = build_sphere(
            base_env.scene,
            f"stage4_selected_stud_{idx}",
            0.003 * marker_scale,
            [0.1, 0.35, 1.0, 0.95],
            sapien.Pose(p=p.tolist()),
        )
    markers["pair_center"] = build_sphere(
        base_env.scene,
        "stage4_stud_pair_center",
        0.0025 * marker_scale,
        [1.0, 0.85, 0.05, 0.95],
        sapien.Pose(p=pick.stud_pair_center.tolist()),
    )
    markers["pick_target"] = build_sphere(
        base_env.scene,
        "stage4_pick_contact_target",
        0.003 * marker_scale,
        [1.0, 0.05, 0.05, 0.95],
        sapien.Pose(p=pick.contact_point.tolist()),
    )
    outward_actor, outward_pose = build_vector_marker(
        base_env.scene,
        "stage4_outward_normal_arrow",
        pick.contact_point + np.array([0.0, 0.0, 0.004]),
        pick.outward_normal,
        0.055 * marker_scale,
        0.0016 * marker_scale,
        [0.0, 1.0, 0.0, 0.85],
    )
    markers["outward_normal"] = outward_actor
    markers["outward_normal"].set_pose(outward_pose)
    tool_wall_direction = apex_contact_pose[:3, 0]
    wall_actor, wall_pose = build_vector_marker(
        base_env.scene,
        "stage4_tool_wall_side_arrow",
        pick.contact_point + np.array([0.0, 0.0, 0.010]),
        tool_wall_direction,
        0.045 * marker_scale,
        0.0020 * marker_scale,
        [0.75, 0.05, 1.0, 0.9],
    )
    markers["tool_wall_direction"] = wall_actor
    markers["tool_wall_direction"].set_pose(wall_pose)

    frame_markers = {}
    for prefix in ["pre_contact", "down_contact", "twist_contact", "twist_up_contact"]:
        frame_markers.update(build_frame_markers(
            base_env.scene,
            f"stage4_{prefix}",
            axis_length=0.035 * marker_scale,
            thickness=0.0012 * marker_scale,
        ))
    set_frame(frame_markers, "stage4_pre_contact", matrix_to_sapien_pose(contact_poses["pre_pick_contact"]))
    set_frame(frame_markers, "stage4_down_contact", matrix_to_sapien_pose(contact_poses["pick_down_contact"]))
    set_frame(frame_markers, "stage4_twist_contact", matrix_to_sapien_pose(twist_visual_pose))
    set_frame(frame_markers, "stage4_twist_up_contact", matrix_to_sapien_pose(contact_poses["pick_twist_up_contact"]))
    if args.show_tcp_frames:
        for prefix in ["tcp_down", "tcp_pre", "tcp_twist", "tcp_twist_up"]:
            frame_markers.update(build_frame_markers(
                base_env.scene,
                f"stage4_{prefix}",
                axis_length=0.024 * marker_scale,
                thickness=0.0008 * marker_scale,
            ))
        set_frame(frame_markers, "stage4_tcp_down", target_tcp_poses["pick_down"])
        set_frame(frame_markers, "stage4_tcp_pre", target_tcp_poses["pre_pick"])
        set_frame(frame_markers, "stage4_tcp_twist", target_tcp_poses["pick_twist"])
        set_frame(frame_markers, "stage4_tcp_twist_up", target_tcp_poses["pick_twist_up"])

    def solve_one_pinocchio(name: str, target_pose: sapien.Pose, q_seed: np.ndarray):
        q_sol, success, err = pin_model.compute_inverse_kinematics(
            tcp_link_index,
            target_pose,
            initial_qpos=q_seed,
            eps=1e-4,
            max_iterations=2000,
            dt=0.1,
            damp=1e-6,
        )
        q_sol = np.asarray(q_sol, dtype=np.float64)
        err = np.asarray(err, dtype=np.float64)
        return q_sol, bool(success), err

    def solve_one_regularized(name: str, target_pose: sapien.Pose, q_seed: np.ndarray):
        target_mat = pose_to_matrix(target_pose)
        q_seed = np.asarray(q_seed, dtype=np.float64)

        def residual(q):
            pin_model.compute_forward_kinematics(q)
            cur_mat = pose_to_matrix(pin_model.get_link_pose(tcp_link_index))
            pos_err = target_mat[:3, 3] - cur_mat[:3, 3]
            rot_err = Rotation.from_matrix(target_mat[:3, :3] @ cur_mat[:3, :3].T).as_rotvec()
            reg_err = q - q_seed
            return np.concatenate([pos_err * 80.0, rot_err * 1.4, reg_err * args.ik_regularization])

        result = least_squares(
            residual,
            np.clip(q_seed, JOINT_LOWER, JOINT_UPPER),
            bounds=(JOINT_LOWER, JOINT_UPPER),
            max_nfev=220,
            xtol=1e-10,
            ftol=1e-10,
            gtol=1e-10,
        )
        q_sol = np.asarray(result.x, dtype=np.float64)
        pin_model.compute_forward_kinematics(q_sol)
        cur_mat = pose_to_matrix(pin_model.get_link_pose(tcp_link_index))
        pos_err = target_mat[:3, 3] - cur_mat[:3, 3]
        rot_err = Rotation.from_matrix(target_mat[:3, :3] @ cur_mat[:3, :3].T).as_rotvec()
        err = np.concatenate([pos_err, rot_err])
        success = bool(result.success and np.linalg.norm(pos_err) < 2.0e-4 and np.linalg.norm(rot_err) < 2.0e-3)
        return q_sol, success, err

    def solve_one(name: str, target_pose: sapien.Pose, q_seed: np.ndarray):
        if args.ik_mode == "pinocchio":
            return solve_one_pinocchio(name, target_pose, q_seed)
        q_sol, success, err = solve_one_regularized(name, target_pose, q_seed)
        if success:
            return q_sol, success, err
        return solve_one_pinocchio(name, target_pose, q_seed)

    def solve_targets(poses: dict[str, sapien.Pose], mode: str):
        q_seed = q_home.copy()
        q_targets_out = {}
        ik_success_out = {}
        ik_errors_out = {}
        q_paths_out = {}

        for name in ["pre_pick", "pick_down"]:
            q_sol, success, err = solve_one(name, poses[name], q_seed)
            q_targets_out[name] = q_sol.astype(np.float32)
            ik_success_out[name] = success
            ik_errors_out[name] = err
            q_seed = q_sol

        twist_steps = max(1, int(args.twist_ik_steps))
        twist_path = []
        twist_success = True
        twist_err = np.zeros(6, dtype=np.float64)
        for deg in np.linspace(0.0, args.pick_twist_deg, twist_steps + 1)[1:]:
            q_sol, success, err = solve_one(
                "pick_twist",
                twist_tcp_pose_for_mode(mode, float(deg)),
                q_seed,
            )
            twist_path.append(q_sol.astype(np.float32))
            twist_success &= success
            twist_err = err
            q_seed = q_sol
        q_targets_out["pick_twist"] = twist_path[-1]
        q_paths_out["pick_twist"] = twist_path
        ik_success_out["pick_twist"] = twist_success
        ik_errors_out["pick_twist"] = twist_err

        q_sol, success, err = solve_one(
            "pick_twist_up",
            twist_tcp_pose_for_mode(mode, args.pick_twist_deg, args.twist_up_height),
            q_seed,
        )
        q_targets_out["pick_twist_up"] = q_sol.astype(np.float32)
        ik_success_out["pick_twist_up"] = success
        ik_errors_out["pick_twist_up"] = err
        q_seed = q_sol

        return q_targets_out, ik_success_out, ik_errors_out, q_paths_out

    executed_orientation = args.tcp_orientation
    q_targets, ik_success, ik_errors, q_paths = solve_targets(target_tcp_poses, executed_orientation)
    if not all(ik_success.values()) and args.tcp_orientation == "apex" and not args.no_ik_fallback:
        print("WARN: strict APEX TCP orientation IK failed; falling back to home TCP orientation for motion.")
        executed_orientation = "home"
        target_tcp_poses = target_poses_for_mode(executed_orientation)
        q_targets, ik_success, ik_errors, q_paths = solve_targets(target_tcp_poses, executed_orientation)

    if args.show_tcp_frames:
        set_frame(frame_markers, "stage4_tcp_down", target_tcp_poses["pick_down"])
        set_frame(frame_markers, "stage4_tcp_pre", target_tcp_poses["pre_pick"])
        set_frame(frame_markers, "stage4_tcp_twist", target_tcp_poses["pick_twist"])
        set_frame(frame_markers, "stage4_tcp_twist_up", target_tcp_poses["pick_twist_up"])

    print("stage4 brick:", args.brick_key)
    print("brick grid[x,y,z,ori]:", [placement.grid.x, placement.grid.y, placement.grid.z, placement.grid.ori])
    if support_key is not None:
        support = stage2_placement_by_key(support_key)
        print("stacked on:", support_key, "grid[x,y,z,ori]:", [support.grid.x, support.grid.y, support.grid.z, support.grid.ori])
    print("press_side/press_offset:", args.press_side, args.press_offset)
    print("contact_offset_tcp:", contact_offset.tolist())
    print("tcp_orientation:", args.tcp_orientation)
    print("executed_tcp_orientation:", executed_orientation)
    print("ik_mode:", args.ik_mode)
    print("selected stud centers:", np.round(pick.selected_stud_centers, 6).tolist())
    print("stud pair center:", np.round(pick.stud_pair_center, 6).tolist())
    print("pick contact target:", np.round(pick.contact_point, 6).tolist())
    print("outward normal:", np.round(pick.outward_normal, 6).tolist())
    print("tangent:", np.round(pick.tangent, 6).tolist())
    print("APEX contact frame x axis:", np.round(apex_contact_pose[:3, 0], 6).tolist())
    print("APEX contact frame y axis:", np.round(apex_contact_pose[:3, 1], 6).tolist())
    print("APEX contact frame z axis / press direction:", np.round(apex_contact_pose[:3, 2], 6).tolist())
    print("home tcp x axis:", np.round(home_tcp_rot[:, 0], 6).tolist())
    print("home tcp y axis:", np.round(home_tcp_rot[:, 1], 6).tolist())
    print("home tcp z axis:", np.round(home_tcp_rot[:, 2], 6).tolist())
    print("tool wall side direction (+APEX x):", np.round(tool_wall_direction, 6).tolist())
    print("wall/outward alignment dot:", float(np.dot(tool_wall_direction, pick.outward_normal)))
    print("contact_z/home_tcp_z dot:", float(np.dot(apex_contact_pose[:3, 2], home_tcp_rot[:, 2])))
    print("twist_ik_steps:", int(args.twist_ik_steps))
    print("pre_pick contact p:", np.round(contact_poses["pre_pick_contact"][:3, 3], 6).tolist())
    print("pick_down contact p:", np.round(contact_poses["pick_down_contact"][:3, 3], 6).tolist())
    print("pick_twist contact p:", np.round(contact_poses["pick_twist_contact"][:3, 3], 6).tolist())
    print("pick_twist_up contact p:", np.round(contact_poses["pick_twist_up_contact"][:3, 3], 6).tolist())
    for name in ["pre_pick", "pick_down", "pick_twist", "pick_twist_up"]:
        print(name, "tcp target p:", np.round(np.asarray(target_tcp_poses[name].p), 6).tolist())
        print(name, "ik success:", ik_success[name], "err:", np.round(ik_errors[name], 6).tolist())
        print(name, "q:", np.round(q_targets[name], 5).tolist())
    if "pick_twist" in q_paths and q_paths["pick_twist"]:
        q_down = q_targets["pick_down"].astype(np.float64)
        q_twist = q_targets["pick_twist"].astype(np.float64)
        print("pick_down->pick_twist q delta:", np.round(q_twist - q_down, 5).tolist())

    if not all(ik_success.values()):
        env.close()
        raise RuntimeError(f"IK failed: {ik_success}")

    def step_to(q_target, steps, tag):
        q_start = as_numpy(base_env.agent.robot.get_qpos()).reshape(-1)
        print(f"[move] {tag}")
        for alpha in np.linspace(0.0, 1.0, max(1, steps)):
            q = (1.0 - alpha) * q_start + alpha * q_target
            env.step(q.astype(np.float32))
            base_env.update_markers()
            if args.render:
                env.render()
                if args.render_sleep > 0:
                    time.sleep(args.render_sleep)

    def hold(steps, tag):
        print(f"[hold] {tag}")
        q = as_numpy(base_env.agent.robot.get_qpos()).reshape(-1).astype(np.float32)
        for _ in range(steps):
            env.step(q)
            base_env.update_markers()
            if args.render:
                env.render()
                if args.render_sleep > 0:
                    time.sleep(args.render_sleep)

    step_to(RM75LegoTool.keyframes["neutral"].qpos.astype(np.float32), args.hold_steps, "home")
    step_to(q_targets["pre_pick"], args.steps_per_segment, "pre_pick")
    step_to(q_targets["pick_down"], args.steps_per_segment, "pick_down")
    for idx, q_twist in enumerate(q_paths.get("pick_twist", [q_targets["pick_twist"]]), start=1):
        step_to(q_twist, max(2, args.steps_per_segment // max(1, int(args.twist_ik_steps))), f"pick_twist_{idx:02d}")
    hold(args.hold_steps, "twist_hold")
    step_to(q_targets["pick_twist_up"], args.steps_per_segment, "pick_twist_up")

    actual_tcp = pose_pos_np(base_env.agent.tcp.pose)
    print("final tcp p:", np.round(actual_tcp, 6).tolist())
    print(f"PASS: stage4 pick geometry and IK motion for {args.brick_key}")
    if args.wait_at_end:
        input("Press Enter to close the ManiSkill viewer...")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
