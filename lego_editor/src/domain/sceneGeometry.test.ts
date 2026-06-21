import { describe, expect, it } from "vitest";

import { brickCenterWorld, worldPointToGrid } from "./sceneGeometry";

describe("scene geometry helpers", () => {
  const baseplate48 = { width: 48, depth: 48 };

  it("centers a 48x48 baseplate at grid 24,24", () => {
    expect(worldPointToGrid([0, 0], 0, 0, baseplate48)).toEqual([24, 24, 0, 0]);
  });

  it("computes brick center with a 48x48 baseplate offset", () => {
    expect(brickCenterWorld([24, 24, 0, 0], "lego_2x4", baseplate48)).toEqual([
      0.016,
      0.0048,
      0.008
    ]);
  });

  it("clamps pointer conversion to the 48x48 baseplate", () => {
    expect(worldPointToGrid([1, 1], 0, 1, baseplate48)).toEqual([47, 47, 0, 1]);
    expect(worldPointToGrid([-1, -1], 0, 1, baseplate48)).toEqual([0, 0, 0, 1]);
  });
});
