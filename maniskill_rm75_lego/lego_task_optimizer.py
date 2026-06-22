from __future__ import annotations

import argparse
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BRICK_SPECS: dict[str, tuple[int, int]] = {
    "lego_1x1": (1, 1),
    "lego_1x2": (2, 1),
    "lego_1x4": (4, 1),
    "lego_1x6": (6, 1),
    "lego_1x8": (8, 1),
    "lego_2x2": (2, 2),
    "lego_2x4": (4, 2),
    "lego_2x6": (6, 2),
    "lego_2x8": (8, 2),
}

PRESS_DOWN_PHASES = {"place_down", "place_press"}
PLACE_EXIT_PHASES = {"place_twist", "place_up"}
PLACE_TOOL_PHASES = PRESS_DOWN_PHASES | PLACE_EXIT_PHASES
PICK_TOOL_PHASES = {"pre_pick", "pick_down"}


@dataclass(frozen=True)
class TaskBrick:
    id: str
    type: str
    grid: list[int]


def brick_dims(brick_type: str, grid: list[int]) -> tuple[int, int]:
    studs_x, studs_y = BRICK_SPECS[brick_type]
    return (studs_x, studs_y) if int(grid[3]) == 0 else (studs_y, studs_x)


def footprint(brick_type: str, grid: list[int]) -> set[tuple[int, int, int]]:
    width, depth = brick_dims(brick_type, grid)
    return {
        (int(grid[0]) + dx, int(grid[1]) + dy, int(grid[2]))
        for dx in range(width)
        for dy in range(depth)
    }


def grid_keys_with_padding(
    brick_type: str,
    grid: list[int],
    plate_size_xy: tuple[int, int],
    padding: int,
) -> set[tuple[int, int, int]]:
    width, depth = brick_dims(brick_type, grid)
    keys: set[tuple[int, int, int]] = set()
    for dx in range(-padding, width + padding):
        for dy in range(-padding, depth + padding):
            x = int(grid[0]) + dx
            y = int(grid[1]) + dy
            if 0 <= x < plate_size_xy[0] and 0 <= y < plate_size_xy[1]:
                keys.add((x, y, int(grid[2])))
    return keys


def expanded_footprint_keys_2d(
    brick_type: str,
    grid: list[int],
    plate_size_xy: tuple[int, int],
    margin: int,
) -> set[tuple[int, int]]:
    width, depth = brick_dims(brick_type, grid)
    keys: set[tuple[int, int]] = set()
    for dx in range(-margin, width + margin):
        for dy in range(-margin, depth + margin):
            x = int(grid[0]) + dx
            y = int(grid[1]) + dy
            if 0 <= x < plate_size_xy[0] and 0 <= y < plate_size_xy[1]:
                keys.add((x, y))
    return keys


def plate_coverage(brick_type: str, grid: list[int], plate_size_xy: tuple[int, int]) -> float:
    studs = footprint(brick_type, grid)
    inside = [
        stud
        for stud in studs
        if 0 <= stud[0] < plate_size_xy[0] and 0 <= stud[1] < plate_size_xy[1]
    ]
    return len(inside) / len(studs)


def side_stud_count(brick_type: str, grid: list[int], press_side: int) -> int:
    studs_x, studs_y = BRICK_SPECS[brick_type]
    return studs_y if press_side in (1, 4) else studs_x


