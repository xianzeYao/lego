import { LEGO_BRICK_SPECS } from "./brickSpecs";
import { footprintStuds } from "./grid";
import type { BrickInstance, GridPose, SceneState } from "./types";

export type SettingsJson = {
  name: string;
  source: {
    format: "lego_editor";
  };
  plate: {
    plate_size_xy: [number, number];
  };
  initial_bricks: Array<{
    id: string;
    type: string;
    grid: GridPose;
    color: [number, number, number, number];
  }>;
};

export type TaskJson = {
  name: string;
  steps: Array<{
    name: string;
    object: string;
    pick: {
      grid: GridPose;
      press_side: number;
      press_offset: number | [number, number];
    };
    place: {
      grid: GridPose;
    };
    planning: {
      press_strategy: "auto_candidate" | "manual";
    };
  }>;
};

type PressOffset = number | [number, number];

function defaultPickGrid(index: number): GridPose {
  return [2, 2 + index * 3, 0, 0];
}

function brickDimensions(brick: Pick<BrickInstance, "type" | "grid">) {
  const spec = LEGO_BRICK_SPECS[brick.type];
  return {
    width: brick.grid[3] === 0 ? spec.studsX : spec.studsY,
    depth: brick.grid[3] === 0 ? spec.studsY : spec.studsX
  };
}

function countInsideStuds(grid: GridPose, width: number, depth: number, scene: SceneState) {
  let inside = 0;
  for (let dx = 0; dx < width; dx += 1) {
    for (let dy = 0; dy < depth; dy += 1) {
      const x = grid[0] + dx;
      const y = grid[1] + dy;
      if (x >= 0 && x < scene.baseplate.width && y >= 0 && y < scene.baseplate.depth) {
        inside += 1;
      }
    }
  }
  return inside;
}

function hasRequiredPlateCoverage(
  grid: GridPose,
  width: number,
  depth: number,
  scene: SceneState
) {
  return countInsideStuds(grid, width, depth, scene) / (width * depth) >= 0.8;
}

function reservedKeys(
  grid: GridPose,
  width: number,
  depth: number,
  scene: SceneState,
  padding: number
): string[] {
  const keys: string[] = [];
  for (let dx = -padding; dx < width + padding; dx += 1) {
    for (let dy = -padding; dy < depth + padding; dy += 1) {
      const x = grid[0] + dx;
      const y = grid[1] + dy;
      if (x >= 0 && x < scene.baseplate.width && y >= 0 && y < scene.baseplate.depth) {
        keys.push(`${x}:${y}:${grid[2]}`);
      }
    }
  }
  return keys;
}

function actualKeys(
  grid: GridPose,
  width: number,
  depth: number,
  scene: SceneState
): string[] {
  return reservedKeys(grid, width, depth, scene, 0);
}

function expandedFootprintKeys(
  grid: GridPose,
  width: number,
  depth: number,
  scene: SceneState,
  margin: number
): string[] {
  const keys: string[] = [];
  for (let dx = -margin; dx < width + margin; dx += 1) {
    for (let dy = -margin; dy < depth + margin; dy += 1) {
      const x = grid[0] + dx;
      const y = grid[1] + dy;
      if (x >= 0 && x < scene.baseplate.width && y >= 0 && y < scene.baseplate.depth) {
        keys.push(`${x}:${y}`);
      }
    }
  }
  return keys;
}

function finalAssemblySafetyKeysBeforeBrick(
  scene: SceneState,
  brickId: string,
  margin = 2
): Set<string> {
  const keys = new Set<string>();
  const rankByBrick = new Map(
    scene.placementHistory.map((step, index) => [step.brickId, index])
  );
  const currentRank = rankByBrick.get(brickId) ?? Number.MAX_SAFE_INTEGER;
  for (const brick of scene.bricks) {
    const brickRank = rankByBrick.get(brick.id) ?? brick.placedAt ?? Number.MAX_SAFE_INTEGER;
    if (brick.id === brickId || brickRank >= currentRank) {
      continue;
    }
    const { width, depth } = brickDimensions(brick);
    for (const key of expandedFootprintKeys(brick.grid, width, depth, scene, margin)) {
      keys.add(key);
    }
  }
  return keys;
}

