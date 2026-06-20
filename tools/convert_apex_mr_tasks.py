#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


NO_SUPPORT_TASKS = ("R", "big_chair", "guitar", "test", "tower", "vessel")
PLATE_SIZE = 48
INVENTORY_STRIP_X_MAX = 28
INVENTORY_GAP = 1
INVENTORY_MARGIN = 4
INVENTORY_TARGET_STACK_HEIGHT = 6
TASK_INVENTORY_STACK_HEIGHT = {
    "vessel": 4,
}
TASK_TYPE_STACK_HEIGHT = {
    "vessel": {"lego_1x8": 2},
}
TASK_INVENTORY_GRID_OVERRIDES = {
    "vessel": {
        "B026": [21, 1, 0, 1],
        "B032": [18, 28, 0, 1],
    },
}
TASK_UNSTACKED_TYPES = {
    "vessel": {"lego_1x1"},
}
TARGET_CENTER = (23, 24)
TASK_TARGET_CENTER_SHIFT = {
    "vessel": (0, -3),
}
INVENTORY_START_X = 7
INVENTORY_SIDE = "left"
FLIP_PICK_SIDE = False
TASK_INVENTORY_X_SHIFT = {
    "guitar": 2,
    "vessel": 2,
}
TASK_INVENTORY_Y_SHIFT = {
    "vessel": -3,
}
TOOL_AUDIT_BOX_STUDS = (0.105 / 0.008, 0.030 / 0.008)
COLOR_PALETTE = (
    [0.78, 0.48, 0.92, 1.0],
    [0.02, 0.18, 0.10, 1.0],
    [1.0, 0.68, 0.02, 1.0],
    [0.82, 0.05, 0.04, 1.0],
    [0.52, 0.86, 0.02, 1.0],
    [0.70, 0.92, 0.08, 1.0],
)


