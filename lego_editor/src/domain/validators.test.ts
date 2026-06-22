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

  it("allows upper placements with partial lower support and warns when support is low", () => {
    const result = validateCandidate(
      scene([brick("B001", [8, 8, 0, 0], 1, "lego_1x1")]),
      {
        type: "lego_2x8",
        grid: [8, 8, 1, 0]
      }
    );

    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
    expect(result.warnings).toContain(
      "Layer 1 placement has low support: 1 of 16 studs."
    );
  });

  it("allows upper placements with at least one supported stud", () => {
    const result = validateCandidate(scene([brick("B001", [8, 8, 0, 0], 1)]), {
      type: "lego_2x4",
      grid: [11, 9, 1, 0]
    });

    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it("allows editing a lower brick under an existing upper brick", () => {
    const result = validateCandidate(scene([brick("B002", [8, 8, 1, 0], 2)]), {
      type: "lego_2x4",
      grid: [8, 8, 0, 0]
    });

    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
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

  it("orders same-layer bricks from smaller x to larger x", () => {
    const right = brick("B001", [12, 8, 0, 0], 1);
    const left = brick("B002", [4, 8, 0, 0], 2);
    const result = sortBuildOrder(scene([right, left], [
      { stepId: "s1", brickId: "B001", type: "lego_2x4", grid: right.grid, timestamp: 1 },
      { stepId: "s2", brickId: "B002", type: "lego_2x4", grid: left.grid, timestamp: 2 }
    ]));

    expect(result.ok).toBe(true);
    expect(result.brickIds).toEqual(["B002", "B001"]);
  });
});
