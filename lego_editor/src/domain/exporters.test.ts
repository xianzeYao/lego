import { describe, expect, it } from "vitest";

import type { BrickInstance, PlacementStep, SceneState } from "./types";
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
  it("exports settings from the final scene", () => {
    expect(exportSettings(scene)).toEqual({
      name: "custom_lego_task",
      plate: {
        width: 48,
        depth: 48
      },
      bricks: [
        {
          id: "B001",
          type: "lego_2x4",
          grid: [22, 20, 0, 0],
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
            press_side: null,
            press_offset: null
          },
          place: {
            grid: [22, 20, 0, 0]
          },
          planning: {
            press_strategy: "unplanned"
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

    expect(exportTask(fallbackScene, ["B001"]).steps[0].pick.grid).toEqual([
      2, 2, 0, 0
    ]);
  });
});
