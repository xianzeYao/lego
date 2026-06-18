from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from maniskill_rm75_lego.lego_pick_place import (
    PickPlaceOperation,
    pick_place_operations_from_steps,
)


@dataclass(frozen=True)
class LegoBrickInstance:
    id: str
    type: str
    grid: list[int]
    color: list[float]
    role: str | None = None


@dataclass(frozen=True)
class LegoTaskDefinition:
    name: str
    plate_z_offset: float
    bricks: list[LegoBrickInstance]
    operations: list[PickPlaceOperation]
    raw: dict


def load_task_json(path: str | Path) -> LegoTaskDefinition:
    path = Path(path)
    if path.is_dir():
        return load_task_config_dir(path)
    if path.is_file():
        raise ValueError(
            f"Expected a task config directory, got file: {path}. "
            "Use a folder containing settings.json for the initial set and task.json for the operations."
        )
    raise FileNotFoundError(f"Task config path does not exist: {path}")


def load_task_config_dir(path: str | Path) -> LegoTaskDefinition:
    path = Path(path)
    settings_path = path / "settings.json"
    task_path = path / "task.json"
    missing = [p.name for p in (settings_path, task_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Task config directory {path} is missing: {', '.join(missing)}. "
            "Expected settings.json for the initial set and task.json for the operations."
        )
    with settings_path.open("r") as f:
        settings = json.load(f)
    with task_path.open("r") as f:
        task = json.load(f)
    merged = {
        **settings,
        **task,
        "plate": settings.get("plate", task.get("plate", {})),
        "initial_bricks": settings.get("initial_bricks", settings.get("bricks", [])),
    }
    return parse_task_json(merged, fallback_name=path.name)


def parse_task_json(data: dict, fallback_name: str = "lego_task") -> LegoTaskDefinition:
    brick_entries = data.get("bricks", data.get("initial_bricks", []))
    bricks = [
        LegoBrickInstance(
            id=entry["id"],
            type=entry["type"],
            grid=list(entry["grid"]),
            color=list(entry.get("color", [0.8, 0.8, 0.8, 1.0])),
            role=entry.get("role"),
        )
        for entry in brick_entries
    ]
    return LegoTaskDefinition(
        name=data.get("name", fallback_name),
        plate_z_offset=float(data.get("plate", {}).get("plate_z_offset", 0.0)),
        bricks=bricks,
        operations=pick_place_operations_from_steps(list(data.get("steps", []))),
        raw=data,
    )
