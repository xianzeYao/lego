import { describe, expect, it } from "vitest";

import { LEGO_BRICK_SPECS } from "./brickSpecs";
import { footprintStuds } from "./grid";
import type { BrickInstance, BrickType, PlacementStep, SceneState } from "./types";
import { exportSettings, exportTask } from "./exporters";

const brick: BrickInstance = {
  id: "B001",
  type: "lego_2x4",
  grid: [22, 20, 0, 0],
  color: [0.8, 0.1, 0.1, 1],
  placedAt: 1
};

const history: PlacementStep[] = [
  {
    stepId: "step-1",
    brickId: "B001",
    type: "lego_2x4",
    grid: brick.grid,
    pickGrid: [7, 4, 0, 0],
    timestamp: 1
  }
];

const scene: SceneState = {
  name: "custom_lego_task",
  baseplate: { width: 48, depth: 48 },
  bricks: [brick],
  placementHistory: history
};

describe("exporters", () => {
  it("exports settings from generated initial staging positions", () => {
    expect(exportSettings(scene)).toEqual({
      name: "custom_lego_task",
      source: {
        format: "lego_editor"
      },
      plate: {
        plate_size_xy: [48, 48]
      },
      initial_bricks: [
        {
          id: "B001",
          type: "lego_2x4",
          grid: [7, 4, 0, 0],
          color: [0.8, 0.1, 0.1, 1]
        }
      ]
    });
  });

  it("exports task steps with unplanned press strategy fields", () => {
    expect(exportTask(scene, ["B001"])).toEqual({
      name: "custom_lego_task",
      steps: [
        {
          name: "place_B001",
          object: "B001",
          pick: {
            grid: [7, 4, 0, 0],
            press_side: 1,
            press_offset: [0, 1]
          },
          place: {
            grid: [22, 20, 0, 0]
          },
          planning: {
            press_strategy: "auto_candidate"
          }
        }
      ]
    });
  });

  it("uses deterministic staging pick grids when history has no pick grid", () => {
    const fallbackScene: SceneState = {
      ...scene,
      placementHistory: [{ ...history[0], pickGrid: undefined }]
    };

    expect(exportSettings(fallbackScene).initial_bricks[0].grid).toEqual([
      8, 2, 0, 0
    ]);
    expect(exportTask(fallbackScene, ["B001"]).steps[0].pick.grid).toEqual([
      8, 2, 0, 0
    ]);
  });

  it("groups staging bricks by type and moves from x=8 toward x=0", () => {
    const second: BrickInstance = {
      ...brick,
      id: "B002",
      type: "lego_1x2",
      grid: [26, 20, 0, 0],
      placedAt: 2
    };
    const third: BrickInstance = {
      ...brick,
      id: "B003",
      grid: [30, 20, 0, 0],
      placedAt: 3
    };
    const groupedScene: SceneState = {
      ...scene,
      bricks: [brick, second, third],
      placementHistory: []
    };

    expect(exportSettings(groupedScene).initial_bricks.map((item) => item.grid)).toEqual([
      [8, 2, 0, 0],
      [8, 9, 0, 0],
      [8, 13, 0, 0]
    ]);
  });

  it("keeps generated staging candidates non-overlapping, within five layers, and at least 80% on plate", () => {
    const bricks: BrickInstance[] = Array.from({ length: 30 }, (_, index) => ({
      id: `B${String(index + 1).padStart(3, "0")}`,
      type: index < 10 ? "lego_2x8" : index < 20 ? "lego_2x4" : "lego_1x2",
      grid: [10 + (index % 8), 12 + Math.floor(index / 8) * 3, 0, index % 2 === 0 ? 0 : 1],
      color: [0.8, 0.1, 0.1, 1],
      placedAt: index + 1
    }));
    const denseScene: SceneState = {
      name: "dense_scene",
      baseplate: { width: 48, depth: 48 },
      bricks,
      placementHistory: []
    };
    const settings = exportSettings(denseScene);
    const occupied = new Set<string>();

    for (const item of settings.initial_bricks) {
      expect(item.grid[2]).toBeLessThanOrEqual(4);
      const studs = footprintStuds(LEGO_BRICK_SPECS[item.type as BrickType], item.grid);
      const insideStuds = studs.filter(
        ([x, y]) => x >= 0 && x < denseScene.baseplate.width && y >= 0 && y < denseScene.baseplate.depth
      );
      expect(insideStuds.length / studs.length).toBeGreaterThanOrEqual(0.8);

      for (const [x, y, z] of studs) {
        if (x < 0 || x >= denseScene.baseplate.width || y < 0 || y >= denseScene.baseplate.depth) {
          continue;
        }
        const key = `${x}:${y}:${z}`;
        expect(occupied.has(key)).toBe(false);
        occupied.add(key);
      }
    }
  });

  it("prefers x-positive press side when the tool clearance corridor is open", () => {
    const result = exportTask(scene, ["B001"]);

    expect(result.steps[0].pick.press_side).toBe(1);
    expect(result.steps[0].pick.press_offset).toEqual([0, 1]);
  });

  it("chooses another press side when x-positive clearance would hit an already placed brick", () => {
    const placed: BrickInstance = {
      id: "B001",
      type: "lego_2x4",
      grid: [18, 10, 0, 0],
      color: [0.1, 0.25, 0.85, 1],
      placedAt: 1
    };
    const blocked: BrickInstance = {
      id: "B002",
      type: "lego_2x4",
      grid: [14, 10, 0, 0],
      color: [0.8, 0.1, 0.1, 1],
      placedAt: 2
    };
    const clearanceScene: SceneState = {
      name: "clearance_scene",
      baseplate: { width: 48, depth: 48 },
      bricks: [placed, blocked],
      placementHistory: [
        { stepId: "s1", brickId: "B001", type: placed.type, grid: placed.grid, timestamp: 1 },
        { stepId: "s2", brickId: "B002", type: blocked.type, grid: blocked.grid, timestamp: 2 }
      ]
    };

    const result = exportTask(clearanceScene, ["B001", "B002"]);

    expect(result.steps[1].pick.press_side).not.toBe(1);
    expect(result.steps[1].planning.press_strategy).toBe("auto_candidate");
  });

  it("treats lower-layer side bricks as tool long-edge blockers while ignoring direct supports", () => {
    const support: BrickInstance = {
      id: "B001",
      type: "lego_2x4",
      grid: [18, 18, 0, 0],
      color: [0.1, 0.25, 0.85, 1],
      placedAt: 1
    };
    const lowerSideBlocker: BrickInstance = {
      id: "B002",
      type: "lego_2x2",
      grid: [21, 20, 0, 0],
      color: [0.95, 0.78, 0.15, 1],
      placedAt: 2
    };
    const upper: BrickInstance = {
      id: "B003",
      type: "lego_2x2",
      grid: [19, 18, 1, 0],
      color: [0.8, 0.1, 0.1, 1],
      placedAt: 3
    };
    const longEdgeScene: SceneState = {
      name: "long_edge_blocker_scene",
      baseplate: { width: 48, depth: 48 },
      bricks: [support, lowerSideBlocker, upper],
      placementHistory: [
        { stepId: "s1", brickId: "B001", type: support.type, grid: support.grid, timestamp: 1 },
        { stepId: "s2", brickId: "B002", type: lowerSideBlocker.type, grid: lowerSideBlocker.grid, timestamp: 2 },
        { stepId: "s3", brickId: "B003", type: upper.type, grid: upper.grid, timestamp: 3 }
      ]
    };

    const result = exportTask(longEdgeScene, ["B001", "B002", "B003"]);

    expect(result.steps[2].pick.press_side).not.toBe(1);
  });

  it("keeps the preferred side with a backend-compatible press offset", () => {
    const support: BrickInstance = {
      id: "B001",
      type: "lego_2x4",
      grid: [19, 18, 0, 0],
      color: [0.1, 0.25, 0.85, 1],
      placedAt: 1
    };
    const sideBlocker: BrickInstance = {
      id: "B002",
      type: "lego_1x1",
      grid: [21, 21, 0, 0],
      color: [0.95, 0.78, 0.15, 1],
      placedAt: 2
    };
    const upper: BrickInstance = {
      id: "B003",
      type: "lego_2x8",
      grid: [19, 18, 1, 1],
      color: [0.8, 0.1, 0.1, 1],
      placedAt: 3
    };
    const offsetScene: SceneState = {
      name: "offset_candidate_scene",
      baseplate: { width: 48, depth: 48 },
      bricks: [support, sideBlocker, upper],
      placementHistory: [
        { stepId: "s1", brickId: "B001", type: support.type, grid: support.grid, timestamp: 1 },
        { stepId: "s2", brickId: "B002", type: sideBlocker.type, grid: sideBlocker.grid, timestamp: 2 },
        { stepId: "s3", brickId: "B003", type: upper.type, grid: upper.grid, timestamp: 3 }
      ]
    };

    const result = exportTask(offsetScene, ["B001", "B002", "B003"]);

    expect(result.steps[2].pick.press_side).toBe(1);
    expect(result.steps[2].pick.press_offset).toEqual([0, 1]);
  });
});
