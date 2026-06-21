import { describe, expect, it } from "vitest";

import type { BrickInstance, PlacementStep, SceneState } from "./types";
import {
  buildDependencyGraph,
  sortBuildOrder,
  validateCandidate
} from "./validators";

const red: [number, number, number, number] = [0.8, 0.1, 0.1, 1];
const blue: [number, number, number, number] = [0.1, 0.2, 0.8, 1];

function brick(
  id: string,
  grid: BrickInstance["grid"],
  placedAt: number,
  type: BrickInstance["type"] = "lego_2x4"
): BrickInstance {
  return { id, type, grid, color: placedAt % 2 === 0 ? red : blue, placedAt };
}

function scene(bricks: BrickInstance[], history: PlacementStep[] = []): SceneState {
  return {
    name: "test_scene",
    baseplate: { width: 32, depth: 32 },
    bricks,
    placementHistory: history
  };
}

describe("placement validation", () => {
  it("blocks same-layer footprint overlap", () => {
    const result = validateCandidate(scene([brick("B001", [4, 4, 0, 0], 1)]), {
      type: "lego_2x4",
      grid: [6, 4, 0, 0]
    });

    expect(result.valid).toBe(false);
    expect(result.errors).toContain("Footprint overlaps B001.");
  });

  it("blocks stacked placement with no lower support", () => {
    const result = validateCandidate(scene([]), {
      type: "lego_2x4",
      grid: [8, 8, 1, 0]
    });

    expect(result.valid).toBe(false);
    expect(result.errors).toContain("Stacked brick has no support from layer 0.");
  });

  it("allows stacked placement with lower support", () => {
    const result = validateCandidate(scene([brick("B001", [8, 8, 0, 0], 1)]), {
      type: "lego_2x4",
      grid: [8, 8, 1, 0]
    });

    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("blocks upper placements unless every projected stud is supported", () => {
    const result = validateCandidate(scene([brick("B001", [8, 8, 0, 0], 1)]), {
      type: "lego_2x8",
      grid: [8, 8, 1, 0]
    });

    expect(result.valid).toBe(false);
    expect(result.errors).toContain(
      "Layer 1 placement is missing lower support for 8 studs."
    );
  });

  it("blocks inserting a lower brick under an existing upper brick", () => {
    const result = validateCandidate(scene([brick("B002", [8, 8, 1, 0], 2)]), {
      type: "lego_2x4",
      grid: [8, 8, 0, 0]
    });

    expect(result.valid).toBe(false);
    expect(result.errors).toContain("Cannot insert below existing upper brick B002.");
  });
});

describe("construction order", () => {
  it("builds dependencies from lower-layer footprint contact", () => {
    const lower = brick("B001", [8, 8, 0, 0], 1);
    const upper = brick("B002", [9, 8, 1, 0], 2);

    const graph = buildDependencyGraph([upper, lower]);

    expect([...graph.get("B002")!]).toEqual(["B001"]);
    expect([...graph.get("B001")!]).toEqual([]);
  });

  it("sorts placement history into a buildable lower-before-upper order", () => {
    const lower = brick("B001", [8, 8, 0, 0], 1);
    const upper = brick("B002", [9, 8, 1, 0], 2);
    const history: PlacementStep[] = [
      { stepId: "s2", brickId: "B002", type: "lego_2x4", grid: upper.grid, timestamp: 2 },
      { stepId: "s1", brickId: "B001", type: "lego_2x4", grid: lower.grid, timestamp: 1 }
    ];

    const result = sortBuildOrder(scene([upper, lower], history));

    expect(result.ok).toBe(true);
    expect(result.reordered).toBe(true);
    expect(result.brickIds).toEqual(["B001", "B002"]);
  });
});
