# LEGO Editor Optimization Pipeline

## One-command sample pipeline

From the repo root, run inside the existing conda env:

```bash
PYTHONPATH=/home/yxz/lego conda run -n maniskill4lego python -m maniskill_rm75_lego.lego_editor_pipeline --output-root /tmp/lego_editor_sample_optimized
```

By default this:

1. Regenerates `config/lego_editor_samples/{easy,middle,hard}` from the frontend sample scenes.
2. Runs the dry-run audit/optimization loop for every sample config directory.
3. Writes optimized configs under the output root, with one `final/` directory per sample.
4. Writes `/tmp/lego_editor_sample_optimized/pipeline_summary.json`.

To reuse existing JSON without re-exporting:

```bash
PYTHONPATH=/home/yxz/lego conda run -n maniskill4lego python -m maniskill_rm75_lego.lego_editor_pipeline --skip-export --output-root /tmp/lego_editor_sample_optimized
```

Extra runner arguments can be passed after `--`:

```bash
PYTHONPATH=/home/yxz/lego conda run -n maniskill4lego python -m maniskill_rm75_lego.lego_editor_pipeline --iterations 8 -- --steps-per-segment 12 --hold-steps 2
```

## Current rule-based export

The frontend only requires the user to build the final shape. `exportSettings` and `exportTask` then create a first candidate:

- The bundled samples are intentionally non-trivial smoke cases:
  - `easy`: 7-piece stepped L marker.
  - `middle`: 18-piece apex-style MR letters with 8-stud spacing.
  - `hard`: 28-piece pixel camera, including stacked lens highlights.
- `task.steps[*].place.grid` comes directly from the final scene.
- `settings.initial_bricks` is generated as staging pick locations.
- Staging groups identical brick types together.
- Bricks in each type group follow placement order.
- Staging scans from `x = 8` toward `x = 0`.
- Staging uses at most 5 layers.
- Each staged brick keeps at least 80% of studs inside the plate.
- Type groups are separated by a larger gap than same-type bricks.
- Larger samples cap generated staging rows before the far back of the plate, then continue on higher staging layers. This avoids the high-y pick poses that were repeatedly near the arm's IK boundary.
- Staging avoids already-planned final assembly footprints for earlier steps, so a later pick start is less likely to sit under the tool sweep of a brick that has already been placed.
- `task.steps[*].pick.grid` is copied from the staged setting.
- Initial `press_side`/`press_offset` prefers side `1` and centered offsets, then avoids obvious tool clearance corridors against already placed bricks.
- Build order is lower layers first, then same-layer smaller `x`, then smaller `y`.

## Current audit-feedback optimization

`task_optimization_loop` repeatedly runs `run_task_lego_robot.py --audit-tool-collisions` and updates the next candidate.

The loop treats these as separate failure classes:

- `place_down` / `place_press`: down-press tool clearance. The current press side becomes forbidden for that brick.
- `place_twist` / `place_up`: release/exit tool clearance. The current press side also becomes forbidden for that brick.
- `pre_pick` / `pick_down`: pick-side staging collision. The side is discouraged first; if repeated or exhausted, the pick grid is forbidden and the brick is restaged.
- IK failures: the current side is forbidden for the failed step.
- Tool-clearance pairs also create order hints. If the tool hits an already placed brick while placing a later brick, the optimizer records a preferred-before edge so the blocking brick can move later when dependencies allow it.

The scoring order is:

1. Fewer down-press tool collisions.
2. Fewer pick tool collisions.
3. Fewer release/exit tool collisions.
4. Runner success.
5. Earlier iteration.

Convergence requires runner success and zero collisions in all three tool-clearance classes.

## One-click optimizer path

The current loop is a deterministic repair search, but its inputs and histories are already shaped like an optimizer problem:

- Variables: task order among dependency-valid steps, staging grid, press side, press offset.
- Hard constraints: no same-layer overlap, support exists for stacked bricks, staging coverage >= 80%, max staging layer <= 4, runner IK succeeds, audit collisions are zero.
- Soft costs: staging compactness, fewer layers, larger clearance margins, shorter travel, centered press offsets, fewer side changes.
- Repair seed: start from the rule-based export, then reuse the loop histories as forbidden or discouraged assignments.
- Feedback state: forbidden place sides, discouraged pick sides, forbidden pick grids, preferred-before order hints, and exhausted restage bricks.

That gives us the practical one-click path we want: the editor exports the final shape, the rule layer creates a quick first `setting.json` and `task.json`, and the optimizer repeatedly repairs side/order/staging until the runner and audit agree. Later we can swap candidate generation from deterministic repair to local search, MILP/CP-SAT, or sampling, while keeping the same audit loop as the feasibility oracle.
