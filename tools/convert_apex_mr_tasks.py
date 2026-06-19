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
TARGET_CENTER = (23, 24)
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


def inventory_ori(brick: dict) -> int:
    return int(brick["target_grid"][3])


def make_inventory_grids(
    bricks: list[dict],
    inventory_x_shift: int = 0,
    inventory_y_shift: int = 0,
    target_stack_height: int = INVENTORY_TARGET_STACK_HEIGHT,
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
    for brick in bricks:
        brick_ori = inventory_ori(brick)
        width_x, height_y = footprint_xy(brick["type"], brick_ori)
        chosen_stack = None
        for stack in stacks:
            if len(stack["bricks"]) >= target_stack_height:
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


def normalize_target_grids(bricks: list[dict]) -> int:
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

    shift_x = int(round(TARGET_CENTER[0] - (min_x + max_x) / 2.0))
    shift_y = int(round(TARGET_CENTER[1] - (min_y + max_y) / 2.0))
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

    target_z_offset = normalize_target_grids(bricks)
    ordered_bricks = sorted(bricks, key=placement_order_key)
    inventory = make_inventory_grids(
        ordered_bricks,
        TASK_INVENTORY_X_SHIFT.get(task, 0),
        TASK_INVENTORY_Y_SHIFT.get(task, 0),
        TASK_INVENTORY_STACK_HEIGHT.get(task, INVENTORY_TARGET_STACK_HEIGHT),
    )
    initial_bricks = []
    steps = []
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
