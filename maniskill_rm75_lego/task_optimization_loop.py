from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from maniskill_rm75_lego.lego_task_optimizer import (
    PLACE_EXIT_PHASES,
    PICK_TOOL_PHASES,
    PRESS_DOWN_PHASES,
    failed_pick_grids_from_collision_log,
    failed_pick_grids_from_failure_text,
    forbidden_sides_from_place_exit_collision_log,
    forbidden_sides_from_pick_collision_log,
    forbidden_sides_from_collision_log,
    forbidden_sides_from_failure_text,
    merge_forbidden_pick_grids,
    merge_forbidden_sides,
    merge_order_hints,
    optimize_config_dir,
    place_order_hints_from_collision_log,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "maniskill_rm75_lego" / "scripts" / "run_task_lego_robot.py"


def count_tool_clearance_records_for_phases(collision_log_path: Path, phases: set[str]) -> int:
    if not collision_log_path.exists():
        return 0
    with collision_log_path.open("r") as f:
        data = json.load(f)
    return sum(
        record.get("kind") == "tool_clearance"
        and str(record.get("stage", "")).partition("/")[2] in phases
        for record in data.get("records", [])
    )


def count_press_down_tool_clearance_records(collision_log_path: Path) -> int:
    return count_tool_clearance_records_for_phases(collision_log_path, PRESS_DOWN_PHASES)


def count_pick_tool_clearance_records(collision_log_path: Path) -> int:
    return count_tool_clearance_records_for_phases(collision_log_path, PICK_TOOL_PHASES)


def count_place_exit_tool_clearance_records(collision_log_path: Path) -> int:
    return count_tool_clearance_records_for_phases(collision_log_path, PLACE_EXIT_PHASES)


def has_press_down_tool_clearance_records(collision_log_path: Path) -> bool:
    return count_press_down_tool_clearance_records(collision_log_path) > 0


def has_tool_clearance_records(collision_log_path: Path) -> bool:
    return (
        count_press_down_tool_clearance_records(collision_log_path)
        + count_place_exit_tool_clearance_records(collision_log_path)
    ) > 0


def build_runner_command(
    config_dir: Path,
    collision_log_path: Path,
    runner_args: list[str] | None = None,
) -> list[str]:
    return [
        sys.executable,
        str(RUNNER_PATH),
        "--task-config",
        str(config_dir),
        "--no-render",
        "--no-wait-at-end",
        "--auto-continue-pauses",
        "--audit-tool-collisions",
        "--collision-log",
        str(collision_log_path),
        *(runner_args or []),
    ]


def prepare_candidate_dir(source_dir: Path, candidate_dir: Path) -> None:
    if candidate_dir.exists():
        shutil.rmtree(candidate_dir)
    shutil.copytree(source_dir, candidate_dir)


def write_summary(output_dir: Path, summary: dict) -> None:
    with (output_dir / "optimization_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")


def has_new_forbidden_sides(
    history: dict[str, set[int]],
    candidate: dict[str, set[int]],
) -> bool:
    return any(not set(sides).issubset(history.get(brick_id, set())) for brick_id, sides in candidate.items())


def audit_score(
    runner_returncode: int,
    press_down_tool_collisions: int,
    pick_tool_collisions: int,
    place_exit_tool_collisions: int,
    iteration: int,
) -> tuple[int, int, int, int, int]:
    return (
        int(press_down_tool_collisions),
        int(pick_tool_collisions),
        int(place_exit_tool_collisions),
        1 if runner_returncode else 0,
        int(iteration),
    )


def available_sides_after_press_forbidden(press_forbidden_sides: set[int]) -> set[int]:
    if len(press_forbidden_sides) >= 4:
        return {1, 2, 3, 4}
    return {1, 2, 3, 4} - set(press_forbidden_sides)


def exhausted_pick_side_bricks(
    press_forbidden_history: dict[str, set[int]],
    pick_forbidden_history: dict[str, set[int]],
    failed_pick_grids: dict[str, set[tuple[int, int, int, int]]],
) -> set[str]:
    exhausted: set[str] = set()
    for brick_id in failed_pick_grids:
        available_sides = available_sides_after_press_forbidden(press_forbidden_history.get(brick_id, set()))
        if available_sides and available_sides.issubset(pick_forbidden_history.get(brick_id, set())):
            exhausted.add(brick_id)
    return exhausted


def repeated_failed_pick_grid_bricks(
    failed_pick_grid_counts: dict[str, dict[tuple[int, int, int, int], int]],
    min_failures: int = 2,
) -> set[str]:
    return {
        brick_id
        for brick_id, grid_counts in failed_pick_grid_counts.items()
        if any(count >= min_failures for count in grid_counts.values())
    }


def increment_failed_pick_grid_counts(
    failed_pick_grid_counts: dict[str, dict[tuple[int, int, int, int], int]],
    failed_pick_grids: dict[str, set[tuple[int, int, int, int]]],
) -> dict[str, dict[tuple[int, int, int, int], int]]:
    next_counts = {
        brick_id: dict(grid_counts)
        for brick_id, grid_counts in failed_pick_grid_counts.items()
    }
    for brick_id, grids in failed_pick_grids.items():
        brick_counts = next_counts.setdefault(brick_id, {})
        for grid in grids:
            brick_counts[grid] = brick_counts.get(grid, 0) + 1
    return next_counts


def sides_from_task_planning(
    task: dict,
    planning_key: str,
) -> dict[str, set[int]]:
    sides_by_brick: dict[str, set[int]] = {}
    for step in task.get("steps", []):
        brick_id = str(step.get("object", step.get("brick_id")))
        optimizer = step.get("planning", {}).get("optimizer", {})
        values = optimizer.get(planning_key, [])
        if not isinstance(values, list):
            continue
        sides = {int(value) for value in values}
        if sides:
            sides_by_brick.setdefault(brick_id, set()).update(sides)
    return sides_by_brick


def optimizer_history_from_task(task: dict) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    return (
        sides_from_task_planning(task, "forbidden_press_sides"),
        sides_from_task_planning(task, "discouraged_pick_sides"),
    )


def pick_grids_from_task_planning(
    task: dict,
    planning_key: str = "forbidden_pick_grids",
) -> dict[str, set[tuple[int, int, int, int]]]:
    grids_by_brick: dict[str, set[tuple[int, int, int, int]]] = {}
    for step in task.get("steps", []):
        brick_id = str(step.get("object", step.get("brick_id")))
        optimizer = step.get("planning", {}).get("optimizer", {})
        values = optimizer.get(planning_key, [])
        if not isinstance(values, list):
            continue
        grids: set[tuple[int, int, int, int]] = set()
        for value in values:
            if isinstance(value, list) and len(value) == 4:
                grids.add(tuple(int(item) for item in value))
        if grids:
            grids_by_brick.setdefault(brick_id, set()).update(grids)
    return grids_by_brick


def order_hints_from_task_planning(
    task: dict,
    planning_key: str = "preferred_before",
) -> dict[str, set[str]]:
    hints_by_brick: dict[str, set[str]] = {}
    for step in task.get("steps", []):
        brick_id = str(step.get("object", step.get("brick_id")))
        optimizer = step.get("planning", {}).get("optimizer", {})
        values = optimizer.get(planning_key, [])
        if not isinstance(values, list):
            continue
        hints = {str(value) for value in values}
        if hints:
            hints_by_brick.setdefault(brick_id, set()).update(hints)
    return hints_by_brick


def failed_pick_counts_from_forbidden_grids(
    forbidden_pick_grids: dict[str, set[tuple[int, int, int, int]]],
) -> dict[str, dict[tuple[int, int, int, int], int]]:
    return {
        brick_id: {grid: 1 for grid in grids}
        for brick_id, grids in forbidden_pick_grids.items()
    }


def run_optimization_loop(
    config_dir: Path,
    output_dir: Path,
    iterations: int,
    runner_args: list[str] | None = None,
    stop_on_runner_failure_without_log: bool = True,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    current_dir = output_dir / "candidate_00"
    prepare_candidate_dir(config_dir, current_dir)
    with (current_dir / "task.json").open("r") as f:
        initial_task = json.load(f)
    press_forbidden_history, pick_forbidden_history = optimizer_history_from_task(initial_task)
    forbidden_pick_grid_history = pick_grids_from_task_planning(initial_task)
    preferred_before_history = order_hints_from_task_planning(initial_task)
    failed_pick_grid_counts = failed_pick_counts_from_forbidden_grids(forbidden_pick_grid_history)
    best_score: tuple[int, int, int, int, int] | None = None
    best_iteration: int | None = None
    best_source_dir: Path | None = None
    best_dir = output_dir / "best"
    summary = {
        "input_dir": str(config_dir),
        "output_dir": str(output_dir),
        "iterations_requested": int(iterations),
        "iterations": [],
        "final_dir": None,
        "best_dir": None,
        "best_iteration": None,
        "best_score": None,
        "converged": False,
    }

    for iteration in range(max(1, iterations)):
        collision_log = output_dir / f"collision_{iteration:02d}.json"
        runner_log = output_dir / f"runner_{iteration:02d}.log"
        command = build_runner_command(current_dir, collision_log, runner_args)
        result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
        runner_log.write_text(
            f"$ {' '.join(command)}\n\n"
            f"[returncode] {result.returncode}\n\n"
            f"[stdout]\n{result.stdout}\n\n"
            f"[stderr]\n{result.stderr}\n"
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        press_down_tool_collisions = count_press_down_tool_clearance_records(collision_log)
        pick_tool_collisions = count_pick_tool_clearance_records(collision_log)
        place_exit_tool_collisions = count_place_exit_tool_clearance_records(collision_log)
        if collision_log.exists():
            print(f"[optimization loop] press_down_tool_clearance_records={press_down_tool_collisions}")
            print(f"[optimization loop] pick_tool_clearance_records={pick_tool_collisions}")
            print(f"[optimization loop] place_exit_tool_clearance_records={place_exit_tool_collisions}")
        iteration_summary = {
            "iteration": iteration,
            "candidate_dir": str(current_dir),
            "runner_returncode": int(result.returncode),
            "runner_log": str(runner_log),
            "collision_log": str(collision_log) if collision_log.exists() else None,
            "press_down_tool_clearance_records": press_down_tool_collisions,
            "pick_tool_clearance_records": pick_tool_collisions,
            "place_exit_tool_clearance_records": place_exit_tool_collisions,
            "converged": False,
        }
        summary["iterations"].append(iteration_summary)

        if collision_log.exists() or result.returncode == 0:
            current_score = audit_score(
                result.returncode,
                press_down_tool_collisions,
                pick_tool_collisions,
                place_exit_tool_collisions,
                iteration,
            )
            if best_score is None or current_score < best_score:
                best_score = current_score
                best_iteration = iteration
                best_source_dir = current_dir
                prepare_candidate_dir(current_dir, best_dir)
                summary["best_dir"] = str(best_dir)
                summary["best_iteration"] = best_iteration
                summary["best_score"] = list(best_score)
            iteration_summary["score"] = list(current_score)
            iteration_summary["best_so_far"] = best_source_dir == current_dir

        if (
            result.returncode == 0
            and press_down_tool_collisions == 0
            and pick_tool_collisions == 0
            and place_exit_tool_collisions == 0
        ):
            final_dir = output_dir / "final"
            prepare_candidate_dir(current_dir, final_dir)
            iteration_summary["converged"] = True
            summary["final_dir"] = str(final_dir)
            summary["converged"] = True
            write_summary(output_dir, summary)
            return final_dir

        if (
            not collision_log.exists()
            and "IK failed for " not in runner_log.read_text()
            and stop_on_runner_failure_without_log
        ):
            raise RuntimeError(
                f"runner failed before writing collision log or IK failure for {current_dir}; "
                f"exit code {result.returncode}"
            )

        next_dir = output_dir / f"candidate_{iteration + 1:02d}"
        with (current_dir / "task.json").open("r") as f:
            current_task = json.load(f)
        learned_new_side = False
        exhausted_restage_brick_ids: set[str] = set()
        if collision_log.exists():
            with collision_log.open("r") as f:
                collision_data = json.load(f)
                press_forbidden = forbidden_sides_from_collision_log(current_task, collision_data)
                place_exit_forbidden = forbidden_sides_from_place_exit_collision_log(
                    current_task,
                    collision_data,
                )
                press_forbidden = merge_forbidden_sides(press_forbidden, place_exit_forbidden)
                preferred_before_history = merge_order_hints(
                    preferred_before_history,
                    place_order_hints_from_collision_log(current_task, collision_data),
                )
                learned_new_side = learned_new_side or has_new_forbidden_sides(
                    press_forbidden_history,
                    press_forbidden,
                )
                press_forbidden_history = merge_forbidden_sides(press_forbidden_history, press_forbidden)
                if press_down_tool_collisions == 0:
                    pick_side_forbidden = forbidden_sides_from_pick_collision_log(current_task, collision_data)
                    failed_pick_grids = failed_pick_grids_from_collision_log(current_task, collision_data)
                    failed_pick_grid_counts = increment_failed_pick_grid_counts(
                        failed_pick_grid_counts,
                        failed_pick_grids,
                    )
                    repeated_restage_brick_ids = repeated_failed_pick_grid_bricks(failed_pick_grid_counts)
                    learned_new_side = learned_new_side or has_new_forbidden_sides(
                        pick_forbidden_history,
                        pick_side_forbidden,
                    )
                    pick_forbidden_history = merge_forbidden_sides(
                        pick_forbidden_history,
                        pick_side_forbidden,
                    )
                    exhausted_restage_brick_ids.update(
                        exhausted_pick_side_bricks(
                            press_forbidden_history,
                            pick_forbidden_history,
                            failed_pick_grids,
                        )
                    )
                    exhausted_restage_brick_ids.update(
                        brick_id
                        for brick_id in repeated_restage_brick_ids
                        if brick_id in failed_pick_grids
                    )
                    if exhausted_restage_brick_ids:
                        forbidden_pick_grid_history = merge_forbidden_pick_grids(
                            forbidden_pick_grid_history,
                            {
                                brick_id: grids
                                for brick_id, grids in failed_pick_grids.items()
                                if brick_id in exhausted_restage_brick_ids
                            },
                        )
                if press_down_tool_collisions == 0 and not learned_new_side:
                    forbidden_pick_grid_history = merge_forbidden_pick_grids(
                        forbidden_pick_grid_history,
                        failed_pick_grids_from_collision_log(current_task, collision_data),
                    )
        runner_text = runner_log.read_text()
        failure_forbidden = forbidden_sides_from_failure_text(current_task, runner_text)
        learned_new_side = learned_new_side or has_new_forbidden_sides(
            press_forbidden_history,
            failure_forbidden,
        )
        press_forbidden_history = merge_forbidden_sides(
            press_forbidden_history,
            failure_forbidden,
        )
        if press_down_tool_collisions == 0 and not learned_new_side:
            failure_pick_grids = failed_pick_grids_from_failure_text(current_task, runner_text)
            failed_pick_grid_counts = increment_failed_pick_grid_counts(
                failed_pick_grid_counts,
                failure_pick_grids,
            )
            forbidden_pick_grid_history = merge_forbidden_pick_grids(
                forbidden_pick_grid_history,
                failure_pick_grids,
            )
        elif press_down_tool_collisions == 0:
            failure_pick_grids = failed_pick_grids_from_failure_text(current_task, runner_text)
            failed_pick_grid_counts = increment_failed_pick_grid_counts(
                failed_pick_grid_counts,
                failure_pick_grids,
            )
            exhausted_restage_brick_ids.update(
                exhausted_pick_side_bricks(
                    press_forbidden_history,
                    pick_forbidden_history,
                    failure_pick_grids,
                )
            )
            repeated_restage_brick_ids = repeated_failed_pick_grid_bricks(failed_pick_grid_counts)
            exhausted_restage_brick_ids.update(
                brick_id
                for brick_id in repeated_restage_brick_ids
                if brick_id in failure_pick_grids
            )
            if exhausted_restage_brick_ids:
                forbidden_pick_grid_history = merge_forbidden_pick_grids(
                    forbidden_pick_grid_history,
                    {
                        brick_id: grids
                        for brick_id, grids in failure_pick_grids.items()
                        if brick_id in exhausted_restage_brick_ids
                    },
                )
        iteration_summary["forbidden_pick_grids"] = {
            brick_id: [list(grid) for grid in sorted(grids)]
            for brick_id, grids in sorted(forbidden_pick_grid_history.items())
        }
        iteration_summary["forbidden_press_sides"] = {
            brick_id: sorted(sides)
            for brick_id, sides in sorted(press_forbidden_history.items())
        }
        iteration_summary["discouraged_pick_sides"] = {
            brick_id: sorted(sides)
            for brick_id, sides in sorted(pick_forbidden_history.items())
        }
        iteration_summary["exhausted_restage_brick_ids"] = sorted(exhausted_restage_brick_ids)
        iteration_summary["failed_pick_grid_counts"] = {
            brick_id: [
                {"grid": list(grid), "count": count}
                for grid, count in sorted(grid_counts.items())
            ]
            for brick_id, grid_counts in sorted(failed_pick_grid_counts.items())
        }
        iteration_summary["preferred_before"] = {
            brick_id: sorted(before)
            for brick_id, before in sorted(preferred_before_history.items())
        }
        optimize_config_dir(
            input_dir=current_dir,
            output_dir=next_dir,
            collision_log_path=collision_log if collision_log.exists() else None,
            failure_log_path=runner_log,
            forbidden_sides_by_brick=press_forbidden_history,
            discouraged_sides_by_brick=pick_forbidden_history,
            forbidden_pick_grids_by_brick=forbidden_pick_grid_history,
            preferred_before_by_brick=preferred_before_history,
            restage_pick_brick_ids=exhausted_restage_brick_ids if learned_new_side else None,
            restage_pick_collisions=press_down_tool_collisions == 0
            and (not learned_new_side or bool(exhausted_restage_brick_ids)),
        )
        current_dir = next_dir

    final_dir = output_dir / "final"
    prepare_candidate_dir(current_dir, final_dir)
    summary["final_dir"] = str(final_dir)
    write_summary(output_dir, summary)
    return final_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Iteratively run LEGO task audit and re-optimize task press candidates."
    )
    parser.add_argument("config_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument(
        "--keep-going-without-log",
        action="store_true",
        help="Continue optimization even if the runner fails before writing a collision log.",
    )
    parser.add_argument(
        "runner_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments passed to run_task_lego_robot.py after '--'.",
    )
    args = parser.parse_args()
    runner_args = args.runner_args
    if runner_args[:1] == ["--"]:
        runner_args = runner_args[1:]

    final_dir = run_optimization_loop(
        config_dir=args.config_dir,
        output_dir=args.output_dir,
        iterations=args.iterations,
        runner_args=runner_args,
        stop_on_runner_failure_without_log=not args.keep_going_without_log,
    )
    print(f"wrote final optimized candidate: {final_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
