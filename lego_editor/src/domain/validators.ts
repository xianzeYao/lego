import { LEGO_BRICK_SPECS } from "./brickSpecs";
import { footprintStuds, isInsideBaseplate, occupancyKey } from "./grid";
import type { BrickInstance, BrickType, GridPose, SceneState, StudCoord } from "./types";

export type CandidatePlacement = {
  type: BrickType;
  grid: GridPose;
  ignoreBrickId?: string;
};

export type ValidationResult = {
  valid: boolean;
  errors: string[];
  warnings: string[];
};

export type BuildOrderResult = {
  ok: boolean;
  reordered: boolean;
  brickIds: string[];
  errors: string[];
};

function xyKey([x, y]: StudCoord): string {
  return `${x}:${y}`;
}

function brickFootprint(brick: BrickInstance): StudCoord[] {
  return footprintStuds(LEGO_BRICK_SPECS[brick.type], brick.grid);
}

function overlapCount(a: StudCoord[], b: StudCoord[]): number {
  const bKeys = new Set(b.map(xyKey));
  return a.filter((stud) => bKeys.has(xyKey(stud))).length;
}

export function validateCandidate(
  scene: SceneState,
  candidate: CandidatePlacement
): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  const candidateStuds = footprintStuds(
    LEGO_BRICK_SPECS[candidate.type],
    candidate.grid
  );
  const [, , z] = candidate.grid;
  const bricks = scene.bricks.filter((brick) => brick.id !== candidate.ignoreBrickId);

  if (!isInsideBaseplate(candidateStuds, scene.baseplate)) {
    errors.push("Footprint extends outside the baseplate.");
  }

  const occupiedSameLayer = new Map<string, BrickInstance>();
  for (const brick of bricks) {
    for (const stud of brickFootprint(brick)) {
      occupiedSameLayer.set(occupancyKey(stud), brick);
    }
  }

  for (const stud of candidateStuds) {
    const overlap = occupiedSameLayer.get(occupancyKey(stud));
    if (overlap) {
      errors.push(`Footprint overlaps ${overlap.id}.`);
      break;
    }
  }

  if (z > 0) {
    const lowerLayer = bricks.filter((brick) => brick.grid[2] === z - 1);
    const supportedStuds = lowerLayer.reduce(
      (count, brick) => count + overlapCount(candidateStuds, brickFootprint(brick)),
      0
    );
    const unsupportedStuds = candidateStuds.length - supportedStuds;

    if (supportedStuds === 0) {
      errors.push(`Stacked brick has no support from layer ${z - 1}.`);
    } else if (unsupportedStuds > 0) {
      errors.push(
        `Layer ${z} placement is missing lower support for ${unsupportedStuds} stud${unsupportedStuds === 1 ? "" : "s"}.`
      );
    }
  }

  for (const brick of bricks) {
    if (brick.grid[2] <= z) {
      continue;
    }
    if (overlapCount(candidateStuds, brickFootprint(brick)) > 0) {
      errors.push(`Cannot insert below existing upper brick ${brick.id}.`);
      break;
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings
  };
}

export function buildDependencyGraph(
  bricks: BrickInstance[]
): Map<string, Set<string>> {
  const graph = new Map<string, Set<string>>();

  for (const brick of bricks) {
    graph.set(brick.id, new Set<string>());
  }

  for (const brick of bricks) {
    const z = brick.grid[2];
    if (z === 0) {
      continue;
    }
    const footprint = brickFootprint(brick);
    for (const lower of bricks) {
      if (lower.id === brick.id || lower.grid[2] !== z - 1) {
        continue;
      }
      if (overlapCount(footprint, brickFootprint(lower)) > 0) {
        graph.get(brick.id)!.add(lower.id);
      }
    }
  }

  return graph;
}

export function sortBuildOrder(scene: SceneState): BuildOrderResult {
  const graph = buildDependencyGraph(scene.bricks);
  const byId = new Map(scene.bricks.map((brick) => [brick.id, brick]));
  const historyOrder = new Map(
    scene.placementHistory.map((step, index) => [step.brickId, index])
  );
  const remaining = new Set(scene.bricks.map((brick) => brick.id));
  const ordered: string[] = [];

  while (remaining.size > 0) {
    const ready = [...remaining]
      .filter((brickId) =>
        [...(graph.get(brickId) ?? [])].every((dependency) =>
          ordered.includes(dependency)
        )
      )
      .sort((a, b) => {
        const layerDelta = byId.get(a)!.grid[2] - byId.get(b)!.grid[2];
        if (layerDelta !== 0) {
          return layerDelta;
        }
        return (
          (historyOrder.get(a) ?? Number.MAX_SAFE_INTEGER) -
          (historyOrder.get(b) ?? Number.MAX_SAFE_INTEGER)
        );
      });

    if (ready.length === 0) {
      return {
        ok: false,
        reordered: false,
        brickIds: ordered,
        errors: ["Could not produce a valid construction order."]
      };
    }

    const next = ready[0];
    remaining.delete(next);
    ordered.push(next);
  }

  const original = scene.placementHistory.map((step) => step.brickId);
  const reordered =
    original.length !== ordered.length ||
    ordered.some((brickId, index) => brickId !== original[index]);

  return {
    ok: true,
    reordered,
    brickIds: ordered,
    errors: []
  };
}
