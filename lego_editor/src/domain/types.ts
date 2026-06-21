export type BrickType =
  | "lego_1x1"
  | "lego_1x2"
  | "lego_1x4"
  | "lego_1x6"
  | "lego_1x8"
  | "lego_2x2"
  | "lego_2x4"
  | "lego_2x6"
  | "lego_2x8";

export type Orientation = 0 | 1;
export type GridPose = [x: number, y: number, z: number, ori: Orientation];
export type StudCoord = [x: number, y: number, z: number];
export type RgbaColor = [r: number, g: number, b: number, a: number];

export type BrickSpec = {
  type: BrickType;
  label: string;
  studsX: number;
  studsY: number;
};

export type BrickInstance = {
  id: string;
  type: BrickType;
  grid: GridPose;
  color: RgbaColor;
  placedAt: number;
  pressSide?: number | null;
  pressOffset?: [number, number] | null;
};

export type PlacementStep = {
  stepId: string;
  brickId: string;
  type: BrickType;
  grid: GridPose;
  pickGrid?: GridPose;
  timestamp: number;
};

export type SceneState = {
  name: string;
  baseplate: {
    width: number;
    depth: number;
  };
  bricks: BrickInstance[];
  placementHistory: PlacementStep[];
};
