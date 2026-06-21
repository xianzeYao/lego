import type { GridPose, SceneState } from "./types";

export type SettingsJson = {
  name: string;
  plate: {
    width: number;
    depth: number;
  };
  bricks: Array<{
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
      press_side: number | null;
      press_offset: [number, number] | null;
    };
    place: {
      grid: GridPose;
    };
    planning: {
      press_strategy: "unplanned" | "manual";
    };
  }>;
};

function defaultPickGrid(index: number): GridPose {
  return [2, 2 + index * 3, 0, 0];
}

export function exportSettings(scene: SceneState): SettingsJson {
  return {
    name: scene.name,
    plate: {
      width: scene.baseplate.width,
      depth: scene.baseplate.depth
    },
    bricks: scene.bricks.map((brick) => ({
      id: brick.id,
      type: brick.type,
      grid: brick.grid,
      color: brick.color
    }))
  };
}

export function exportTask(scene: SceneState, brickIds: string[]): TaskJson {
  const bricksById = new Map(scene.bricks.map((brick) => [brick.id, brick]));
  const historyById = new Map(
    scene.placementHistory.map((step, index) => [step.brickId, { step, index }])
  );

  return {
    name: scene.name,
    steps: brickIds.map((brickId, index) => {
      const brick = bricksById.get(brickId);
      if (!brick) {
        throw new Error(`Cannot export missing brick ${brickId}.`);
      }
      const history = historyById.get(brickId);
      const pressStrategy =
        brick.pressSide == null && brick.pressOffset == null ? "unplanned" : "manual";

      return {
        name: `place_${brick.id}`,
        object: brick.id,
        pick: {
          grid: history?.step.pickGrid ?? defaultPickGrid(history?.index ?? index),
          press_side: brick.pressSide ?? null,
          press_offset: brick.pressOffset ?? null
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