def default_press_offset(brick_type: str, grid: list[int], press_side: int) -> int | list[int]:
    stud_count = side_stud_count(brick_type, grid, press_side)
    if stud_count <= 1:
        return 0
    start = max(0, (stud_count - 2) // 2)
    return [start, start + 1]


def press_offset_candidates(brick_type: str, grid: list[int], press_side: int) -> list[int | list[int]]:
    stud_count = side_stud_count(brick_type, grid, press_side)
    if stud_count <= 1:
        return [0]
    return [[index, index + 1] for index in range(stud_count - 1)]


def offset_indices(press_offset: int | list[int]) -> list[int]:
    if isinstance(press_offset, int):
        return [press_offset]
    return [int(value) for value in press_offset]


def offset_center_distance(brick_type: str, grid: list[int], press_side: int, press_offset: int | list[int]) -> float:
    indices = offset_indices(press_offset)
    selected_center = sum(indices) / len(indices)
    return abs(selected_center - (side_stud_count(brick_type, grid, press_side) - 1) / 2)


def tool_clearance_keys(
    brick_type: str,
    grid: list[int],
    press_side: int,
    press_offset: int | list[int],
) -> set[tuple[int, int]]:
    width, depth = brick_dims(brick_type, grid)
    x, y = int(grid[0]), int(grid[1])
    reach = 2
    indices = offset_indices(press_offset)
    min_offset = min(indices)
    max_offset = max(indices)
    keys: set[tuple[int, int]] = set()
    if press_side == 1:
        keys.update((cx, cy) for cx in range(x + width, x + width + reach) for cy in range(y + min_offset - 1, y + max_offset + 2))
    elif press_side == 4:
        keys.update((cx, cy) for cx in range(x - reach, x) for cy in range(y + min_offset - 1, y + max_offset + 2))
    elif press_side == 2:
        selected_xs = [x + width - 1 - offset for offset in indices]
        keys.update((cx, cy) for cy in range(y + depth, y + depth + reach) for cx in range(min(selected_xs) - 1, max(selected_xs) + 2))
    elif press_side == 3:
        selected_xs = [x + width - 1 - offset for offset in indices]
        keys.update((cx, cy) for cy in range(y - reach, y) for cx in range(min(selected_xs) - 1, max(selected_xs) + 2))
    return keys


def direct_support_ids(brick: TaskBrick, placed: list[TaskBrick]) -> set[str]:
    z = int(brick.grid[2])
    if z <= 0:
        return set()
    support_keys = {(x, y, z - 1) for x, y, _ in footprint(brick.type, brick.grid)}
    return {
        placed_brick.id
        for placed_brick in placed
        if int(placed_brick.grid[2]) == z - 1
        and bool(footprint(placed_brick.type, placed_brick.grid) & support_keys)
    }


def occupied_tool_sweep_keys(brick: TaskBrick, placed: list[TaskBrick]) -> set[tuple[int, int]]:
    support_ids = direct_support_ids(brick, placed)
    target_z = int(brick.grid[2])
    keys: set[tuple[int, int]] = set()
    for placed_brick in placed:
        if int(placed_brick.grid[2]) > target_z:
            continue
        if placed_brick.id in support_ids:
            continue
        keys.update((x, y) for x, y, _ in footprint(placed_brick.type, placed_brick.grid))
    return keys


def choose_press(
    brick: TaskBrick,
    placed: list[TaskBrick],
    plate_size_xy: tuple[int, int],
    forbidden_sides: set[int] | None = None,
    discouraged_sides: set[int] | None = None,
    pick_grid: list[int] | None = None,
    pick_obstacle_keys: set[tuple[int, int]] | None = None,
) -> tuple[int, int | list[int]]:
    forbidden_sides = set(forbidden_sides or ())
    effective_forbidden_sides = forbidden_sides if len(forbidden_sides) < 4 else set()
    available_sides = {1, 2, 3, 4} - effective_forbidden_sides
    discouraged_sides = set(discouraged_sides or ())
    effective_discouraged_sides = (
        discouraged_sides
        if available_sides and not available_sides.issubset(discouraged_sides)
        else set()
    )
    occupied_tool_sweep = occupied_tool_sweep_keys(brick, placed)
    pick_obstacle_keys = set(pick_obstacle_keys or ())

    width, depth = brick_dims(brick.type, brick.grid)
    x, y = int(brick.grid[0]), int(brick.grid[1])
    side_scores = []
    for preference, press_side in enumerate((1, 2, 3, 4)):
        if press_side in effective_forbidden_sides:
            side_scores.append(
                (
                    10**9,
                    0,
                    0,
                    0,
                    preference,
                    0.0,
                    press_side,
                    default_press_offset(brick.type, brick.grid, press_side),
                )
            )
            continue
        if press_side == 1:
            plate_penalty = max(0, x + width + 2 - plate_size_xy[0])
        elif press_side == 4:
            plate_penalty = max(0, 2 - x)
        elif press_side == 2:
            plate_penalty = max(0, y + depth + 2 - plate_size_xy[1])
        else:
            plate_penalty = max(0, 2 - y)
        for press_offset in press_offset_candidates(brick.type, brick.grid, press_side):
            clearance_hits = len(tool_clearance_keys(brick.type, brick.grid, press_side, press_offset) & occupied_tool_sweep)
            pick_clearance_hits = 0
            if pick_grid is not None and pick_obstacle_keys:
                pick_clearance_hits = len(
                    tool_clearance_keys(brick.type, pick_grid, press_side, press_offset) & pick_obstacle_keys
                )
            side_scores.append(
                (
                    clearance_hits,
                    1 if press_side in effective_discouraged_sides else 0,
                    pick_clearance_hits,
                    plate_penalty,
                    preference,
                    offset_center_distance(brick.type, brick.grid, press_side, press_offset),
                    press_side,
                    press_offset,
                )
            )

    _, _, _, _, _, _, press_side, press_offset = min(side_scores)
    return press_side, press_offset


def dependencies(bricks: list[TaskBrick]) -> dict[str, set[str]]:
    graph = {brick.id: set() for brick in bricks}
    by_footprint = {brick.id: footprint(brick.type, brick.grid) for brick in bricks}
    for brick in bricks:
        z = int(brick.grid[2])
        if z == 0:
            continue
        projected = {(x, y, z - 1) for x, y, _ in by_footprint[brick.id]}
        for lower in bricks:
            if lower.id == brick.id or int(lower.grid[2]) != z - 1:
                continue
            if projected & by_footprint[lower.id]:
                graph[brick.id].add(lower.id)
    return graph


def optimize_order(
    bricks: list[TaskBrick],
    original_order: list[str],
    preferred_before_by_brick: dict[str, set[str]] | None = None,
) -> list[str]:
    graph = dependencies(bricks)
    by_id = {brick.id: brick for brick in bricks}
    original_rank = {brick_id: index for index, brick_id in enumerate(original_order)}
    preferred_before_by_brick = {
        brick_id: set(before)
        for brick_id, before in (preferred_before_by_brick or {}).items()
        if brick_id in by_id
    }
    remaining = set(by_id)
    ordered: list[str] = []
    while remaining:
        ready = [
            brick_id
            for brick_id in remaining
            if all(dependency in ordered for dependency in graph[brick_id])
        ]
        if not ready:
            raise ValueError("Could not produce a valid construction order")
        ready.sort(
            key=lambda brick_id: (
                int(by_id[brick_id].grid[2]),
                -len(preferred_before_by_brick.get(brick_id, set()) & remaining),
                int(by_id[brick_id].grid[0]),
                int(by_id[brick_id].grid[1]),
                original_rank.get(brick_id, 10**9),
            )
        )
        chosen = ready[0]
        remaining.remove(chosen)
        ordered.append(chosen)
    return ordered


def forbidden_sides_from_collision_log_for_phases(
    task: dict[str, Any],
    collision_log: dict[str, Any],
    phases: set[str],
) -> dict[str, set[int]]:
    step_by_name = {str(step.get("name")): step for step in task.get("steps", [])}
    forbidden: dict[str, set[int]] = {}
    for record in collision_log.get("records", []):
        if record.get("kind") != "tool_clearance":
            continue
        stage = str(record.get("stage", ""))
        step_name, _, phase = stage.partition("/")
        if phase not in phases:
            continue
        step = step_by_name.get(step_name)
        if not step:
            continue
        brick_id = str(step.get("object", step.get("brick_id")))
        press_side = step.get("pick", {}).get("press_side")
        if press_side is None:
            continue
        forbidden.setdefault(brick_id, set()).add(int(press_side))
    return forbidden


def forbidden_sides_from_collision_log(task: dict[str, Any], collision_log: dict[str, Any]) -> dict[str, set[int]]:
    return forbidden_sides_from_collision_log_for_phases(task, collision_log, PRESS_DOWN_PHASES)


def place_order_hints_from_collision_log(
    task: dict[str, Any],
    collision_log: dict[str, Any],
) -> dict[str, set[str]]:
    step_by_name = {str(step.get("name")): step for step in task.get("steps", [])}
    task_brick_ids = {
        str(step.get("object", step.get("brick_id")))
        for step in task.get("steps", [])
    }
    hints: dict[str, set[str]] = {}
    for record in collision_log.get("records", []):
        if record.get("kind") != "tool_clearance":
            continue
        stage = str(record.get("stage", ""))
        step_name, _, phase = stage.partition("/")
        if phase not in PLACE_TOOL_PHASES:
            continue
        step = step_by_name.get(step_name)
        if not step:
            continue
        target_id = str(step.get("object", step.get("brick_id")))
        for key in ("a", "b"):
            blocker_id = str(record.get(key, ""))
            if blocker_id in {"", "tool", target_id} or blocker_id not in task_brick_ids:
                continue
            hints.setdefault(target_id, set()).add(blocker_id)
    return hints


def forbidden_sides_from_place_exit_collision_log(
    task: dict[str, Any],
    collision_log: dict[str, Any],
) -> dict[str, set[int]]:
    return forbidden_sides_from_collision_log_for_phases(task, collision_log, PLACE_EXIT_PHASES)


def forbidden_sides_from_pick_collision_log(task: dict[str, Any], collision_log: dict[str, Any]) -> dict[str, set[int]]:
    return forbidden_sides_from_collision_log_for_phases(task, collision_log, PICK_TOOL_PHASES)


def failed_pick_bricks_from_collision_log(task: dict[str, Any], collision_log: dict[str, Any]) -> set[str]:
    step_by_name = {str(step.get("name")): step for step in task.get("steps", [])}
    failed: set[str] = set()
    for record in collision_log.get("records", []):
        if record.get("kind") != "tool_clearance":
            continue
        stage = str(record.get("stage", ""))
        step_name, _, phase = stage.partition("/")
        if phase not in PICK_TOOL_PHASES:
            continue
        step = step_by_name.get(step_name)
        if not step:
            continue
        failed.add(str(step.get("object", step.get("brick_id"))))
    return failed


def pick_grids_for_bricks(task: dict[str, Any], brick_ids: set[str]) -> dict[str, set[tuple[int, int, int, int]]]:
    grids: dict[str, set[tuple[int, int, int, int]]] = {}
    for step in task.get("steps", []):
        brick_id = str(step.get("object", step.get("brick_id")))
        if brick_id not in brick_ids:
            continue
        grid = step.get("pick", {}).get("grid")
        if grid is None:
            continue
        grids.setdefault(brick_id, set()).add(tuple(int(value) for value in grid))
    return grids


def failed_pick_grids_from_collision_log(
    task: dict[str, Any],
    collision_log: dict[str, Any],
) -> dict[str, set[tuple[int, int, int, int]]]:
    return pick_grids_for_bricks(task, failed_pick_bricks_from_collision_log(task, collision_log))


def failed_pick_grids_from_failure_text(
    task: dict[str, Any],
    text: str,
) -> dict[str, set[tuple[int, int, int, int]]]:
    return pick_grids_for_bricks(task, failed_pick_bricks_from_failure_text(task, text))


def merge_forbidden_sides(
    target: dict[str, set[int]],
    source: dict[str, set[int]],
) -> dict[str, set[int]]:
    merged = {brick_id: set(sides) for brick_id, sides in target.items()}
    for brick_id, sides in source.items():
        merged.setdefault(brick_id, set()).update(sides)
    return merged


def merge_forbidden_pick_grids(
    target: dict[str, set[tuple[int, int, int, int]]],
    source: dict[str, set[tuple[int, int, int, int]]],
) -> dict[str, set[tuple[int, int, int, int]]]:
    merged = {brick_id: set(grids) for brick_id, grids in target.items()}
    for brick_id, grids in source.items():
        merged.setdefault(brick_id, set()).update(grids)
    return merged


def merge_order_hints(
    target: dict[str, set[str]],
    source: dict[str, set[str]],
) -> dict[str, set[str]]:
    merged = {brick_id: set(before) for brick_id, before in target.items()}
    for brick_id, before in source.items():
        merged.setdefault(brick_id, set()).update(before)
    return merged


def forbidden_sides_from_failure_text(task: dict[str, Any], text: str) -> dict[str, set[int]]:
    step_by_name = {str(step.get("name")): step for step in task.get("steps", [])}
    forbidden: dict[str, set[int]] = {}
    for match in re.finditer(r"IK failed for ([^\\s:]+)", text):
        step_name = match.group(1).split("/", 1)[0]
        step = step_by_name.get(step_name)
        if not step:
            continue
        brick_id = str(step.get("object", step.get("brick_id")))
        press_side = step.get("pick", {}).get("press_side")
        if press_side is None:
            continue
        forbidden.setdefault(brick_id, set()).add(int(press_side))
    return forbidden


def failed_pick_bricks_from_failure_text(task: dict[str, Any], text: str) -> set[str]:
    step_by_name = {str(step.get("name")): step for step in task.get("steps", [])}
    failed: set[str] = set()
    for match in re.finditer(r"IK failed for ([^\\s:]+)", text):
        stage = match.group(1)
        step_name, _, phase = stage.partition("/")
        if not (phase.startswith("pre_pick") or phase.startswith("pick_")):
            continue
        step = step_by_name.get(step_name)
        if not step:
            continue
        failed.add(str(step.get("object", step.get("brick_id"))))
    return failed


def find_restaging_grid(
    brick_type: str,
    current_grid: list[int],
    plate_size_xy: tuple[int, int],
    reserved: set[tuple[int, int, int]],
    forbidden_grids: set[tuple[int, int, int, int]] | None = None,
    obstacle_keys: set[tuple[int, int]] | None = None,
    safety_keys: set[tuple[int, int]] | None = None,
    press_side: int = 1,
    press_offset: int | list[int] | None = None,
) -> list[int]:
    forbidden_grids = set(forbidden_grids or ())
    obstacle_keys = set(obstacle_keys or ())
    safety_keys = set(safety_keys or ())
    press_offset = default_press_offset(brick_type, current_grid, press_side) if press_offset is None else press_offset
    width, _ = brick_dims(brick_type, current_grid)
    min_x = int(-width * 0.2)
    best: tuple[int, int, list[int]] | None = None
    scan_rank = 0
    for z in range(5):
        for y in range(2, plate_size_xy[1]):
            for x in range(8, min_x - 1, -1):
                scan_rank += 1
                candidate = [x, y, z, int(current_grid[3])]
                candidate_key = tuple(candidate)
                if candidate == [int(value) for value in current_grid]:
                    continue
                if candidate_key in forbidden_grids:
                    continue
                actual = grid_keys_with_padding(brick_type, candidate, plate_size_xy, 0)
                if plate_coverage(brick_type, candidate, plate_size_xy) < 0.8:
                    continue
                if actual & reserved:
                    continue
                if {(grid_x, grid_y) for grid_x, grid_y, _ in actual} & safety_keys:
                    continue
                clearance_hits = len(
                    tool_clearance_keys(brick_type, candidate, press_side, press_offset) & obstacle_keys
                )
                score = (clearance_hits, scan_rank, candidate)
                if best is None or score < best:
                    best = score
                    if clearance_hits == 0:
                        return candidate
    if best is not None:
        return best[2]
    raise ValueError(f"Could not restage {brick_type}; no free grid within 5 layers")


def pick_obstacle_keys_before_step(
    task: dict[str, Any],
    entries_by_id: dict[str, dict[str, Any]],
    brick_id: str,
) -> set[tuple[int, int]]:
    keys: set[tuple[int, int]] = set()
    for step in task.get("steps", []):
        step_brick_id = str(step.get("object", step.get("brick_id")))
        if step_brick_id == brick_id:
            break
        entry = entries_by_id.get(step_brick_id)
        place_grid = step.get("place", {}).get("grid", step.get("to_grid"))
        if entry is None or place_grid is None:
            continue
        keys.update((x, y) for x, y, _ in footprint(str(entry["type"]), list(place_grid)))
    return keys


def pick_safety_keys_before_step(
    task: dict[str, Any],
    entries_by_id: dict[str, dict[str, Any]],
    brick_id: str,
    plate_size_xy: tuple[int, int],
    margin: int = 8,
) -> set[tuple[int, int]]:
    keys: set[tuple[int, int]] = set()
    for step in task.get("steps", []):
        step_brick_id = str(step.get("object", step.get("brick_id")))
        if step_brick_id == brick_id:
            break
        entry = entries_by_id.get(step_brick_id)
        place_grid = step.get("place", {}).get("grid", step.get("to_grid"))
        if entry is None or place_grid is None:
            continue
        keys.update(expanded_footprint_keys_2d(str(entry["type"]), list(place_grid), plate_size_xy, margin))
    return keys


def restage_failed_pick_bricks(
    settings: dict[str, Any],
    task: dict[str, Any],
    failed_brick_ids: set[str],
    forbidden_pick_grids_by_brick: dict[str, set[tuple[int, int, int, int]]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not failed_brick_ids:
        return settings, task

    next_settings = copy.deepcopy(settings)
    next_task = copy.deepcopy(task)
    plate = next_settings.get("plate", next_task.get("plate", {}))
    plate_size = tuple(plate.get("plate_size_xy", [48, 48]))
    entries = next_settings.get("initial_bricks", next_settings.get("bricks", []))
    entries_by_id = {str(entry["id"]): entry for entry in entries}
    reserved: set[tuple[int, int, int]] = set()

    for brick_id, entry in entries_by_id.items():
        if brick_id in failed_brick_ids:
            continue
        reserved.update(grid_keys_with_padding(entry["type"], list(entry["grid"]), plate_size, 1))  # type: ignore[arg-type]

    for brick_id in sorted(failed_brick_ids):
        entry = entries_by_id.get(brick_id)
        if not entry:
            continue
        step = next(
            (
                item
                for item in next_task.get("steps", [])
                if str(item.get("object", item.get("brick_id"))) == brick_id
            ),
            {},
        )
        pick = step.get("pick", {})
        press_side = int(pick.get("press_side", 1))
        press_offset = pick.get("press_offset", default_press_offset(entry["type"], list(entry["grid"]), press_side))
        new_grid = find_restaging_grid(
            entry["type"],
            list(entry["grid"]),
            plate_size,
            reserved,  # type: ignore[arg-type]
            (forbidden_pick_grids_by_brick or {}).get(brick_id),
            pick_obstacle_keys_before_step(next_task, entries_by_id, brick_id),
            pick_safety_keys_before_step(next_task, entries_by_id, brick_id, plate_size),  # type: ignore[arg-type]
            press_side,
            press_offset,
        )
        entry["grid"] = new_grid
        reserved.update(grid_keys_with_padding(entry["type"], new_grid, plate_size, 1))  # type: ignore[arg-type]

        for step in next_task.get("steps", []):
            if str(step.get("object", step.get("brick_id"))) == brick_id:
                step.setdefault("pick", {})["grid"] = new_grid

    return next_settings, next_task


def optimize_task(
    settings: dict[str, Any],
    task: dict[str, Any],
    forbidden_sides_by_brick: dict[str, set[int]] | None = None,
    discouraged_sides_by_brick: dict[str, set[int]] | None = None,
    forbidden_pick_grids_by_brick: dict[str, set[tuple[int, int, int, int]]] | None = None,
    preferred_before_by_brick: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    forbidden_sides_by_brick = forbidden_sides_by_brick or {}
    discouraged_sides_by_brick = discouraged_sides_by_brick or {}
    forbidden_pick_grids_by_brick = forbidden_pick_grids_by_brick or {}
    plate = settings.get("plate", task.get("plate", {}))
    plate_size = tuple(plate.get("plate_size_xy", [48, 48]))
    steps = list(task.get("steps", []))
    original_order = [step.get("object", step.get("brick_id")) for step in steps]
    bricks = [
        TaskBrick(
            id=str(step.get("object", step.get("brick_id"))),
            type=str(next((entry["type"] for entry in settings.get("initial_bricks", settings.get("bricks", [])) if entry["id"] == step.get("object", step.get("brick_id"))), "")),
            grid=list(step.get("place", {}).get("grid", step.get("to_grid"))),
        )
        for step in steps
    ]
    if any(not brick.type or brick.grid is None for brick in bricks):
        raise ValueError("Every task step must reference a known brick and place.grid")

    preferred_before_by_brick = preferred_before_by_brick or {}
    ordered_ids = optimize_order(bricks, [str(item) for item in original_order], preferred_before_by_brick)
    steps_by_id = {str(step.get("object", step.get("brick_id"))): step for step in steps}
    bricks_by_id = {brick.id: brick for brick in bricks}
    placed: list[TaskBrick] = []
    optimized_steps = []

    for brick_id in ordered_ids:
        step = copy.deepcopy(steps_by_id[brick_id])
        brick = bricks_by_id[brick_id]
        pick = step.setdefault("pick", {})
        pick_grid = pick.get("grid")
        pick_grid = list(pick_grid) if pick_grid is not None else None
        press_side, press_offset = choose_press(
            brick,
            placed,
            plate_size,  # type: ignore[arg-type]
            forbidden_sides_by_brick.get(brick.id),
            discouraged_sides_by_brick.get(brick.id),
            pick_grid,
            {
                (x, y)
                for placed_brick in placed
                for x, y, _ in footprint(placed_brick.type, placed_brick.grid)
            },
        )
        pick["press_side"] = press_side
        pick["press_offset"] = press_offset
        planning = step.setdefault("planning", {})
        planning["press_strategy"] = "optimizer_candidate"
        forbidden_sides = sorted(forbidden_sides_by_brick.get(brick.id, set()))
        discouraged_sides = sorted(discouraged_sides_by_brick.get(brick.id, set()))
        if forbidden_sides:
            optimizer_planning = planning.setdefault("optimizer", {})
            optimizer_planning["forbidden_sides"] = sorted(
                set(forbidden_sides) | set(discouraged_sides)
            )
            optimizer_planning["forbidden_press_sides"] = forbidden_sides
        if discouraged_sides:
            optimizer_planning = planning.setdefault("optimizer", {})
            optimizer_planning["forbidden_sides"] = sorted(
                set(forbidden_sides) | set(discouraged_sides)
            )
            optimizer_planning["discouraged_pick_sides"] = discouraged_sides
        forbidden_pick_grids = sorted(forbidden_pick_grids_by_brick.get(brick.id, set()))
        if forbidden_pick_grids:
            optimizer_planning = planning.setdefault("optimizer", {})
            optimizer_planning["forbidden_pick_grids"] = [
                list(grid) for grid in forbidden_pick_grids
            ]
        preferred_before = sorted(preferred_before_by_brick.get(brick.id, set()))
        if preferred_before:
            optimizer_planning = planning.setdefault("optimizer", {})
            optimizer_planning["preferred_before"] = preferred_before
        optimized_steps.append(step)
        placed.append(brick)

    optimized = copy.deepcopy(task)
    optimized["steps"] = optimized_steps
    return optimized


def optimize_config_dir(
    input_dir: Path,
    output_dir: Path | None = None,
    collision_log_path: Path | None = None,
    failure_log_path: Path | None = None,
    forbidden_sides_by_brick: dict[str, set[int]] | None = None,
    discouraged_sides_by_brick: dict[str, set[int]] | None = None,
    forbidden_pick_grids_by_brick: dict[str, set[tuple[int, int, int, int]]] | None = None,
    preferred_before_by_brick: dict[str, set[str]] | None = None,
    restage_pick_brick_ids: set[str] | None = None,
    restage_pick_collisions: bool = True,
) -> Path:
    output_dir = output_dir or input_dir
    with (input_dir / "settings.json").open("r") as f:
        settings = json.load(f)
    with (input_dir / "task.json").open("r") as f:
        task = json.load(f)

    forbidden: dict[str, set[int]] = {
        brick_id: set(sides)
        for brick_id, sides in (forbidden_sides_by_brick or {}).items()
    }
    discouraged: dict[str, set[int]] = {
        brick_id: set(sides)
        for brick_id, sides in (discouraged_sides_by_brick or {}).items()
    }
    preferred_before: dict[str, set[str]] = {
        brick_id: set(before)
        for brick_id, before in (preferred_before_by_brick or {}).items()
    }
    restaged = False
    if collision_log_path is not None:
        with collision_log_path.open("r") as f:
            collision_log = json.load(f)
            forbidden = merge_forbidden_sides(
                forbidden,
                forbidden_sides_from_collision_log(task, collision_log),
            )
            forbidden = merge_forbidden_sides(
                forbidden,
                forbidden_sides_from_place_exit_collision_log(task, collision_log),
            )
            preferred_before = merge_order_hints(
                preferred_before,
                place_order_hints_from_collision_log(task, collision_log),
            )
        failed_pick_ids = failed_pick_bricks_from_collision_log(task, collision_log)
        if restage_pick_brick_ids is not None:
            failed_pick_ids &= set(restage_pick_brick_ids)
        if restage_pick_collisions and failed_pick_ids:
            settings, task = restage_failed_pick_bricks(
                settings,
                task,
                failed_pick_ids,
                forbidden_pick_grids_by_brick,
            )
            restaged = True
    if failure_log_path is not None and failure_log_path.exists():
        failure_text = failure_log_path.read_text()
        forbidden = merge_forbidden_sides(
            forbidden,
            forbidden_sides_from_failure_text(task, failure_text),
        )
        failed_pick_ids = failed_pick_bricks_from_failure_text(task, failure_text)
        if restage_pick_brick_ids is not None:
            failed_pick_ids &= set(restage_pick_brick_ids)
        if restage_pick_collisions and failed_pick_ids:
            settings, task = restage_failed_pick_bricks(
                settings,
                task,
                failed_pick_ids,
                forbidden_pick_grids_by_brick,
            )
            restaged = True

    optimized = optimize_task(
        settings,
        task,
        forbidden,
        discouraged,
        forbidden_pick_grids_by_brick,
        preferred_before,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir != input_dir or restaged:
        with (output_dir / "settings.json").open("w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
    with (output_dir / "task.json").open("w") as f:
        json.dump(optimized, f, indent=2)
        f.write("\n")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize LEGO task order and press candidates.")
    parser.add_argument("config_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--collision-log",
        type=Path,
        default=None,
        help="Optional run_task_lego_robot.py collision JSON; tool_clearance records forbid the side used by the matching step.",
    )
    parser.add_argument(
        "--failure-log",
        type=Path,
        default=None,
        help="Optional runner stdout/stderr log; IK failed stages forbid the side used by the matching step.",
    )
    args = parser.parse_args()
    output_dir = optimize_config_dir(args.config_dir, args.output_dir, args.collision_log, args.failure_log)
    print(f"wrote optimized task config: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
