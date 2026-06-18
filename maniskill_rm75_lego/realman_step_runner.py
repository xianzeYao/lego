from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def load_realman_executor(script_path: Path):
    script_path = script_path.expanduser().resolve()
    module_dir = script_path.parent
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))
    spec = importlib.util.spec_from_file_location("rm75_foundationpose_real_exec", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load RealMan script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.RealmanJointExecutor


def confirm_stage(label: str, q_target: np.ndarray, step: bool) -> str:
    print(f"\n[next] {label}")
    print("q(rad):", np.round(np.asarray(q_target, dtype=np.float64), 5).tolist())
    if not step:
        return "run"
    text = input("Press Enter to execute/render this stage, 's' to skip, or 'q' to abort: ").strip().lower()
    if text == "q":
        return "abort"
    if text == "s":
        return "skip"
    return "run"


def _shortest_joint_target(q_prev: np.ndarray, q_target: np.ndarray) -> np.ndarray:
    q_prev = np.asarray(q_prev, dtype=np.float32).reshape(-1)
    q_target = np.asarray(q_target, dtype=np.float32).reshape(-1)[: q_prev.size]
    q_delta = (q_target - q_prev + np.pi) % (2 * np.pi) - np.pi
    return (q_prev + q_delta).astype(np.float32)


def densify_joint_path(q_start: np.ndarray, q_path: np.ndarray, max_delta_per_step: float) -> list[np.ndarray]:
    q_prev = np.asarray(q_start, dtype=np.float32).reshape(-1)
    q_path = np.asarray(q_path, dtype=np.float32)
    if q_path.ndim == 1:
        q_path = q_path[None, :]
    q_cmds: list[np.ndarray] = []
    max_delta_per_step = max(float(max_delta_per_step), 1e-6)
    for q_target_raw in q_path:
        q_target = _shortest_joint_target(q_prev, q_target_raw)
        q_delta = q_target - q_prev
        max_delta = float(np.max(np.abs(q_delta))) if q_delta.size > 0 else 0.0
        num_steps = max(1, int(np.ceil(max_delta / max_delta_per_step)))
        for alpha in np.linspace(0.0, 1.0, num_steps + 1, dtype=np.float32)[1:]:
            q_cmd = (1.0 - alpha) * q_prev + alpha * q_target
            q_cmds.append(np.asarray(q_cmd, dtype=np.float32))
        q_prev = q_target
    return q_cmds


def run_q_path_stage(
    *,
    label: str,
    q_path: np.ndarray,
    args,
    env,
    render_step,
    get_qpos,
    real_exec=None,
    steps: int | None = None,
) -> bool:
    q_path = np.asarray(q_path, dtype=np.float32)
    if q_path.ndim == 1:
        q_path = q_path[None, :]
    q_target = q_path[-1]
    q_start = np.asarray(get_qpos(), dtype=np.float32).reshape(-1)
    decision = confirm_stage(label, q_target, bool(getattr(args, "step", False)))
    if decision == "abort":
        print("[abort] user aborted before stage", label)
        return False
    if decision == "skip":
        print("[skip]", label)
        return True
    print(f"[move] {label}")

    def shadow_callback(q_cmd):
        if not getattr(args, "render", False):
            return
        env.step(np.asarray(q_cmd, dtype=np.float32))
        render_step()

    if real_exec is not None:
        q_real_start = real_exec.get_arm_qpos()
        arm_dim = int(len(q_real_start))
        q_cmds = densify_joint_path(
            q_real_start,
            q_path[:, :arm_dim],
            float(getattr(args, "real_max_delta_per_step", 0.025)),
        )
        if not q_cmds:
            return True
        period = 1.0 / max(float(getattr(args, "real_control_hz", 10.0)), 1e-3)
        hold_steps = int(getattr(args, "real_hold_steps", 0))
        print(f"[real {label}] stream_q_path waypoints={len(q_path)} commands={len(q_cmds)}")
        real_exec._execute_command_stream(
            q_cmds,
            q_cmds[-1],
            gripper_pos=None,
            period=period,
            hold_steps=hold_steps,
            shadow_callback=shadow_callback if getattr(args, "render", False) else None,
        )
        if not getattr(args, "render", False):
            env.step(np.asarray(q_cmds[-1], dtype=np.float32))
            render_step()
        return True

    if len(q_path) == 1:
        count = max(1, int(getattr(args, "steps_per_segment", 80) if steps is None else steps))
        for alpha in np.linspace(0.0, 1.0, count):
            q = (1.0 - alpha) * q_start + alpha * q_target
            env.step(q.astype(np.float32))
            render_step()
    else:
        for q_cmd in q_path:
            env.step(np.asarray(q_cmd, dtype=np.float32))
            render_step()
    return True