def load_json(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def lego_type_from_dims(height: int, width: int) -> str:
    a, b = sorted((int(height), int(width)))
    supported = {
        (1, 1),
        (1, 2),
        (1, 4),
        (1, 6),
        (1, 8),
        (2, 2),
        (2, 4),
        (2, 6),
        (2, 8),
    }
    if (a, b) not in supported:
        raise ValueError(f"Unsupported LEGO dimensions {height}x{width}")
    return f"lego_{a}x{b}"


def convert_ori(apex_ori: int, height: int, width: int) -> int:
    if height == width:
        return 0
    if apex_ori not in (0, 1):
        raise ValueError(f"Unsupported APEX orientation {apex_ori}")
    return 1 - int(apex_ori)


def convert_grid(node: dict, lego_lib: dict) -> list[int]:
    brick_id = str(node["brick_id"])
    dims = lego_lib[brick_id]
    return [
        int(node["x"]),
        int(node["y"]),
        int(node["z"]) - 1,
        convert_ori(int(node["ori"]), int(dims["height"]), int(dims["width"])),
    ]


def local_press_offset(offset: int, stud_count: int) -> int | list[int]:
    """Use a single-stud grab only on one-stud sides; otherwise grab adjacent studs."""
    offset = int(offset)
    stud_count = int(stud_count)
    if stud_count <= 0:
        raise ValueError(f"Invalid stud_count={stud_count}")
    if stud_count == 1:
        if offset != 0:
            raise ValueError(f"press_offset={offset} invalid for one-stud side; expected 0")
        return 0
    if offset <= 0:
        return [0, 1]
    if offset >= stud_count - 1:
        return [stud_count - 2, stud_count - 1]
    return [offset - 1, offset]


def convert_press(apex_side: int, apex_offset: int, height: int, width: int) -> tuple[int, int | list[int]]:
    """Map APEX-MR side/offset into this repo's brick-local side convention.

    APEX names the short brick axis "height" and the long axis "width". This
    repo stores the same brick as studs_x=long, studs_y=short. Keep the runner's
    side semantics unchanged and rotate the APEX side labels during conversion.
    """
    apex_side = int(apex_side)
    apex_offset = int(apex_offset)
    height = int(height)
    width = int(width)
    if apex_side in (1, 4):
        if not 0 <= apex_offset < width:
            raise ValueError(
                f"APEX press_offset={apex_offset} invalid for side {apex_side}; expected 0..{width - 1}"
        )
        local_offset = width - 1 - apex_offset
        local_side = 3 if apex_side == 1 else 2
        return local_side, local_press_offset(local_offset, width)
    if apex_side in (2, 3):
        if not 0 <= apex_offset < height:
            raise ValueError(
                f"APEX press_offset={apex_offset} invalid for side {apex_side}; expected 0..{height - 1}"
            )
        local_side = 1 if apex_side == 2 else 4
        return local_side, local_press_offset(apex_offset, height)
    raise ValueError(f"Unsupported APEX press_side {apex_side}; expected 1..4")


def type_key(lego_type: str) -> tuple[int, int]:
    dims = lego_type.removeprefix("lego_").split("x")
    return int(dims[0]), int(dims[1])


def footprint_xy(lego_type: str, ori: int) -> tuple[int, int]:
    studs_short, studs_long = type_key(lego_type)
    if int(ori) == 0:
        return studs_long, studs_short
    if int(ori) == 1:
        return studs_short, studs_long
    raise ValueError(f"Unsupported LEGO orientation {ori}")


def local_stud_dims(lego_type: str) -> tuple[int, int]:
    studs_short, studs_long = type_key(lego_type)
    return studs_long, studs_short


def side_stud_count(lego_type: str, side: int) -> int:
    studs_x, studs_y = local_stud_dims(lego_type)
    if int(side) in (1, 4):
        return studs_y
    if int(side) in (2, 3):
        return studs_x
    raise ValueError(f"Unsupported press_side={side}")


def centered_press_offset(lego_type: str, side: int) -> int | list[int]:
    stud_count = side_stud_count(lego_type, side)
    if stud_count == 1:
        return 0
    return local_press_offset(stud_count // 2, stud_count)


def grid_footprint_aabb(lego_type: str, grid: list[int]) -> tuple[float, float, float, float]:
    x, y, _z, ori = grid
    width_x, height_y = footprint_xy(lego_type, ori)
    return float(x), float(y), float(x + width_x), float(y + height_y)


def contact_frame_top_view(
    lego_type: str,
    grid: list[int],
    side: int,
    press_offset: int | list[int],
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Return contact center plus local tool x/y axes in plate-grid units."""
    x, y, _z, ori = grid
    studs_x, studs_y = local_stud_dims(lego_type)
    if isinstance(press_offset, int):
        offsets = (press_offset,)
    else:
        offsets = tuple(int(offset) for offset in press_offset)

    if side in (1, 4):
        y_values = [-studs_y / 2.0 + (offset + 0.5) for offset in offsets]
        local_x = studs_x / 2.0 if side == 1 else -studs_x / 2.0
        local_y = sum(y_values) / len(y_values)
        outward_local = (1.0 if side == 1 else -1.0, 0.0)
    elif side in (2, 3):
        x_values = [studs_x / 2.0 - (offset + 0.5) for offset in offsets]
        local_x = sum(x_values) / len(x_values)
        local_y = studs_y / 2.0 if side == 2 else -studs_y / 2.0
        outward_local = (0.0, 1.0 if side == 2 else -1.0)
    else:
        raise ValueError(f"Unsupported press_side={side}")

    if int(ori) == 0:
        center = (x + studs_x / 2.0 + local_x, y + studs_y / 2.0 + local_y)
        x_axis = outward_local
    elif int(ori) == 1:
        center = (x + studs_y / 2.0 - local_y, y + studs_x / 2.0 + local_x)
        x_axis = (-outward_local[1], outward_local[0])
    else:
        raise ValueError(f"Unsupported LEGO orientation {ori}")

    y_axis = (-x_axis[1], x_axis[0])
    return center, x_axis, y_axis


def tool_top_view_aabb(
    lego_type: str,
    grid: list[int],
    side: int,
    press_offset: int | list[int],
) -> tuple[float, float, float, float]:
    center, x_axis, y_axis = contact_frame_top_view(lego_type, grid, side, press_offset)
    half_x = TOOL_AUDIT_BOX_STUDS[0] / 2.0
    half_y = TOOL_AUDIT_BOX_STUDS[1] / 2.0
    extent_x = abs(x_axis[0]) * half_x + abs(y_axis[0]) * half_y
    extent_y = abs(x_axis[1]) * half_x + abs(y_axis[1]) * half_y
    return (
        center[0] - extent_x,
        center[1] - extent_y,
        center[0] + extent_x,
        center[1] + extent_y,
    )


def aabb_overlap_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    overlap_x = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    overlap_y = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return overlap_x * overlap_y


def choose_vessel_press_side(
    brick: dict,
    original_side: int,
    original_offset: int | list[int],
    placed_bricks: list[dict],
) -> tuple[int, int | list[int]]:
    """Pick the target-side approach with the most clearance from placed bricks."""
    current_grid = brick["target_grid"]
    current_aabb = grid_footprint_aabb(brick["type"], current_grid)
    candidates = []
    allowed_sides = (1, 2, 3, 4)
    if brick["type"] == "lego_1x8" and original_side in (2, 3):
        allowed_sides = (2, 3)
    for side in allowed_sides:
        offset = centered_press_offset(brick["type"], side)
        tool_aabb = tool_top_view_aabb(brick["type"], current_grid, side, offset)
        score = 0.0
        same_layer_score = 0.0
        for placed in placed_bricks:
            placed_grid = placed["target_grid"]
            if int(placed_grid[2]) > int(current_grid[2]):
                continue
            placed_aabb = grid_footprint_aabb(placed["type"], placed_grid)
            if aabb_overlap_area(current_aabb, placed_aabb) > 0.0:
                continue
            area = aabb_overlap_area(tool_aabb, placed_aabb)
            score += area
            if int(placed_grid[2]) == int(current_grid[2]):
                same_layer_score += area
        original_penalty = 0 if side == original_side and offset == original_offset else 1
        candidates.append((score, same_layer_score, original_penalty, side, offset))
    _, _, _, side, offset = min(candidates, key=lambda item: item[:4])
    return side, offset


def inventory_ori(brick: dict) -> int:
    return int(brick["target_grid"][3])


def make_inventory_grids(
    bricks: list[dict],
    inventory_x_shift: int = 0,
    inventory_y_shift: int = 0,
    target_stack_height: int = INVENTORY_TARGET_STACK_HEIGHT,
    unstacked_types: set[str] | None = None,
    type_stack_height: dict[str, int] | None = None,
) -> dict[str, list[int]]:
    """Lay out inventory near the plate edge, filling +Y first then +X.

    Inventory mirrors each brick's target orientation where possible, reducing
    the wrist rotation needed between pick and place. For large tasks the same
    edge slots are reused in Z; earlier operations are placed above later ones.
    """
    max_width_x = max(footprint_xy(brick["type"], inventory_ori(brick))[0] for brick in bricks)
    max_height_y = max(footprint_xy(brick["type"], inventory_ori(brick))[1] for brick in bricks)
    slots: list[tuple[int, int, int]] = []
    if INVENTORY_SIDE == "right":
        x_cursor = max(INVENTORY_MARGIN, PLATE_SIZE - INVENTORY_MARGIN - INVENTORY_STRIP_X_MAX)
        x_limit = PLATE_SIZE - INVENTORY_MARGIN
    else:
        x_cursor = max(INVENTORY_MARGIN, INVENTORY_START_X + int(inventory_x_shift))
        x_limit = min(INVENTORY_STRIP_X_MAX, PLATE_SIZE - INVENTORY_MARGIN)
    y_limit = PLATE_SIZE - INVENTORY_MARGIN
    while x_cursor + max_width_x <= x_limit:
        y_cursor = INVENTORY_MARGIN + int(inventory_y_shift)
        while y_cursor + max_height_y <= y_limit:
            slots.append((x_cursor, y_cursor, 1))
            y_cursor += max_height_y + INVENTORY_GAP
        x_cursor += max_width_x + INVENTORY_GAP

    if not slots:
        raise RuntimeError("Failed to create inventory slots")
    inventory: dict[str, list[int]] = {}
    stacks: list[dict] = []
    next_slot_index = 0
    unstacked_types = set(unstacked_types or ())
    type_stack_height = dict(type_stack_height or {})
    for brick in bricks:
        brick_ori = inventory_ori(brick)
        width_x, height_y = footprint_xy(brick["type"], brick_ori)
        stack_height_limit = int(type_stack_height.get(brick["type"], target_stack_height))
        chosen_stack = None
        for stack in stacks:
            if brick["type"] in unstacked_types:
                continue
            if len(stack["bricks"]) >= stack_height_limit:
                continue
            if brick_ori != stack["ori"]:
                continue
            if width_x == stack["max_width_x"] and height_y == stack["max_height_y"]:
                chosen_stack = stack
                break
        if chosen_stack is None and next_slot_index >= len(slots):
            compatible_stacks = [
                stack
                for stack in stacks
                if brick_ori == stack["ori"]
                and width_x == stack["max_width_x"]
                and height_y == stack["max_height_y"]
                and len(stack["bricks"]) < stack_height_limit
            ]
            if compatible_stacks:
                chosen_stack = min(compatible_stacks, key=lambda stack: len(stack["bricks"]))
        if chosen_stack is None:
            if next_slot_index >= len(slots):
                compatible_stacks = [
                    stack for stack in stacks if brick_ori == stack["ori"]
                ]
                if not compatible_stacks:
                    raise RuntimeError(
                        f"Not enough inventory slots for orientation {brick_ori}"
                    )
                chosen_stack = min(compatible_stacks, key=lambda stack: len(stack["bricks"]))
            else:
                x, y, _ori = slots[next_slot_index]
                next_slot_index += 1
                chosen_stack = {
                    "slot": (x, y),
                    "ori": brick_ori,
                    "bricks": [],
                    "max_width_x": 0,
                    "max_height_y": 0,
                }
                stacks.append(chosen_stack)
        chosen_stack["bricks"].append(brick)
        chosen_stack["max_width_x"] = max(chosen_stack["max_width_x"], width_x)
        chosen_stack["max_height_y"] = max(chosen_stack["max_height_y"], height_y)

    for stack in stacks:
        x, y = stack["slot"]
        stack_bricks = stack["bricks"]
        for index, brick in enumerate(stack_bricks):
            z = len(stack_bricks) - 1 - index
            ori = stack["ori"]
            inventory[brick["id"]] = [x, y, z, ori]
    return inventory


def opposite_press_side(side: int) -> int:
    return {1: 4, 2: 3, 3: 2, 4: 1}[int(side)]


def normalize_target_grids(
    bricks: list[dict],
    target_center: tuple[int, int] = TARGET_CENTER,
) -> int:
    min_z = min(brick["target_grid"][2] for brick in bricks)
    for brick in bricks:
        brick["target_grid"][2] -= min_z

    min_x = min_y = 10**9
    max_x = max_y = -10**9
    for brick in bricks:
        x, y, _z, ori = brick["target_grid"]
        width_x, height_y = footprint_xy(brick["type"], ori)
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x + width_x)
        max_y = max(max_y, y + height_y)

    shift_x = int(round(target_center[0] - (min_x + max_x) / 2.0))
    shift_y = int(round(target_center[1] - (min_y + max_y) / 2.0))
    shift_x = max(-min_x, min(PLATE_SIZE - max_x, shift_x))
    shift_y = max(-min_y, min(PLATE_SIZE - max_y, shift_y))
    for brick in bricks:
        brick["target_grid"][0] += shift_x
        brick["target_grid"][1] += shift_y
    return min_z


def placement_order_key(brick: dict) -> tuple[int, int, int]:
    return (
        int(brick["target_grid"][2]),
        int(brick["apex"].get("brick_seq", 0)),
        int(brick["apex_key"]),
    )


def min_tool_overlap_against(a: dict, b: dict) -> float:
    a_aabb = grid_footprint_aabb(a["type"], a["target_grid"])
    b_aabb = grid_footprint_aabb(b["type"], b["target_grid"])
    if aabb_overlap_area(a_aabb, b_aabb) > 0.0:
        return 0.0
    best = None
    for side in (1, 2, 3, 4):
        offset = centered_press_offset(a["type"], side)
        tool_aabb = tool_top_view_aabb(a["type"], a["target_grid"], side, offset)
        area = aabb_overlap_area(tool_aabb, b_aabb)
        best = area if best is None else min(best, area)
    return float(best or 0.0)


def vessel_ordered_bricks(bricks: list[dict]) -> list[dict]:
    """Keep z-order, but place same-layer tool-obstructing bricks earlier."""
    ordered: list[dict] = []
    for z in sorted({int(brick["target_grid"][2]) for brick in bricks}):
        layer = [brick for brick in bricks if int(brick["target_grid"][2]) == z]
        net_priority: dict[str, float] = {brick["id"]: 0.0 for brick in layer}
        for a in layer:
            for b in layer:
                if a is b:
                    continue
                net_priority[a["id"]] += min_tool_overlap_against(a, b)
                net_priority[a["id"]] -= min_tool_overlap_against(b, a)
        ordered.extend(
            sorted(
                layer,
                key=lambda brick: (
                    -net_priority[brick["id"]],
                    int(brick["apex"].get("brick_seq", 0)),
                    int(brick["apex_key"]),
                ),
            )
        )
    return ordered


def convert_task(apex_root: Path, task: str, out_root: Path) -> None:
    lego_lib = load_json(apex_root / "config/lego_tasks/lego_library.json")
    assembly_path = apex_root / "config/lego_tasks/assembly_tasks" / f"{task}.json"
    assembly = load_json(assembly_path)

    bricks = []
    for key in sorted(assembly, key=lambda k: int(k)):
        node = assembly[key]
        dims = lego_lib[str(node["brick_id"])]
        bricks.append(
            {
                "id": f"B{int(key):03d}",
                "apex_key": key,
                "type": lego_type_from_dims(int(dims["height"]), int(dims["width"])),
                "target_grid": convert_grid(node, lego_lib),
                "apex": node,
            }
        )

    target_shift = TASK_TARGET_CENTER_SHIFT.get(task, (0, 0))
    target_center = (
        TARGET_CENTER[0] + int(target_shift[0]),
        TARGET_CENTER[1] + int(target_shift[1]),
    )
    target_z_offset = normalize_target_grids(bricks, target_center)
    ordered_bricks = vessel_ordered_bricks(bricks) if task == "vessel" else sorted(bricks, key=placement_order_key)
    inventory = make_inventory_grids(
        ordered_bricks,
        TASK_INVENTORY_X_SHIFT.get(task, 0),
        TASK_INVENTORY_Y_SHIFT.get(task, 0),
        TASK_INVENTORY_STACK_HEIGHT.get(task, INVENTORY_TARGET_STACK_HEIGHT),
        TASK_UNSTACKED_TYPES.get(task),
        TASK_TYPE_STACK_HEIGHT.get(task),
    )
    inventory.update(TASK_INVENTORY_GRID_OVERRIDES.get(task, {}))
    initial_bricks = []
    steps = []
    placed_bricks: list[dict] = []
    for index, brick in enumerate(ordered_bricks):
        color = COLOR_PALETTE[index % len(COLOR_PALETTE)]
        node = brick["apex"]
        dims = lego_lib[str(node["brick_id"])]
        press_side, press_offset = convert_press(
            int(node.get("press_side", 1)),
            int(node.get("press_offset", 0)),
            int(dims["height"]),
            int(dims["width"]),
        )
        if task == "R" and brick["type"] == "lego_2x2":
            press_side = 1
        if task in ("guitar", "vessel") and brick["type"] == "lego_2x2" and press_side == 3:
            press_side = 1
        if task == "guitar" and brick["id"] == "B003":
            press_side = 3
            press_offset = [0, 1]
        if task == "vessel" and brick["id"] == "B010":
            press_side = 1
            press_offset = 0
        if task == "vessel":
            press_side, press_offset = choose_vessel_press_side(
                brick,
                press_side,
                press_offset,
                placed_bricks,
            )
        if FLIP_PICK_SIDE:
            press_side = opposite_press_side(press_side)
        initial_bricks.append(
            {
                "id": brick["id"],
                "type": brick["type"],
                "grid": inventory[brick["id"]],
                "role": f"apex_mr_{task}_brick_{brick['apex_key']}",
                "color": color,
            }
        )
        steps.append(
            {
                "name": f"place_{brick['id'].lower()}",
                "object": brick["id"],
                "pick": {
                    "grid": inventory[brick["id"]],
                    "press_side": press_side,
                    "press_offset": press_offset,
                },
                "place": {
                    "grid": brick["target_grid"],
                },
                "apex_mr": {
                    "source_task": task,
                    "source_key": brick["apex_key"],
                    "brick_id": int(node["brick_id"]),
                    "brick_seq": node.get("brick_seq"),
                    "press_grid": [
                        int(node.get("press_x", node["x"])),
                        int(node.get("press_y", node["y"])),
                        int(node.get("press_z", node["z"])) - 1 - target_z_offset,
                        convert_ori(
                            int(node.get("press_ori", node["ori"])),
                            int(lego_lib[str(node["brick_id"])]["height"]),
                            int(lego_lib[str(node["brick_id"])]["width"]),
                        ),
                    ],
                },
            }
        )
        placed_bricks.append(brick)

    settings = {
        "name": f"apex_mr_{task}",
        "source": {
            "format": "APEX-MR",
            "assembly_task": str(assembly_path),
        },
        "plate": {
            "plate_z_offset": 0.0,
            "plate_size_xy": [48, 48],
        },
        "initial_bricks": initial_bricks,
    }
    task_json = {
        "name": f"apex_mr_{task}",
        "steps": steps,
    }

    task_dir = out_root / task
    write_json(task_dir / "settings.json", settings)
    write_json(task_dir / "task.json", task_json)
    print(f"wrote {task_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert no-support APEX-MR LEGO tasks into this repo's config format.")
    parser.add_argument("--apex-root", type=Path, default=Path("third_party/APEX-MR"))
    parser.add_argument("--out-root", type=Path, default=Path("config/apex_mr"))
    parser.add_argument("--tasks", nargs="+", default=list(NO_SUPPORT_TASKS))
    args = parser.parse_args()

    for task in args.tasks:
        convert_task(args.apex_root, task, args.out_root)


if __name__ == "__main__":
    main()
