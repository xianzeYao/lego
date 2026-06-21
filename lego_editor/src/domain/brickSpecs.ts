import type { BrickSpec, BrickType } from "./types";

export const LEGO_BRICK_SPECS: Record<BrickType, BrickSpec> = {
  lego_1x1: { type: "lego_1x1", label: "1 x 1", studsX: 1, studsY: 1 },
  lego_1x2: { type: "lego_1x2", label: "1 x 2", studsX: 2, studsY: 1 },
  lego_1x4: { type: "lego_1x4", label: "1 x 4", studsX: 4, studsY: 1 },
  lego_1x6: { type: "lego_1x6", label: "1 x 6", studsX: 6, studsY: 1 },
  lego_1x8: { type: "lego_1x8", label: "1 x 8", studsX: 8, studsY: 1 },
  lego_2x2: { type: "lego_2x2", label: "2 x 2", studsX: 2, studsY: 2 },
  lego_2x4: { type: "lego_2x4", label: "2 x 4", studsX: 4, studsY: 2 },
  lego_2x6: { type: "lego_2x6", label: "2 x 6", studsX: 6, studsY: 2 },
  lego_2x8: { type: "lego_2x8", label: "2 x 8", studsX: 8, studsY: 2 }
};

export const BRICK_TYPES = Object.keys(LEGO_BRICK_SPECS) as BrickType[];