function orderedStagingBricks(scene: SceneState): BrickInstance[] {
  const placementOrder = new Map(
    scene.placementHistory.map((step, index) => [step.brickId, index])
  );
  const typeOrder = new Map<string, number>();

  for (const brick of scene.bricks) {
    if (!typeOrder.has(brick.type)) {
      typeOrder.set(brick.type, typeOrder.size);
    }
  }

  return [...scene.bricks].sort((a, b) => {
    const typeDelta = typeOrder.get(a.type)! - typeOrder.get(b.type)!;
    if (typeDelta !== 0) {
      return typeDelta;
    }
    return (
      (placementOrder.get(a.id) ?? Number.MAX_SAFE_INTEGER) -
      (placementOrder.get(b.id) ?? Number.MAX_SAFE_INTEGER)
    );
  });
}

function historyPickGrids(scene: SceneState): Map<string, GridPose> {
  return new Map(
    scene.placementHistory
      .filter((step) => step.pickGrid)
      .map((step) => [step.brickId, step.pickGrid!])
  );
}

function generatedPickGrids(scene: SceneState): Map<string, GridPose> {
  const historyGrids = historyPickGrids(scene);
  const grids = new Map<string, GridPose>();
  const reserved = new Set<string>();
  let x = 8;
  let y = 2;
  let z = 0;
  let rowDepth = 0;
  let previousType: string | null = null;
  const sameTypeGap = scene.bricks.length >= 10 ? 1 : scene.bricks.length >= 6 ? 3 : 5;
  const typeGap = 2;
  const maxLayer = 4;
  const maxY = scene.bricks.length >= 12 ? Math.min(scene.baseplate.depth - 2, 32) : scene.baseplate.depth - 2;

  function reserve(grid: GridPose, width: number, depth: number) {
    for (const key of reservedKeys(grid, width, depth, scene, 1)) {
      reserved.add(key);
    }
  }

  function canPlace(grid: GridPose, width: number, depth: number, safetyKeys: Set<string>) {
    const footprintKeys = actualKeys(grid, width, depth, scene).map((key) => key.split(":").slice(0, 2).join(":"));
    return (
      hasRequiredPlateCoverage(grid, width, depth, scene) &&
      actualKeys(grid, width, depth, scene).every((key) => !reserved.has(key)) &&
      footprintKeys.every((key) => !safetyKeys.has(key))
    );
  }

  function nextRow() {
    x = 8;
    y += Math.max(rowDepth, 1) + sameTypeGap;
    rowDepth = 0;
  }

  function nextLayer() {
    x = 8;
    y = 2;
    z += 1;
    rowDepth = 0;
  }

  orderedStagingBricks(scene).forEach((brick) => {
    const historyGrid = historyGrids.get(brick.id);
    const { width, depth } = brickDimensions(brick);
    const assemblySafety = finalAssemblySafetyKeysBeforeBrick(scene, brick.id);
    if (historyGrid) {
      grids.set(brick.id, historyGrid);
      reserve(historyGrid, width, depth);
      return;
    }

    const gap = previousType === null || previousType === brick.type ? sameTypeGap : typeGap;
    const minX = Math.ceil(-width * 0.2);

    if (previousType !== null && previousType !== brick.type) {
      y += rowDepth + typeGap;
      x = 8;
      rowDepth = 0;
    }

    let candidate: GridPose = [x, y, z, brick.grid[3]];
    while (!canPlace(candidate, width, depth, assemblySafety)) {
      x -= 1;
      if (x < minX) {
        nextRow();
      }
      if (y + depth > maxY) {
        nextLayer();
      }
      if (z > maxLayer) {
        throw new Error(`Could not generate staging grid for ${brick.id}; staging exceeds 5 layers.`);
      }
      candidate = [x, y, z, brick.grid[3]];
    }

    grids.set(brick.id, candidate);
    reserve(candidate, width, depth);
    x -= width + gap;
    rowDepth = Math.max(rowDepth, depth);
    previousType = brick.type;
  });

  return grids;
}

function defaultPressOffset(brick: BrickInstance): PressOffset {
  return pressOffsetForSide(brick, 1);
}

