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
from maniskill_rm75_lego.agents.rm75_lego_tool import ARM_JOINT_NAMES, RM75LegoTool


def as_numpy(x):
    if torch.is_tensor(x):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--wait-at-end", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = gym.make(
        "RM75LegoSmoke-v1",
        obs_mode="none",
        reward_mode="none",
        control_mode="pd_joint_pos",
        render_mode="human" if args.render else "rgb_array",
        num_envs=1,
    )
    env.reset(seed=args.seed)
    base_env = env.unwrapped
    robot = base_env.agent.robot

    active_joint_names = [joint.name for joint in robot.get_active_joints()]
    link_names = [link.name for link in robot.get_links()]
    qpos0 = as_numpy(robot.get_qpos()).reshape(-1)
    qvel0 = as_numpy(robot.get_qvel()).reshape(-1)
    neutral = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float32)

    print("URDF:", RM75LegoTool.urdf_path)
    print("active joints:", active_joint_names)
    print("link count:", len(link_names))
    print("has lego_tool_link:", "lego_tool_link" in link_names)
    print("has lego_tool_tcp:", "lego_tool_tcp" in link_names)
    print("initial qpos:", np.round(qpos0, 6).tolist())
    print("initial qvel max abs:", float(np.max(np.abs(qvel0))))
    print("tcp pose p:", np.round(as_numpy(base_env.agent.tcp.pose.p).reshape(-1), 6).tolist())

    if active_joint_names != ARM_JOINT_NAMES:
        raise RuntimeError(
            f"Unexpected active joints: {active_joint_names}; expected {ARM_JOINT_NAMES}"
        )
    if "lego_tool_tcp" not in link_names:
        raise RuntimeError("lego_tool_tcp link was not loaded")

    action = neutral
    for _ in range(args.steps):
        obs, reward, terminated, truncated, info = env.step(action)
        base_env.update_markers()
        if args.render:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)

    qpos1 = as_numpy(robot.get_qpos()).reshape(-1)
    qvel1 = as_numpy(robot.get_qvel()).reshape(-1)
    max_qpos_err = float(np.max(np.abs(qpos1 - neutral)))
    max_qvel = float(np.max(np.abs(qvel1)))
    tcp_p = as_numpy(base_env.agent.tcp.pose.p).reshape(-1)

    print("final qpos:", np.round(qpos1, 6).tolist())
    print("final max qpos error from neutral:", max_qpos_err)
    print("final max qvel:", max_qvel)
    print("final tcp pose p:", np.round(tcp_p, 6).tolist())
    print("PASS: RM75 LEGO tool loads and holds neutral under pd_joint_pos")
    if args.wait_at_end:
        input("Press Enter to close the ManiSkill viewer...")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
