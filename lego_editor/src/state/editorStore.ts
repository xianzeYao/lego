import { LEGO_BRICK_SPECS } from "../domain/brickSpecs";
import { exportSettings, exportTask, type SettingsJson, type TaskJson } from "../domain/exporters";
import type {
  BrickInstance,
  BrickType,
  GridPose,
  RgbaColor,
  SceneState
} from "../domain/types";
import {
  sortBuildOrder,
  validateCandidate,
  type ValidationResult
} from "../domain/validators";

export type EditorState = {
  scene: SceneState;
  selectedType: BrickType;
  selectedColor: RgbaColor;
  selectedOrientation: 0 | 1;
  selectedBrickId: string | null;
  lastValidation: ValidationResult;
};

export type EditorAction =
  | { type: "selectType"; brickType: BrickType }
  | { type: "selectColor"; color: RgbaColor }
  | { type: "rotate" }
  | { type: "selectBrick"; brickId: string | null }
  | { type: "placeCandidate"; grid: GridPose }
  | { type: "removeBrick"; brickId: string }
  | {
      type: "updatePressStrategy";
      brickId: string;
      pressSide: number | null;
      pressOffset: [number, number] | null;
    };

export type ExportPayload =
  | {
      ok: true;
      reordered: boolean;
      settings: SettingsJson;
      task: TaskJson;
      errors: [];
    }
  | {
      ok: false;
      reordered: false;
      settings: SettingsJson;
      task: null;
      errors: string[];
    };

export const DEFAULT_COLORS: RgbaColor[] = [
  [0.8, 0.1, 0.1, 1],
  [0.1, 0.25, 0.85, 1],
  [0.95, 0.78, 0.15, 1],
  [0.12, 0.62, 0.32, 1],
  [0.95, 0.95, 0.95, 1],
  [0.08, 0.09, 0.12, 1]
];

const emptyValidation: ValidationResult = {
  valid: true,
  errors: [],
  warnings: []
};

export function createInitialEditorState(): EditorState {
  return {
    scene: {
      name: "custom_lego_task",
      baseplate: { width: 48, depth: 48 },
      bricks: [],
      placementHistory: []
    },
    selectedType: "lego_2x4",
    selectedColor: DEFAULT_COLORS[0],
    selectedOrientation: 0,
    selectedBrickId: null,
    lastValidation: emptyValidation
  };
}

function nextBrickId(bricks: BrickInstance[]): string {
  return `B${String(bricks.length + 1).padStart(3, "0")}`;
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "selectType":
      return { ...state, selectedType: action.brickType };
    case "selectColor":
      return { ...state, selectedColor: action.color };
    case "rotate":
      return {
        ...state,
        selectedOrientation: state.selectedOrientation === 0 ? 1 : 0
      };
    case "selectBrick":
      return { ...state, selectedBrickId: action.brickId };
    case "placeCandidate": {
      const grid: GridPose = [
        action.grid[0],
        action.grid[1],
        action.grid[2],
        state.selectedOrientation
      ];
      const validation = validateCandidate(state.scene, {
        type: state.selectedType,
        grid
      });

      if (!validation.valid) {
        return { ...state, lastValidation: validation };
      }

      const id = nextBrickId(state.scene.bricks);
      const placedAt = state.scene.placementHistory.length + 1;
      const brick: BrickInstance = {
        id,
        type: state.selectedType,
        grid,
        color: state.selectedColor,
        placedAt,
        pressSide: null,
        pressOffset: null
      };

      return {
        ...state,
        selectedBrickId: id,
        lastValidation: validation,
        scene: {
          ...state.scene,
          bricks: [...state.scene.bricks, brick],
          placementHistory: [
            ...state.scene.placementHistory,
            {
              stepId: `place_${id}`,
              brickId: id,
              type: brick.type,
              grid: brick.grid,
              timestamp: placedAt
            }
          ]
        }
      };
    }
    case "removeBrick": {
      const brick = state.scene.bricks.find((item) => item.id === action.brickId);
      if (!brick) {
        return state;
      }

      const wouldRemove = state.scene.bricks.filter(
        (item) => item.id !== action.brickId
      );
      const upperDependents = wouldRemove.filter((item) => {
        if (item.grid[2] <= brick.grid[2]) {
          return false;
        }
        const result = validateCandidate(
          { ...state.scene, bricks: wouldRemove.filter((other) => other.id !== item.id) },
          { type: item.type, grid: item.grid }
        );
        return !result.valid;
      });

      if (upperDependents.length > 0) {
        return {
          ...state,
          lastValidation: {
            valid: false,
            errors: [`Cannot remove ${brick.id}; it supports upper-layer bricks.`],
            warnings: []
          }
        };
      }

      return {
        ...state,
        selectedBrickId:
          state.selectedBrickId === action.brickId ? null : state.selectedBrickId,
        lastValidation: emptyValidation,
        scene: {
          ...state.scene,
          bricks: wouldRemove,
          placementHistory: state.scene.placementHistory.filter(
            (step) => step.brickId !== action.brickId
          )
        }
      };
    }
    case "updatePressStrategy":
      return {
        ...state,
        scene: {
          ...state.scene,
          bricks: state.scene.bricks.map((brick) =>
            brick.id === action.brickId
              ? {
                  ...brick,
                  pressSide: action.pressSide,
                  pressOffset: action.pressOffset
                }
              : brick
          )
        }
      };
    default:
      return state;
  }
}

export function selectedSpec(state: EditorState) {
  return LEGO_BRICK_SPECS[state.selectedType];
}

export function selectExportPayload(state: EditorState): ExportPayload {
  const settings = exportSettings(state.scene);
  const order = sortBuildOrder(state.scene);

  if (!order.ok) {
    return {
      ok: false,
      reordered: false,
      settings,
      task: null,
      errors: order.errors
    };
  }

  return {
    ok: true,
    reordered: order.reordered,
    settings,
    task: exportTask(state.scene, order.brickIds),
    errors: []
  };
}