function sideStudCount(brick: BrickInstance, pressSide: number): number {
  const spec = LEGO_BRICK_SPECS[brick.type];
  return pressSide === 1 || pressSide === 4 ? spec.studsY : spec.studsX;
}

function pressOffsetForSide(brick: BrickInstance, pressSide: number): PressOffset {
  const studCount = sideStudCount(brick, pressSide);
  if (studCount <= 1) {
    return 0;
  }
  const start = Math.max(0, Math.floor((studCount - 2) / 2));
  return [start, start + 1];
}

function pressOffsetCandidates(brick: BrickInstance, pressSide: number): PressOffset[] {
  const studCount = sideStudCount(brick, pressSide);
  if (studCount <= 1) {
    return [0];
  }
  return Array.from({ length: studCount - 1 }, (_, index) => [index, index + 1] as [number, number]);
}

function offsetIndices(offset: PressOffset): number[] {
  return Array.isArray(offset) ? offset : [offset];
}

function offsetCenterDistance(brick: BrickInstance, pressSide: number, offset: PressOffset): number {
  const indices = offsetIndices(offset);
  const selectedCenter = indices.reduce((sum, index) => sum + index, 0) / indices.length;
  return Math.abs(selectedCenter - (sideStudCount(brick, pressSide) - 1) / 2);
}

function directSupportIds(brick: BrickInstance, placedBricks: BrickInstance[]): Set<string> {
  const supportIds = new Set<string>();
  const z = brick.grid[2];
  if (z <= 0) {
    return supportIds;
  }

  const targetSupportKeys = new Set(
    footprintStuds(LEGO_BRICK_SPECS[brick.type], brick.grid).map(
      ([x, y]) => `${x}:${y}:${z - 1}`
    )
  );

  for (const placedBrick of placedBricks) {
    if (placedBrick.grid[2] !== z - 1) {
      continue;
    }
    const isSupport = footprintStuds(LEGO_BRICK_SPECS[placedBrick.type], placedBrick.grid).some(
      ([x, y, studZ]) => targetSupportKeys.has(`${x}:${y}:${studZ}`)
    );
    if (isSupport) {
      supportIds.add(placedBrick.id);
    }
  }

  return supportIds;
}

function occupiedToolSweepKeys(targetBrick: BrickInstance, placedBricks: BrickInstance[]): Set<string> {
  const keys = new Set<string>();
  const supportIds = directSupportIds(targetBrick, placedBricks);
  const targetZ = targetBrick.grid[2];
  for (const placedBrick of placedBricks) {
    if (placedBrick.grid[2] > targetZ) {
      continue;
    }
    if (supportIds.has(placedBrick.id)) {
      continue;
    }
    for (const [x, y] of footprintStuds(LEGO_BRICK_SPECS[placedBrick.type], placedBrick.grid)) {
      keys.add(`${x}:${y}`);
    }
  }
  return keys;
}

function toolClearanceKeys(brick: BrickInstance, pressSide: number, pressOffset: PressOffset): string[] {
  const { width, depth } = brickDimensions(brick);
  const [x, y] = brick.grid;
  const keys: string[] = [];
  const reach = 2;
  const indices = offsetIndices(pressOffset);
  const minOffset = Math.min(...indices);
  const maxOffset = Math.max(...indices);

  if (pressSide === 1) {
    const yStart = y + minOffset - 1;
    const yEnd = y + maxOffset + 1;
    for (let cx = x + width; cx < x + width + reach; cx += 1) {
      for (let cy = yStart; cy <= yEnd; cy += 1) {
        keys.push(`${cx}:${cy}`);
      }
    }
  } else if (pressSide === 4) {
    const yStart = y + minOffset - 1;
    const yEnd = y + maxOffset + 1;
    for (let cx = x - reach; cx < x; cx += 1) {
      for (let cy = yStart; cy <= yEnd; cy += 1) {
        keys.push(`${cx}:${cy}`);
      }
    }
  } else if (pressSide === 2) {
    const selectedXs = indices.map((offset) => x + width - 1 - offset);
    const xStart = Math.min(...selectedXs) - 1;
    const xEnd = Math.max(...selectedXs) + 1;
    for (let cy = y + depth; cy < y + depth + reach; cy += 1) {
      for (let cx = xStart; cx <= xEnd; cx += 1) {
        keys.push(`${cx}:${cy}`);
      }
    }
  } else if (pressSide === 3) {
    const selectedXs = indices.map((offset) => x + width - 1 - offset);
    const xStart = Math.min(...selectedXs) - 1;
    const xEnd = Math.max(...selectedXs) + 1;
    for (let cy = y - reach; cy < y; cy += 1) {
      for (let cx = xStart; cx <= xEnd; cx += 1) {
        keys.push(`${cx}:${cy}`);
      }
    }
  }

  return keys;
}

