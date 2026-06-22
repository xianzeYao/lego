import type { BrickInstance, BrickType, GridPose, RgbaColor, SceneState } from "./types";

export type SampleDifficulty = "easy" | "middle" | "hard";

const COLORS: RgbaColor[] = [
  [0.8, 0.1, 0.1, 1],
  [0.1, 0.25, 0.85, 1],
  [0.95, 0.78, 0.15, 1],
  [0.12, 0.62, 0.32, 1],
  [0.95, 0.95, 0.95, 1],
  [0.08, 0.09, 0.12, 1]
];

const RED: RgbaColor = [0.8, 0.1, 0.1, 1];
const BLUE: RgbaColor = [0.1, 0.25, 0.85, 1];
const YELLOW: RgbaColor = [0.95, 0.78, 0.15, 1];
const GREEN: RgbaColor = [0.12, 0.62, 0.32, 1];
const WHITE: RgbaColor = [0.95, 0.95, 0.95, 1];
const BLACK: RgbaColor = [0.08, 0.09, 0.12, 1];
const BROWN: RgbaColor = [0.48, 0.24, 0.08, 1];

function makeBrick(
  index: number,
  type: BrickType,
  grid: GridPose,
  color = COLORS[index % COLORS.length]
): BrickInstance {
  return {
    id: `B${String(index + 1).padStart(3, "0")}`,
    type,
    grid,
    color,
    placedAt: index + 1,
    pressSide: null,
    pressOffset: null
  };
}

function makeScene(name: string, bricks: BrickInstance[]): SceneState {
  return {
    name,
    baseplate: { width: 48, depth: 48 },
    bricks,
    placementHistory: bricks.map((brick) => ({
      stepId: `place_${brick.id}`,
      brickId: brick.id,
      type: brick.type,
      grid: brick.grid,
      timestamp: brick.placedAt
    }))
  };
}

export function createSampleScene(difficulty: SampleDifficulty): SceneState {
  if (difficulty === "easy") {
    return makeScene("lego_editor_easy_stepped_l_marker", [
      makeBrick(0, "lego_2x2", [12, 10, 0, 0], BLUE),
      makeBrick(1, "lego_2x2", [12, 18, 0, 0], BLUE),
      makeBrick(2, "lego_2x2", [12, 26, 0, 0], BLUE),
      makeBrick(3, "lego_2x2", [20, 26, 0, 0], YELLOW),
      makeBrick(4, "lego_2x2", [28, 26, 0, 0], YELLOW),
      makeBrick(5, "lego_2x2", [20, 18, 0, 0], WHITE),
      makeBrick(6, "lego_2x2", [28, 18, 0, 0], WHITE)
    ]);
  }

  if (difficulty === "middle") {
    return makeScene("lego_editor_middle_apex_mr_letters", [
      makeBrick(0, "lego_2x2", [4, 4, 0, 0], RED),
      makeBrick(1, "lego_2x2", [4, 12, 0, 0], RED),
      makeBrick(2, "lego_2x2", [4, 20, 0, 0], RED),
      makeBrick(3, "lego_2x2", [4, 28, 0, 0], RED),
      makeBrick(4, "lego_2x2", [20, 4, 0, 0], RED),
      makeBrick(5, "lego_2x2", [20, 12, 0, 0], RED),
      makeBrick(6, "lego_2x2", [20, 20, 0, 0], RED),
      makeBrick(7, "lego_2x2", [20, 28, 0, 0], RED),
      makeBrick(8, "lego_2x2", [8, 20, 0, 0], RED),
      makeBrick(9, "lego_2x2", [12, 12, 0, 0], RED),
      makeBrick(10, "lego_2x2", [16, 20, 0, 0], RED),
      makeBrick(11, "lego_2x2", [26, 4, 0, 0], GREEN),
      makeBrick(12, "lego_2x2", [26, 12, 0, 0], GREEN),
      makeBrick(13, "lego_2x2", [26, 20, 0, 0], GREEN),
      makeBrick(14, "lego_2x2", [26, 28, 0, 0], GREEN),
      makeBrick(15, "lego_2x2", [30, 28, 0, 0], GREEN),
      makeBrick(16, "lego_2x2", [30, 20, 0, 0], GREEN),
      makeBrick(17, "lego_2x2", [30, 4, 0, 0], GREEN)
    ]);
  }

  return makeScene("lego_editor_hard_pixel_camera", [
    makeBrick(0, "lego_2x2", [10, 12, 0, 0], BLACK),
    makeBrick(1, "lego_2x2", [14, 12, 0, 0], BLACK),
    makeBrick(2, "lego_2x2", [18, 12, 0, 0], BLACK),
    makeBrick(3, "lego_2x2", [22, 12, 0, 0], BLACK),
    makeBrick(4, "lego_2x2", [26, 12, 0, 0], BLACK),
    makeBrick(5, "lego_2x2", [30, 12, 0, 0], BLACK),
    makeBrick(6, "lego_2x2", [10, 16, 0, 0], BLUE),
    makeBrick(7, "lego_2x2", [14, 16, 0, 0], BLUE),
    makeBrick(8, "lego_2x2", [18, 16, 0, 0], BLACK),
    makeBrick(9, "lego_2x2", [22, 16, 0, 0], BLACK),
    makeBrick(10, "lego_2x2", [26, 16, 0, 0], BLUE),
    makeBrick(11, "lego_2x2", [30, 16, 0, 0], WHITE),
    makeBrick(12, "lego_2x2", [10, 20, 0, 0], BLUE),
    makeBrick(13, "lego_2x2", [14, 20, 0, 0], BLUE),
    makeBrick(14, "lego_2x2", [18, 20, 0, 0], BLACK),
    makeBrick(15, "lego_2x2", [22, 20, 0, 0], BLACK),
    makeBrick(16, "lego_2x2", [26, 20, 0, 0], BLUE),
    makeBrick(17, "lego_2x2", [30, 20, 0, 0], BLUE),
    makeBrick(18, "lego_2x2", [10, 24, 0, 0], BLACK),
    makeBrick(19, "lego_2x2", [14, 24, 0, 0], BLACK),
    makeBrick(20, "lego_2x2", [18, 24, 0, 0], BLACK),
    makeBrick(21, "lego_2x2", [22, 24, 0, 0], BLACK),
    makeBrick(22, "lego_2x2", [26, 24, 0, 0], BLACK),
    makeBrick(23, "lego_2x2", [30, 24, 0, 0], BLACK),
    makeBrick(24, "lego_1x4", [14, 8, 0, 0], RED),
    makeBrick(25, "lego_1x4", [22, 8, 0, 0], RED),
    makeBrick(26, "lego_2x2", [18, 16, 1, 0], WHITE),
    makeBrick(27, "lego_2x2", [22, 16, 1, 0], WHITE)
  ]);
}
