#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


NO_SUPPORT_TASKS = ("R", "big_chair", "guitar", "test", "tower", "vessel")
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


def type_key(lego_type: str) -> tuple[int, int]:
    dims = lego_type.removeprefix("lego_").split("x")
    return int(dims[0]), int(dims[1])


def make_inventory_grids(bricks: list[dict]) -> dict[str, list[int]]:
    """Lay out one pick brick per target brick on deterministic inventory rows."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for brick in bricks:
        by_type[brick["type"]].append(brick)

    inventory: dict[str, list[int]] = {}
    y_cursor = 0
    max_row_width = 48
    for lego_type in sorted(by_type, key=type_key):
        _, studs_long = type_key(lego_type)
        step = studs_long + 1
        x_cursor = 0
        row_height = 3
        for brick in by_type[lego_type]:
            if x_cursor + studs_long > max_row_width:
                x_cursor = 0
                y_cursor += row_height
            inventory[brick["id"]] = [x_cursor, y_cursor, 0, 0]
            x_cursor += step
        y_cursor += row_height
    return inventory


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

    inventory = make_inventory_grids(bricks)
    initial_bricks = []
    steps = []
    for index, brick in enumerate(bricks):
        color = COLOR_PALETTE[index % len(COLOR_PALETTE)]
        node = brick["apex"]
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
                    "press_side": int(node.get("press_side", 1)),
                    "press_offset": int(node.get("press_offset", 0)),
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
                        int(node.get("press_z", node["z"])) - 1,
                        convert_ori(
                            int(node.get("press_ori", node["ori"])),
                            int(lego_lib[str(node["brick_id"])]["height"]),
                            int(lego_lib[str(node["brick_id"])]["width"]),
                        ),
                    ],
                },
            }
        )

    steps.sort(key=lambda step: (assembly[step["apex_mr"]["source_key"]].get("brick_seq", 0), int(step["apex_mr"]["source_key"])))

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
