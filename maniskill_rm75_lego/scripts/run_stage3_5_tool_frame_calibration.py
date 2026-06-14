#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
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
import torch
from scipy.spatial.transform import Rotation

from mani_skill.utils.structs.pose import Pose

import maniskill_rm75_lego.envs  # noqa: F401
from maniskill_rm75_lego.agents.rm75_lego_tool import RM75LegoTool
from maniskill_rm75_lego.envs.rm75_lego_smoke import CONTACT_OFFSET_TCP


AXIS_TO_VEC = {
    "x": np.array([1.0, 0.0, 0.0], dtype=np.float32),
    "y": np.array([0.0, 1.0, 0.0], dtype=np.float32),
    "z": np.array([0.0, 0.0, 1.0], dtype=np.float32),
}


def as_numpy(x):
    if torch.is_tensor(x):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def pose_pos_np(pose) -> np.ndarray:
    return as_numpy(pose.p).reshape(-1)[:3]


def wxyz_from_rotvec(rotvec: np.ndarray) -> np.ndarray:
    xyzw = Rotation.from_rotvec(rotvec).as_quat()
    return np.array([xyzw[3], xyzw[0], xyzw[1], xyzw[2]], dtype=np.float32)


def pose_from_local(local_p, local_q=None) -> Pose:
    if local_q is None:
        return Pose.create_from_pq(np.asarray(local_p, dtype=np.float32))
    return Pose.create_from_pq(
        np.asarray(local_p, dtype=np.float32), np.asarray(local_q, dtype=np.float32)
    )


def build_sphere(scene, name, radius, color):
    builder = scene.create_actor_builder()
    builder.set_initial_pose(sapien.Pose())
    builder.add_sphere_visual(
        radius=radius,
        material=sapien.render.RenderMaterial(base_color=color),
    )
    return builder.build_kinematic(name=name)


def build_axis_marker(scene, name, axis: str, length: float, thickness: float, color):
    return build_signed_axis_marker(scene, name, axis, length, thickness, color)


