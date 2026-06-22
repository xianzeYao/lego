import { describe, expect, it } from "vitest";

import { LEGO_BRICK_SPECS } from "./brickSpecs";
import { exportSettings, exportTask } from "./exporters";
import { footprintStuds } from "./grid";
import { createSampleScene, type SampleDifficulty } from "./sampleScenes";
import type { BrickType } from "./types";
import { sortBuildOrder, validateCandidate } from "./validators";

const difficulties: SampleDifficulty[] = ["easy", "middle", "hard"];

describe("sample scenes", () => {
  it.each(difficulties)("exports a complete %s candidate task", (difficulty) => {
    const scene = createSampleScene(difficulty);
    const order = sortBuildOrder(scene);

    expect(order.ok).toBe(true);
    expect(order.brickIds).toHaveLength(scene.bricks.length);

    const settings = exportSettings(scene);
    const task = exportTask(scene, order.brickIds);

    expect(settings.initial_bricks).toHaveLength(scene.bricks.length);
    expect(task.steps).toHaveLength(scene.bricks.length);
    expect(task.steps.map((step) => step.place.grid)).toEqual(
      order.brickIds.map((brickId) => scene.bricks.find((brick) => brick.id === brickId)!.grid)
    );
    expect(task.steps.every((step) => step.pick.press_side >= 1 && step.pick.press_side <= 4)).toBe(true);
    if (difficulty === "easy") {
      expect(task.steps[0].pick.press_side).toBe(1);
    }
    expect(task.steps.every((step) => step.pick.press_offset != null)).toBe(true);
  });

  it.each(difficulties)("exports %s staging as grouped, legal pick grids", (difficulty) => {
    const scene = createSampleScene(difficulty);
    const order = sortBuildOrder(scene);
    expect(order.ok).toBe(true);

    const settings = exportSettings(scene);
    const task = exportTask(scene, order.brickIds);
    const settingById = new Map(settings.initial_bricks.map((brick) => [brick.id, brick]));
    const seenTypes = new Set<string>();
    const closedTypes = new Set<string>();
    const occupied = new Set<string>();

    for (const brick of settings.initial_bricks) {
      expect(closedTypes.has(brick.type)).toBe(false);
      for (const type of seenTypes) {
        if (type !== brick.type) {
          closedTypes.add(type);
        }
      }
      seenTypes.add(brick.type);

      expect(brick.grid[2]).toBeLessThanOrEqual(4);
      const studs = footprintStuds(LEGO_BRICK_SPECS[brick.type as BrickType], brick.grid);
      const insideStuds = studs.filter(
        ([x, y]) => x >= 0 && x < scene.baseplate.width && y >= 0 && y < scene.baseplate.depth
      );
      expect(insideStuds.length / studs.length).toBeGreaterThanOrEqual(0.8);

      for (const [x, y, z] of insideStuds) {
        const key = `${x}:${y}:${z}`;
        expect(occupied.has(key)).toBe(false);
        occupied.add(key);
      }
    }

    for (const step of task.steps) {
      expect(step.pick.grid).toEqual(settingById.get(step.object)?.grid);
    }
  });

  it.each(difficulties)("keeps %s sample placements valid as final geometry", (difficulty) => {
    const scene = createSampleScene(difficulty);

    for (const brick of scene.bricks) {
      const result = validateCandidate(
        { ...scene, bricks: scene.bricks.filter((item) => item.id !== brick.id) },
        { type: brick.type, grid: brick.grid }
      );
      expect(result.valid).toBe(true);
    }
  });

  it("keeps sample difficulties meaningfully separated", () => {
    const easy = createSampleScene("easy");
    const middle = createSampleScene("middle");
    const hard = createSampleScene("hard");

    expect(easy.bricks.length).toBeGreaterThanOrEqual(7);
    expect(middle.name).toContain("apex_mr");
    expect(middle.bricks.length).toBeGreaterThanOrEqual(18);
    expect(hard.name).toContain("camera");
    expect(hard.bricks.length).toBeGreaterThanOrEqual(24);
  });
});
