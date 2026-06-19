#!/usr/bin/env python3
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROBOT_PREVIEW_SCRIPT = REPO_ROOT / "maniskill_rm75_lego" / "scripts" / "run_task_ladder_robot_preview.py"


def run_task(task_name: str, passthrough: list[str] | None = None) -> int:
    if passthrough is None:
        passthrough = sys.argv[1:]

    task_config = REPO_ROOT / "config" / "apex_mr" / task_name
    if not task_config.is_dir():
        raise FileNotFoundError(f"Missing converted task config: {task_config}")

    sys.argv = [
        str(ROBOT_PREVIEW_SCRIPT),
        "--task-config",
        str(task_config),
        *passthrough,
    ]
    runpy.run_path(str(ROBOT_PREVIEW_SCRIPT), run_name="__main__")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the generic RM75 robot preview for a converted task.",
        add_help=False,
    )
    parser.add_argument("task_name")
    args, passthrough = parser.parse_known_args()
    return run_task(args.task_name, passthrough)


if __name__ == "__main__":
    raise SystemExit(main())
