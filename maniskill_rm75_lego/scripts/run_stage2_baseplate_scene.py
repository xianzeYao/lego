#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import gymnasium as gym
import numpy as np
import torch
import time

import maniskill_rm75_lego.envs  # noqa: F401
from maniskill_rm75_lego.agents.rm75_lego_tool import RM75LegoTool
from maniskill_rm75_lego.envs.rm75_lego_pick_place import (
    BASEPLATE32_MESH_PATH,
    BRICK_INITIAL_POS,
    BRICK_MESH_BOUNDS_MAX,
    BRICK_MESH_BOUNDS_MIN,
    BRICK_MESH_SIZE,
    BRICK_URDF_ORIGIN_Z_ON_GROUND,
    LEGO_1X4_URDF_PATH,
    LEGO_1X2_URDF_PATH,
    LEGO_2X4_URDF_PATH,
    LEGO_BASEPLATE32_URDF_PATH,
    LEGO_BRICK_URDF_PATHS,
    PLATE_ORIGIN_POS,
    PLATE_SIZE_XY,
    PLATE_TOP_POS,
    STAGE2_BRICK_PLACEMENTS,
    STUD_DIAMETER,
    STUD_MARKER_HEIGHT,
    TARGET_POS,
    describe_plate_grid_points,
    describe_stage2_placements,
    grid_origin_axis_pose,
)


def as_numpy(x):
    if torch.is_tensor(x):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=20)
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

    print("baseplate urdf:", str(LEGO_BASEPLATE32_URDF_PATH))
    print("baseplate mesh:", str(BASEPLATE32_MESH_PATH))
    print("legacy sample lego urdfs:", [str(LEGO_1X2_URDF_PATH), str(LEGO_1X4_URDF_PATH), str(LEGO_2X4_URDF_PATH)])
    print("all non-plate lego urdfs:")
    for key, path in LEGO_BRICK_URDF_PATHS.items():
        print(" ", key, str(path))
    print("plate size studs:", list(PLATE_SIZE_XY))
    print("plate mesh origin pos:", np.round(PLATE_ORIGIN_POS, 6).tolist())
    print("plate top/grid pos:", np.round(PLATE_TOP_POS, 6).tolist())
    print("plate grid (0,0) axis visual origin:", np.round(grid_origin_axis_pose().p, 6).tolist())
    print("plate grid (0,0) axis colors: +X red, +Y green, +Z blue")
    print("plate grid point examples:")
    for row in describe_plate_grid_points():
        print(" ", "grid[x,y,z]", row["grid"], "world xyz", np.round(row["world"], 6).tolist())
    print("brick mesh size incl studs:", BRICK_MESH_SIZE.tolist())
    print("brick mesh bounds min:", BRICK_MESH_BOUNDS_MIN.tolist())
    print("brick mesh bounds max:", BRICK_MESH_BOUNDS_MAX.tolist())
    print("brick actor origin z above brick bottom:", BRICK_URDF_ORIGIN_Z_ON_GROUND)
    print("blue stud marker diameter:", STUD_DIAMETER)
    print("blue stud marker height:", STUD_MARKER_HEIGHT)
    print("expected 1x2 brick initial pos:", BRICK_INITIAL_POS.tolist())
    print("expected 1x2 target pos:", TARGET_POS.tolist())
    print("stage2 grid placements:")
    for row in describe_stage2_placements():
        print(
            " ",
            row["key"],
            "studs",
            row["studs"],
            "grid[x,y,z,ori]",
            row["grid"],
            "bottom",
            np.round(row["bottom_pos"], 6).tolist(),
            "actor",
            np.round(row["actor_pos"], 6).tolist(),
            "press_side_1_offset_0",
            row["press_side_1_offset_0"],
        )
    print("actual baseplate pos:", np.round(as_numpy(base_env.baseplate.pose.p).reshape(-1), 6).tolist())
    for placement in STAGE2_BRICK_PLACEMENTS:
        actor = base_env.bricks[placement.key]
        print(
            f"actual {placement.key} pos:",
            np.round(as_numpy(actor.pose.p).reshape(-1), 6).tolist(),
        )
    print(
        "actual target pos:",
        np.round(as_numpy(base_env.goal_marker.pose.p).reshape(-1), 6).tolist(),
    )
    print(
        "tcp pos:",
        np.round(as_numpy(base_env.agent.tcp.pose.p).reshape(-1), 6).tolist(),
    )

    actual_plate = as_numpy(base_env.baseplate.pose.p).reshape(-1)[:3]
    if np.linalg.norm(actual_plate - PLATE_ORIGIN_POS) > 1e-5:
        raise RuntimeError(
            f"Baseplate pos={actual_plate.tolist()} does not match expected {PLATE_ORIGIN_POS.tolist()}"
        )
    for row, placement in zip(describe_stage2_placements(), STAGE2_BRICK_PLACEMENTS):
        actor_pos = as_numpy(base_env.bricks[placement.key].pose.p).reshape(-1)[:3]
        expected_pos = row["actor_pos"]
        if np.linalg.norm(actor_pos - expected_pos) > 1e-5:
            raise RuntimeError(
                f"{placement.key} pos={actor_pos.tolist()} does not match expected {expected_pos.tolist()}"
            )

    action = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float32)
    for _ in range(args.steps):
        env.step(action)
        base_env.update_markers()
        if args.render:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)

    brick_pos_after = as_numpy(base_env.brick.pose.p).reshape(-1)
    target_pos_after = as_numpy(base_env.goal_marker.pose.p).reshape(-1)
    print("final 1x2 brick pos:", np.round(brick_pos_after, 6).tolist())
    print("final target pos:", np.round(target_pos_after, 6).tolist())
    print("PASS: baseplate32 grid scene with all non-plate LEGO brick types initializes")
    if args.wait_at_end:
        input("Press Enter to close the ManiSkill viewer...")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
