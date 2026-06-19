from __future__ import annotations

from dataclasses import dataclass, field

PressOffset = int | list[int]


@dataclass(frozen=True)
class PickSpec:
    object_ids: list[str]
    reference_id: str
    grid: list[int] | None = None
    press_side: int | None = None
    press_offset: PressOffset | None = None


@dataclass(frozen=True)
class PlaceSpec:
    target_grids: dict[str, list[int]]
    grid: list[int] | None = None
    pause_after: str | None = None


@dataclass(frozen=True)
class PickPlaceOperation:
    name: str
    kind: str
    pick: PickSpec
    place: PlaceSpec
    metadata: dict = field(default_factory=dict)


def pick_spec_from_step(step: dict, object_ids: list[str], reference_id: str) -> PickSpec:
    pick = step.get("pick", {})
    return PickSpec(
        object_ids=object_ids,
        reference_id=reference_id,
        grid=pick.get("grid", step.get("from_grid")),
        press_side=pick.get("press_side"),
        press_offset=pick.get("press_offset"),
    )


def pick_place_operations_from_steps(steps: list[dict]) -> list[PickPlaceOperation]:
    operations: list[PickPlaceOperation] = []
    for index, step in enumerate(steps, start=1):
        kind = step.get("kind")
        name = step.get("name", f"operation_{index:02d}")
        if kind is None:
            kind = "pick_place_assembly" if "objects" in step else "pick_place_single"
        if kind == "pick_place_single":
            brick_id = step.get("object", step.get("brick_id"))
            place = step.get("place", {})
            target_grid = place.get("grid", step.get("to_grid"))
            operations.append(
                PickPlaceOperation(
                    name=name,
                    kind=kind,
                    pick=pick_spec_from_step(step, [brick_id], brick_id),
                    place=PlaceSpec(
                        target_grids={brick_id: target_grid},
                        grid=target_grid,
                        pause_after=place.get("pause_after", step.get("pause_after")),
                    ),
                    metadata={"source_step": step},
                )
            )
        elif kind == "pick_place_assembly":
            object_ids = list(step.get("objects", step.get("assembly_ids")))
            reference_id = step.get("reference", step.get("assembly_pick_reference", object_ids[0]))
            place = step.get("place", {})
            target_grids = place.get("object_grids", step.get("to_grids"))
            operations.append(
                PickPlaceOperation(
                    name=name,
                    kind=kind,
                    pick=pick_spec_from_step(step, object_ids, reference_id),
                    place=PlaceSpec(
                        target_grids={brick_id: grid for brick_id, grid in target_grids.items()},
                        grid=place.get("reference_grid", target_grids.get(reference_id)),
                        pause_after=place.get("pause_after", step.get("pause_after")),
                    ),
                    metadata={"source_step": step},
                )
            )
        else:
            print(f"[skip] unsupported task step kind={kind!r} name={name!r}")
    return operations
