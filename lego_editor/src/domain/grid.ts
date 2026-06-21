import type { BrickSpec, GridPose, StudCoord } from "./types";

export const STUD_PITCH = 0.008;
export const BRICK_BODY_HEIGHT = 0.0096;

export function footprintStuds(spec: BrickSpec, grid: GridPose): StudCoord[] {
  const [originX, originY, z, orientation] = grid;
  const width = orientation === 0 ? spec.studsX : spec.studsY;
  const depth = orientation === 0 ? spec.studsY : spec.studsX;
  const studs: StudCoord[] = [];

  for (let dx = 0; dx < width; dx += 1) {
    for (let dy = 0; dy < depth; dy += 1) {
      studs.push([originX + dx, originY + dy, z]);
    }
  }

  return studs;
}

export function isInsideBaseplate(
  studs: StudCoord[],
  baseplate: { width: number; depth: number }
): boolean {
  return studs.every(
    ([x, y]) => x >= 0 && y >= 0 && x < baseplate.width && y < baseplate.depth
  );
}

export function occupancyKey([x, y, z]: StudCoord): string {
  return `${x}:${y}:${z}`;
}

export function gridToWorld([x, y, z]: StudCoord): [number, number, number] {
  return [
    Number(((x - 16) * STUD_PITCH).toFixed(6)),
    Number(((y - 16) * STUD_PITCH).toFixed(6)),
    Number((z * BRICK_BODY_HEIGHT).toFixed(6))
  ];
}
