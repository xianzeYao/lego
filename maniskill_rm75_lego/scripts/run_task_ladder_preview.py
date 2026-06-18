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

import maniskill_rm75_lego.envs  # noqa: F401
from maniskill_rm75_lego.envs.rm75_lego_pick_place import (
    PLATE_SIZE_XY,
    PLATE_TOP_POS,
    PLATE_YAW,
    baseplate_origin_from_top,
    build_colored_mesh_actor,
)
from maniskill_rm75_lego.lego_grid import (
    LEGO_BRICK_SPECS,
    LegoGridPose,
    apex_brick_actor_pose,
)
from maniskill_rm75_lego.lego_task_parser import LegoTaskDefinition, load_task_json


BRICK_BY_NAME = {spec.name: spec for spec in LEGO_BRICK_SPECS}


def parse_args():
    parser = argparse.ArgumentParser(description="Preview a LEGO task_ladder initial set on the RM75 plate scene.")
    parser.add_argument("--task-json", "--task-config", default="config/ladder")
    parser.add_argument("--plate-z-offset", type=float, default=None)
    parser.add_argument("--render", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--render-sleep", type=float, default=0.03)
    parser.add_argument("--wait-at-end", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--hide-default-bricks", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--play-task", action="store_true")
    parser.add_argument("--steps-per-move", type=int, default=80)
    parser.add_argument("--hold-frames", type=int, default=30)
    parser.add_argument("--auto-continue-pauses", action="store_true")
    return parser.parse_args()


def _hide_default_scene_bricks(base_env) -> None:
    for actor in getattr(base_env, "bricks", {}).values():
        actor.set_pose(sapien.Pose(p=[0.0, 0.0, -1.0]))
    goal = getattr(base_env, "goal_marker", None)
    if goal is not None:
        goal.set_pose(sapien.Pose(p=[0.0, 0.0, -1.0]))


def _plate_top_pos(task: LegoTaskDefinition, cli_offset: float | None) -> np.ndarray:
    offset = task.plate_z_offset
    if cli_offset is not None:
        offset = cli_offset
    plate_top = np.asarray(PLATE_TOP_POS, dtype=np.float64).copy()
    plate_top[2] += float(offset)
    return plate_top


def _brick_pose_from_grid(plate_top: np.ndarray, brick_type: str, grid_values: list[int]) -> sapien.Pose:
    return apex_brick_actor_pose(
        plate_top,
        PLATE_SIZE_XY,
        BRICK_BY_NAME[brick_type],
        LegoGridPose(*grid_values),
        PLATE_YAW,
    )


def _lerp_pose(a: sapien.Pose, b: sapien.Pose, alpha: float) -> sapien.Pose:
    pa = np.asarray(a.p, dtype=np.float64)
    pb = np.asarray(b.p, dtype=np.float64)
    p = (1.0 - alpha) * pa + alpha * pb
    # Task preview currently keeps all task_ladder bricks at the same yaw.
    return sapien.Pose(p=p.tolist(), q=b.q)


def _render_hold(env, args, label: str) -> None:
    if not args.render:
        return
    print(f"[hold] {label}")
    for _ in range(max(0, int(args.hold_frames))):
        env.render()
        if args.render_sleep > 0:
            time.sleep(args.render_sleep)


def _move_actor(env, actor, start_pose: sapien.Pose, end_pose: sapien.Pose, args, label: str) -> None:
    print(f"[move] {label}: {np.round(np.asarray(start_pose.p), 4).tolist()} -> {np.round(np.asarray(end_pose.p), 4).tolist()}")
    for alpha in np.linspace(0.0, 1.0, max(1, int(args.steps_per_move)) + 1)[1:]:
        actor.set_pose(_lerp_pose(start_pose, end_pose, float(alpha)))
        if args.render:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)


def _move_assembly(env, actors_and_poses: list[tuple], delta: np.ndarray, args, label: str) -> None:
    print(f"[move] {label}: assembly_delta={np.round(delta, 4).tolist()}")
    starts = [(actor, pose) for actor, pose in actors_and_poses]
    for alpha in np.linspace(0.0, 1.0, max(1, int(args.steps_per_move)) + 1)[1:]:
        for actor, start_pose in starts:
            p = np.asarray(start_pose.p, dtype=np.float64) + float(alpha) * delta
            actor.set_pose(sapien.Pose(p=p.tolist(), q=start_pose.q))
        if args.render:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)


