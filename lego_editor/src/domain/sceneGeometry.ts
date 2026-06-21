import { LEGO_BRICK_SPECS } from "./brickSpecs";
import { BRICK_BODY_HEIGHT, STUD_PITCH } from "./grid";
import type { BrickType, GridPose } from "./types";

export type BaseplateSize = {
  width: number;
  depth: number;
};

function roundMeters(value: number): number {
  return Number(value.toFixed(6));
}

export function worldPointToGrid(
  [worldX, worldZ]: [number, number],
  layer: number,
  orientation: 0 | 1,
  baseplate: BaseplateSize
): GridPose {
  return [
    Math.max(0, Math.min(baseplate.width - 1, Math.floor(worldX / STUD_PITCH + baseplate.width / 2))),
    Math.max(0, Math.min(baseplate.depth - 1, Math.floor(worldZ / STUD_PITCH + baseplate.depth / 2))),
    layer,
    orientation
  ];
}

export function brickCenterWorld(
  grid: GridPose,
  type: BrickType,
  baseplate: BaseplateSize
): [number, number, number] {
  const spec = LEGO_BRICK_SPECS[type];
  const widthStuds = grid[3] === 0 ? spec.studsX : spec.studsY;
  const depthStuds = grid[3] === 0 ? spec.studsY : spec.studsX;

  return [
    roundMeters((grid[0] + widthStuds / 2 - baseplate.width / 2) * STUD_PITCH),
    roundMeters(grid[2] * BRICK_BODY_HEIGHT + BRICK_BODY_HEIGHT / 2),
    roundMeters((grid[1] + depthStuds / 2 - baseplate.depth / 2) * STUD_PITCH)
  ];
}

export function brickAssetOriginWorld(
  grid: GridPose,
  type: BrickType,
  baseplate: BaseplateSize
): [number, number, number] {
  const [x, , z] = brickCenterWorld(grid, type, baseplate);
  return [x, roundMeters(grid[2] * BRICK_BODY_HEIGHT + BRICK_BODY_HEIGHT), z];
}
