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
import torch

from mani_skill.utils.structs.pose import Pose

import maniskill_rm75_lego.envs  # noqa: F401
from maniskill_rm75_lego.agents.rm75_lego_tool import RM75LegoTool
from maniskill_rm75_lego.envs.rm75_lego_pick_place import TARGET_POS


CONTACT_OFFSET_TCP = np.array([0.0, 0.0, -0.015], dtype=np.float32)


def as_numpy(x):
    if torch.is_tensor(x):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def pose_pos_np(pose) -> np.ndarray:
    return as_numpy(pose.p).reshape(-1)[:3]


def pos_error(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps-per-waypoint", type=int, default=40)
    parser.add_argument("--hold-steps", type=int, default=20)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--wait-at-end", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


class FakeAttachRunner:
    def __init__(self, env, args):
        self.env = env
        self.base_env = env.unwrapped
        self.args = args
        self.attached = False
        self.contact_T_brick = None
        self.max_attach_pos_err = 0.0

    def contact_pose(self):
        return self.base_env.agent.tcp.pose * Pose.create_from_pq(CONTACT_OFFSET_TCP)

    def update_attached_brick(self):
        if not self.attached:
            return
        expected = self.contact_pose() * self.contact_T_brick
        self.base_env.brick.set_pose(expected)
        actual_p = pose_pos_np(self.base_env.brick.pose)
        expected_p = pose_pos_np(expected)
        self.max_attach_pos_err = max(self.max_attach_pos_err, pos_error(actual_p, expected_p))

    def step(self, q_target):
        self.env.step(np.asarray(q_target, dtype=np.float32))
        self.base_env.update_markers()
        self.update_attached_brick()
        if self.args.render:
            self.env.render()
            if self.args.render_sleep > 0:
                time.sleep(self.args.render_sleep)

    def move_linear(self, q_target, steps, tag):
        q_start = as_numpy(self.base_env.agent.robot.get_qpos()).reshape(-1)
        q_target = np.asarray(q_target, dtype=np.float32).reshape(-1)
        print(f"[move] {tag}: {np.round(q_start, 4).tolist()} -> {np.round(q_target, 4).tolist()}")
        for alpha in np.linspace(0.0, 1.0, max(1, steps)):
            q = (1.0 - alpha) * q_start + alpha * q_target
            self.step(q)

    def hold(self, steps, tag):
        q = as_numpy(self.base_env.agent.robot.get_qpos()).reshape(-1)
        print(f"[hold] {tag}: {steps} steps")
        for _ in range(steps):
            self.step(q)

    def fake_attach(self):
        contact = self.contact_pose()
        self.contact_T_brick = contact.inv() * self.base_env.brick.pose
        self.attached = True
        self.update_attached_brick()
        print("[attach] recorded contact_T_brick")
        print("[attach] contact p:", np.round(pose_pos_np(contact), 6).tolist())
        print("[attach] brick p:", np.round(pose_pos_np(self.base_env.brick.pose), 6).tolist())

    def fake_release_at_target(self):
        target_pose = Pose.create_from_pq(
            torch.as_tensor(TARGET_POS, device=self.base_env.device, dtype=torch.float32).reshape(1, 3)
        )
        self.base_env.brick.set_pose(target_pose)
        self.attached = False
        print("[release] set brick to target pose")
        print("[release] brick p:", np.round(pose_pos_np(self.base_env.brick.pose), 6).tolist())


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
    runner = FakeAttachRunner(env, args)

    q_home = RM75LegoTool.keyframes["neutral"].qpos.astype(np.float32)
    q_pick = np.array([0.0, -0.55, 0.0, 1.05, 0.0, 0.55, 0.0], dtype=np.float32)
    q_lift = np.array([0.0, -0.35, 0.0, 0.75, 0.0, 0.85, 0.0], dtype=np.float32)
    q_transfer = np.array([0.45, -0.35, 0.2, 0.75, -0.2, 0.85, 0.35], dtype=np.float32)
    q_place = np.array([0.45, -0.55, 0.2, 1.05, -0.2, 0.55, 0.35], dtype=np.float32)

    initial_brick_p = pose_pos_np(runner.base_env.brick.pose)
    target_p = np.asarray(TARGET_POS, dtype=np.float64)
    print("initial brick p:", np.round(initial_brick_p, 6).tolist())
    print("target brick p:", np.round(target_p, 6).tolist())
    print("initial tcp p:", np.round(pose_pos_np(runner.base_env.agent.tcp.pose), 6).tolist())

    runner.move_linear(q_home, args.hold_steps, "home")
    runner.move_linear(q_pick, args.steps_per_waypoint, "pre_pick/contact")
    runner.fake_attach()
    runner.move_linear(q_lift, args.steps_per_waypoint, "lift")
    runner.move_linear(q_transfer, args.steps_per_waypoint, "transfer")
    runner.move_linear(q_place, args.steps_per_waypoint, "place/contact")
    runner.fake_release_at_target()
    runner.hold(args.hold_steps, "post_release")
    runner.move_linear(q_home, args.steps_per_waypoint, "retreat/home")

    final_brick_p = pose_pos_np(runner.base_env.brick.pose)
    final_target_err = pos_error(final_brick_p, target_p)
    print("final brick p:", np.round(final_brick_p, 6).tolist())
    print("final target position error:", final_target_err)
    print("max attached position error:", runner.max_attach_pos_err)

    if runner.max_attach_pos_err > 1e-6:
        raise RuntimeError(f"Attached brick drifted by {runner.max_attach_pos_err} m")
    if final_target_err > 1e-6:
        raise RuntimeError(f"Released brick target error is {final_target_err} m")

    print("PASS: fake attach/release pick-place logic keeps brick attached and releases at target")
    if args.wait_at_end:
        input("Press Enter to close the ManiSkill viewer...")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

