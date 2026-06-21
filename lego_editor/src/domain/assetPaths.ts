import type { BrickType } from "./types";

export const LEGO_ASSET_PATHS: Record<BrickType, string> = {
  lego_1x1: "/assets/lego/b1x1.stl",
  lego_1x2: "/assets/lego/b1x2.stl",
  lego_1x4: "/assets/lego/b1x4.stl",
  lego_1x6: "/assets/lego/b1x6.stl",
  lego_1x8: "/assets/lego/b1x8.stl",
  lego_2x2: "/assets/lego/b2x2.stl",
  lego_2x4: "/assets/lego/b2x4.stl",
  lego_2x6: "/assets/lego/b2x6.stl",
  lego_2x8: "/assets/lego/b2x8.stl"
};

export const BASEPLATE_ASSET_PATHS = {
  48: "/assets/lego/base48x48.stl"
} as const;
