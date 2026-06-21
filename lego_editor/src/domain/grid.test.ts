import { describe, expect, it } from "vitest";

import { LEGO_BRICK_SPECS } from "./brickSpecs";
import {
  footprintStuds,
  gridToWorld,
  isInsideBaseplate,
  occupancyKey
} from "./grid";
import type { GridPose } from "./types";

describe("LEGO grid helpers", () => {
  const baseplate = { width: 32, depth: 32 };

  it("computes a 2x4 footprint in default orientation", () => {
    const spec = LEGO_BRICK_SPECS.lego_2x4;
    const grid: GridPose = [10, 12, 0, 0];

    expect(footprintStuds(spec, grid)).toEqual([
      [10, 12, 0],
      [10, 13, 0],
      [11, 12, 0],
      [11, 13, 0],
      [12, 12, 0],
      [12, 13, 0],
      [13, 12, 0],
      [13, 13, 0]
    ]);
  });

  it("swaps footprint dimensions when orientation is rotated", () => {
    const spec = LEGO_BRICK_SPECS.lego_2x4;
    const grid: GridPose = [10, 12, 0, 1];

    expect(footprintStuds(spec, grid)).toEqual([
      [10, 12, 0],
      [10, 13, 0],
      [10, 14, 0],
      [10, 15, 0],
      [11, 12, 0],
      [11, 13, 0],
      [11, 14, 0],
      [11, 15, 0]
    ]);
  });

  it("checks whether all footprint studs are inside the baseplate", () => {
    const spec = LEGO_BRICK_SPECS.lego_2x4;

    expect(isInsideBaseplate(footprintStuds(spec, [28, 30, 0, 0]), baseplate)).toBe(
      true
    );
    expect(isInsideBaseplate(footprintStuds(spec, [29, 30, 0, 0]), baseplate)).toBe(
      false
    );
  });

  it("creates stable occupancy keys", () => {
    expect(occupancyKey([3, 5, 2])).toBe("3:5:2");
  });

  it("maps grid coordinates to centered world coordinates", () => {
    expect(gridToWorld([16, 16, 0])).toEqual([0, 0, 0]);
    expect(gridToWorld([17, 16, 1])).toEqual([0.008, 0, 0.0096]);
  });
});