function chooseAutoPress(
  brick: BrickInstance,
  placedBricks: BrickInstance[],
  scene: SceneState
): { pressSide: number; pressOffset: number | [number, number] } {
  const occupied = occupiedToolSweepKeys(brick, placedBricks);
  const sidePreference = [1, 2, 3, 4];
  const sideScores = sidePreference.flatMap((pressSide, preferenceIndex) => {
    const { width, depth } = brickDimensions(brick);
    const [x, y] = brick.grid;
    const platePenalty =
      pressSide === 1
        ? Math.max(0, x + width + 2 - scene.baseplate.width)
        : pressSide === 4
          ? Math.max(0, 2 - x)
          : pressSide === 2
            ? Math.max(0, y + depth + 2 - scene.baseplate.depth)
            : Math.max(0, 2 - y);
    return pressOffsetCandidates(brick, pressSide).map((pressOffset) => {
      const clearanceHits = toolClearanceKeys(brick, pressSide, pressOffset).filter((key) =>
        occupied.has(key)
      ).length;
      return {
        pressSide,
        pressOffset,
        score: clearanceHits * 10 + platePenalty,
        offsetDistance: offsetCenterDistance(brick, pressSide, pressOffset),
        preferenceIndex
      };
    });
  });
  sideScores.sort(
    (a, b) =>
      a.score - b.score ||
      a.preferenceIndex - b.preferenceIndex ||
      a.offsetDistance - b.offsetDistance
  );
  const { pressSide, pressOffset } = sideScores[0];
  return {
    pressSide,
    pressOffset
  };
}

export function exportSettings(scene: SceneState): SettingsJson {
  const pickGrids = generatedPickGrids(scene);
  const bricks = orderedStagingBricks(scene);

  return {
    name: scene.name,
    source: {
      format: "lego_editor"
    },
    plate: {
      plate_size_xy: [scene.baseplate.width, scene.baseplate.depth]
    },
    initial_bricks: bricks.map((brick) => ({
      id: brick.id,
      type: brick.type,
      grid: pickGrids.get(brick.id) ?? defaultPickGrid(brick.placedAt - 1),
      color: brick.color
    }))
  };
}

export function exportTask(scene: SceneState, brickIds: string[]): TaskJson {
  const bricksById = new Map(scene.bricks.map((brick) => [brick.id, brick]));
  const pickGrids = generatedPickGrids(scene);
  const placedBricks: BrickInstance[] = [];

  return {
    name: scene.name,
    steps: brickIds.map((brickId, index) => {
      const brick = bricksById.get(brickId);
      if (!brick) {
        throw new Error(`Cannot export missing brick ${brickId}.`);
      }
      const autoPress = chooseAutoPress(brick, placedBricks, scene);
      const pressSide = brick.pressSide ?? autoPress.pressSide;
      const pressOffset = brick.pressOffset ?? autoPress.pressOffset ?? defaultPressOffset(brick);
      const pressStrategy =
        brick.pressSide == null && brick.pressOffset == null ? "auto_candidate" : "manual";
      placedBricks.push(brick);

      return {
        name: `place_${brick.id}`,
        object: brick.id,
        pick: {
          grid: pickGrids.get(brick.id) ?? defaultPickGrid(index),
          press_side: pressSide,
          press_offset: pressOffset
        },
        place: {
          grid: brick.grid
        },
        planning: {
          press_strategy: pressStrategy
        }
      };
    })
  };
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json"
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
