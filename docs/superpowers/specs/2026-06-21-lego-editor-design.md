# 3D LEGO Task Editor Design

## Purpose

Build a browser-based editor for manually assembling LEGO task layouts. The editor lets a user choose LEGO brick types, place them directly in a 3D baseplate scene, validate that the resulting structure is geometrically valid and buildable, then export repository-compatible `settings.json` and first-pass `task.json` files.

The first version is an editor and preview tool, not a physics simulator or robot planner.

## Scope

Included in the first version:

- Select LEGO brick type and color from a library.
- Place bricks directly in a 3D scene with stud-grid snapping.
- Support stacking on existing bricks.
- Track final structure and user placement history.
- Validate geometry, support, and basic construction order.
- Export `settings.json` from the final structure.
- Export `task.json` from the placement order, with unplanned press strategy fields kept explicit.

Excluded from the first version:

- Physical stability, center-of-mass, tipping, or structure strength checks.
- Robot reachability or motion-planning validation.
- Automatic `press_side` / `press_offset` selection.
- Full STL-based LEGO rendering. Programmatic cuboids and studs are enough for the first editor.

## Existing Repository Fit

The editor should align with the existing Python task shape:

- `maniskill_rm75_lego/lego_grid.py` defines LEGO grid constants, brick specs, and grid/world conversion.
- `maniskill_rm75_lego/lego_task_parser.py` reads `settings.json` and `task.json` from task config directories.
- Current configs use `settings.json` for initial/final brick definitions and `task.json` for ordered steps.

The editor should keep its TypeScript domain model close to these conventions so a later Python validator or converter can compare outputs directly.

## Product Model

The editor has two sources of truth:

1. `SceneState`: the final assembled structure.
2. `PlacementHistory`: the user's placement sequence.

```ts
type BrickInstance = {
  id: string;
  type: "lego_1x1" | "lego_1x2" | "lego_1x4" | "lego_1x6" | "lego_1x8" |
        "lego_2x2" | "lego_2x4" | "lego_2x6" | "lego_2x8";
  grid: [number, number, number, 0 | 1];
  color: [number, number, number, number];
  placedAt: number;
  pressSide?: number | null;
  pressOffset?: [number, number] | null;
};

type PlacementStep = {
  stepId: string;
  brickId: string;
  type: BrickInstance["type"];
  grid: [number, number, number, 0 | 1];
  timestamp: number;
};
```

The user edits the final structure, but the editor preserves placement history so the first `task.json` can reflect the user's intended build order. Later automatic task planning can replace or reorder this history without changing the scene representation.

## UI Design

Use a tool-style layout:

- Left panel: brick library, color selector, repeat placement mode.
- Center: large 3D canvas with the baseplate, placed bricks, hover ghost, snapping preview, and invalid placement highlights.
- Right panel: selected brick inspector, legality messages, placement order, manual press strategy overrides, and export actions.

The right panel keeps placement order visible even though the layout is not sequence-first. This prevents hidden task ordering mistakes when exporting.

## 3D Placement Behavior

Placement is direct in the 3D scene:

- Clicking the baseplate places at `z = 0`.
- Clicking an existing brick top proposes placement at the next stack level.
- Candidate poses always snap to LEGO grid coordinates `(x, y, z, ori)`.
- Rotation is limited to `ori = 0` and `ori = 1` to match the current Python model.
- The canvas shows a ghost brick before placement.
- Invalid candidates are highlighted and cannot be placed when they violate hard rules.

## Validation Rules

### Geometry

The editor checks in real time:

- Footprint stays inside the baseplate.
- Footprint does not overlap another brick at the same `z`.
- Rotation correctly swaps the footprint dimensions.
- All brick coordinates remain on the stud grid.

Geometry violations are hard errors and block placement.

### Support

For `z > 0`, the brick must have support from the layer below. The first version can implement a conservative rule:

- At least one occupied lower-layer stud must exist under the candidate footprint.
- If fewer than 25% of the candidate footprint studs are supported, show a low-support warning.
- Unsupported placements are hard errors and block placement.

This is structural support only, not physical stability.

### Construction Order

Each brick depends on lower-layer bricks touched by its footprint projection. A brick cannot be built before its dependencies.

The editor applies this in two places:

- During editing, obvious violations are blocked when a change would make lower-layer placement impossible under an already placed upper layer.
- During export, the editor builds a dependency graph and verifies order.

Export behavior:

- If `PlacementHistory` already satisfies dependencies, export it directly.
- If the history violates dependency order but the dependency graph can be topologically sorted, warn the user and export the safe sorted order.
- If no valid order can be produced, block export and highlight the related bricks.

This gives the user direct control while still preventing impossible build sequences.

## Export Format

`settings.json` is generated from final `SceneState.bricks`.

Each brick entry should include:

```json
{
  "id": "B001",
  "type": "lego_2x4",
  "grid": [22, 20, 0, 0],
  "color": [0.8, 0.1, 0.1, 1.0]
}
```

`task.json` is generated from placement order. The first version exports known placement data and explicitly marks press planning as incomplete:

```json
{
  "name": "custom_lego_task",
  "steps": [
    {
      "name": "place_B001",
      "object": "B001",
      "pick": {
        "grid": [7, 4, 0, 0],
        "press_side": null,
        "press_offset": null
      },
      "place": {
        "grid": [22, 20, 0, 0]
      },
      "planning": {
        "press_strategy": "unplanned"
      }
    }
  ]
}
```

This keeps the shape compatible with existing task files while making unfinished contact planning explicit. A later planner can fill `press_side` and `press_offset` without changing the editor's scene model.

## Technical Architecture

Create a new front-end package under `lego_editor/`.

Recommended stack:

- Vite
- React
- TypeScript
- Three.js through `@react-three/fiber`
- `@react-three/drei` for camera controls and scene helpers
- A small local store using Zustand or a React reducer

Core modules:

- `src/domain/brickSpecs.ts`: LEGO brick specs matching `lego_grid.py`.
- `src/domain/grid.ts`: stud pitch, footprint calculation, rotation, grid/world transforms.
- `src/domain/validators.ts`: geometry, support, and construction order validation.
- `src/domain/exporters.ts`: `settings.json` and `task.json` generation.
- `src/components/BrickLibrary.tsx`: left-panel brick selection and colors.
- `src/components/LegoScene.tsx`: 3D placement canvas.
- `src/components/Inspector.tsx`: selected brick details, legality, order, strategy, export.

The domain modules should be pure TypeScript where possible. This keeps core rules testable without rendering.

## Testing

Unit tests should cover:

- Footprint calculation for each brick type and orientation.
- Occupancy conflicts.
- Baseplate boundary checks.
- Support checks for stacked bricks.
- Construction dependency graph and topological sorting.
- Exported JSON shape for both `settings.json` and `task.json`.

Manual browser checks should cover:

- Place on baseplate.
- Rotate before placement.
- Stack on existing bricks.
- Attempt illegal overlap.
- Attempt unsupported placement.
- Delete or move a supporting brick.
- Export with valid placement history.
- Export after a reorderable history mismatch.

Optional repository-level check:

- Generate a sample config directory from the editor output.
- Load it with `maniskill_rm75_lego.lego_task_parser.load_task_config_dir`.
- Confirm the parser accepts the generated structure.

## Future Extensions

- Automatic task planner that fills press strategy and computes feasible pick/place details.
- Python backend validator that shares or compares rules with `lego_grid.py`.
- STL or GLB rendering for more faithful LEGO visuals.
- Import existing `config/*` tasks for review and editing.
- Physical stability validation using a backend or BrickSim integration.
- Robot execution preview using ManiSkill.