def build_signed_axis_marker(scene, name, axis: str, signed_length: float, thickness: float, color):
    builder = scene.create_actor_builder()
    builder.set_initial_pose(sapien.Pose())
    length = abs(signed_length)
    center = signed_length / 2.0
    if axis == "x":
        half_size = [length / 2.0, thickness, thickness]
        pose = sapien.Pose(p=[center, 0, 0])
    elif axis == "y":
        half_size = [thickness, length / 2.0, thickness]
        pose = sapien.Pose(p=[0, center, 0])
    elif axis == "z":
        half_size = [thickness, thickness, length / 2.0]
        pose = sapien.Pose(p=[0, 0, center])
    else:
        raise ValueError(axis)
    builder.add_box_visual(
        pose=pose,
        half_size=half_size,
        material=sapien.render.RenderMaterial(base_color=color),
    )
    return builder.build_kinematic(name=name)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contact-offset", type=float, nargs=3, default=CONTACT_OFFSET_TCP)
    parser.add_argument("--side-axis", choices=["x", "y", "z"], default="x")
    parser.add_argument("--side-sign", type=float, choices=[-1.0, 1.0], default=1.0)
    parser.add_argument("--side-distance", type=float, default=0.018)
    parser.add_argument("--press-axis", choices=["x", "y", "z"], default="z")
    parser.add_argument("--press-sign", type=float, choices=[-1.0, 1.0], default=1.0)
    parser.add_argument("--press-depth", type=float, default=0.005)
    parser.add_argument("--press-visual-length", type=float, default=0.06)
    parser.add_argument("--show-press-end", action="store_true")
    parser.add_argument("--twist-axis", choices=["x", "y", "z"], default="y")
    parser.add_argument("--pick-twist-deg", type=float, default=-14.0)
    parser.add_argument("--place-twist-deg", type=float, default=14.0)
    parser.add_argument("--twist-visual-length", type=float, default=0.04)
    parser.add_argument("--marker-radius", type=float, default=0.0015)
    parser.add_argument("--axis-length", type=float, default=0.045)
    parser.add_argument("--steps", type=int, default=100000)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--wait-at-end", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
    base_env.contact_offset_tcp = np.asarray(args.contact_offset, dtype=np.float32)

    markers = {
        "stud_side": build_sphere(base_env.scene, "calib_stud_side_yellow", args.marker_radius * 1.4, [1.0, 0.85, 0.05, 0.95]),
        "empty_side": build_sphere(base_env.scene, "calib_empty_side_purple", args.marker_radius * 1.4, [0.65, 0.1, 1.0, 0.95]),
        "press_rod": build_signed_axis_marker(base_env.scene, "calib_press_rod", args.press_axis, args.press_sign * args.press_visual_length, 0.0028, [1.0, 0.45, 0.05, 0.9]),
        "pick_twist": build_signed_axis_marker(base_env.scene, "calib_pick_twist_ghost_rod", args.side_axis, args.side_sign * args.twist_visual_length, 0.0028, [1.0, 0.55, 0.05, 0.85]),
        "place_twist": build_signed_axis_marker(base_env.scene, "calib_place_twist_ghost_rod", args.side_axis, args.side_sign * args.twist_visual_length, 0.0028, [0.05, 0.9, 1.0, 0.85]),
        "axis_x": build_axis_marker(base_env.scene, "calib_contact_axis_x", "x", args.axis_length, 0.0015, [1.0, 0.0, 0.0, 0.9]),
        "axis_y": build_axis_marker(base_env.scene, "calib_contact_axis_y", "y", args.axis_length, 0.0015, [0.0, 1.0, 0.0, 0.9]),
        "axis_z": build_axis_marker(base_env.scene, "calib_contact_axis_z", "z", args.axis_length, 0.0015, [0.0, 0.2, 1.0, 0.9]),
    }
    if args.show_press_end:
        markers["press_end"] = build_sphere(
            base_env.scene,
            "calib_press_end_orange",
            args.marker_radius * 1.6,
            [1.0, 0.45, 0.05, 0.95],
        )

    q_home = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float32)
    side_vec = AXIS_TO_VEC[args.side_axis] * args.side_sign * args.side_distance
    press_vec = AXIS_TO_VEC[args.press_axis] * args.press_sign * args.press_depth
    twist_axis_vec = AXIS_TO_VEC[args.twist_axis]

    def update_markers():
        env.step(q_home)
        base_env.update_markers()

        tcp_pose = base_env.agent.tcp.pose
        contact_pose = tcp_pose * pose_from_local(args.contact_offset)
        stud_side_pose = contact_pose * pose_from_local(side_vec)
        empty_side_pose = contact_pose * pose_from_local(-side_vec)
        press_end_pose = contact_pose * pose_from_local(press_vec)

        pick_q = wxyz_from_rotvec(
            twist_axis_vec * np.float32(np.deg2rad(args.pick_twist_deg))
        )
        place_q = wxyz_from_rotvec(
            twist_axis_vec * np.float32(np.deg2rad(args.place_twist_deg))
        )
        pick_twist_pose = contact_pose * pose_from_local([0.0, 0.0, 0.0], pick_q)
        place_twist_pose = contact_pose * pose_from_local([0.0, 0.0, 0.0], place_q)

        markers["stud_side"].set_pose(stud_side_pose)
        markers["empty_side"].set_pose(empty_side_pose)
        if args.show_press_end:
            markers["press_end"].set_pose(press_end_pose)
        markers["press_rod"].set_pose(contact_pose)
        markers["pick_twist"].set_pose(pick_twist_pose)
        markers["place_twist"].set_pose(place_twist_pose)
        markers["axis_x"].set_pose(contact_pose)
        markers["axis_y"].set_pose(contact_pose)
        markers["axis_z"].set_pose(contact_pose)
        positions = {
            "tcp": pose_pos_np(tcp_pose),
            "contact": pose_pos_np(contact_pose),
            "stud_side": pose_pos_np(stud_side_pose),
            "empty_side": pose_pos_np(empty_side_pose),
            "brick": pose_pos_np(base_env.brick.pose),
            "target": pose_pos_np(base_env.goal_marker.pose),
        }
        if args.show_press_end:
            positions["press_end"] = pose_pos_np(press_end_pose)
        return positions

    positions = update_markers()
    print("contact_offset_tcp:", args.contact_offset)
    print("side_axis/sign/distance:", args.side_axis, args.side_sign, args.side_distance)
    print("press_axis/sign/depth/visual_length:", args.press_axis, args.press_sign, args.press_depth, args.press_visual_length)
    print("twist_axis pick/place deg visual_length:", args.twist_axis, args.pick_twist_deg, args.place_twist_deg, args.twist_visual_length)
    for name, pos in positions.items():
        print(f"{name} p:", np.round(pos, 6).tolist())
    print("colors:")
    print("  blue sphere   = lego_tool_tcp_marker from env")
    print("  red sphere    = lego_tool_contact_marker from env")
    print("  yellow sphere = stud/pillar side")
    print("  purple sphere = empty side")
    print("  orange sphere = optional press end, only with --show-press-end")
    print("  orange rod    = enlarged press direction")
    print("  red/green/blue rods = contact X/Y/Z axes")
    print("  orange/cyan rods = pick/place twist ghost stud-side direction")

    for _ in range(args.steps):
        update_markers()
        if args.render:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)

    if args.wait_at_end:
        input("Press Enter to close the ManiSkill viewer...")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