def _play_task(env, task: LegoTaskDefinition, plate_top: np.ndarray, actors_by_id: dict, brick_cfgs_by_id: dict, args) -> None:
    current_poses = {
        brick_id: _brick_pose_from_grid(plate_top, cfg.type, cfg.grid)
        for brick_id, cfg in brick_cfgs_by_id.items()
    }
    print("[play] task playback starts")
    operations = task.operations
    for index, op in enumerate(operations, start=1):
        print(
            f"[op] {index:02d} {op.name}: objects={op.pick.object_ids} "
            f"reference={op.pick.reference_id} press_side={op.pick.press_side} "
            f"press_offset={op.pick.press_offset} place_grid={op.place.grid}"
        )
    _render_hold(env, args, "initial")
    for op in operations:
        if len(op.pick.object_ids) == 1:
            brick_id = op.pick.object_ids[0]
            actor = actors_by_id[brick_id]
            start_pose = current_poses[brick_id]
            end_pose = _brick_pose_from_grid(
                plate_top,
                brick_cfgs_by_id[brick_id].type,
                op.place.target_grids[brick_id],
            )
            _move_actor(env, actor, start_pose, end_pose, args, op.name)
            current_poses[brick_id] = end_pose
            if op.place.pause_after:
                print(f"[pause] {op.place.pause_after}")
                if args.auto_continue_pauses:
                    print("[pause] auto-continue enabled")
                else:
                    input("Press Enter after manual alignment to continue playback...")
            _render_hold(env, args, op.name)
        else:
            reference_id = op.pick.reference_id
            reference_start = current_poses[reference_id]
            reference_end_grid = op.place.target_grids[reference_id]
            reference_end = _brick_pose_from_grid(
                plate_top,
                brick_cfgs_by_id[reference_id].type,
                reference_end_grid,
            )
            delta = np.asarray(reference_end.p, dtype=np.float64) - np.asarray(reference_start.p, dtype=np.float64)
            assembly = [(actors_by_id[brick_id], current_poses[brick_id]) for brick_id in op.pick.object_ids]
            _move_assembly(env, assembly, delta, args, op.name)
            for brick_id in op.pick.object_ids:
                cfg = brick_cfgs_by_id[brick_id]
                current_poses[brick_id] = _brick_pose_from_grid(
                    plate_top,
                    cfg.type,
                    op.place.target_grids[brick_id],
                )
                actors_by_id[brick_id].set_pose(current_poses[brick_id])
            if op.place.pause_after:
                print(f"[pause] {op.place.pause_after}")
                if args.auto_continue_pauses:
                    print("[pause] auto-continue enabled")
                else:
                    input("Press Enter after manual alignment to continue playback...")
            _render_hold(env, args, op.name)
    print("[play] task playback done")


def main() -> int:
    args = parse_args()
    task = load_task_json(args.task_json)
    plate_top = _plate_top_pos(task, args.plate_z_offset)

    env = gym.make(
        "RM75LegoPickPlace-v1",
        obs_mode="none",
        reward_mode="none",
        control_mode="pd_joint_pos",
        render_mode="human" if args.render else "rgb_array",
        num_envs=1,
    )
    env.reset(seed=0)
    base_env = env.unwrapped

    if hasattr(base_env, "baseplate"):
        base_env.baseplate.set_pose(sapien.Pose(p=baseplate_origin_from_top(plate_top).tolist()))
    if args.hide_default_bricks:
        _hide_default_scene_bricks(base_env)

    actors = []
    actors_by_id = {}
    brick_cfgs_by_id = {}
    for brick_cfg in task.bricks:
        brick_type = brick_cfg.type
        spec = BRICK_BY_NAME[brick_type]
        grid = LegoGridPose(*brick_cfg.grid)
        pose = apex_brick_actor_pose(plate_top, PLATE_SIZE_XY, spec, grid, PLATE_YAW)
        actor = build_colored_mesh_actor(
            base_env.scene,
            name=f"task_ladder_{brick_cfg.id}",
            mesh_path=spec.mesh_path,
            color=brick_cfg.color,
            pose=pose,
            body_type="kinematic",
        )
        actors.append(actor)
        actors_by_id[brick_cfg.id] = actor
        brick_cfgs_by_id[brick_cfg.id] = brick_cfg
        print(
            f"{brick_cfg.id}: {brick_type} grid={brick_cfg.grid} "
            f"world_p={np.round(np.asarray(pose.p), 6).tolist()}"
        )

    print(f"[task] {task.name}")
    print(f"[plate] top={np.round(plate_top, 6).tolist()}")
    print(f"[scene] spawned {len(actors)} task_ladder bricks")

    if args.play_task:
        _play_task(env, task, plate_top, actors_by_id, brick_cfgs_by_id, args)

    if args.render:
        print("Preview is running. Press Enter or type 'q' then Enter to close.")
        while True:
            env.render()
            if args.render_sleep > 0:
                time.sleep(args.render_sleep)
            if not args.wait_at_end:
                break
            readable, _, _ = select.select([sys.stdin], [], [], 0.0)
            if readable:
                text = sys.stdin.readline().strip().lower()
                if text in ("", "q", "quit", "exit"):
                    break
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
