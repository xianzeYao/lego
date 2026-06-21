export type CameraViewId = "iso" | "top" | "front" | "right" | "left" | "back";

export type CameraView = {
  id: CameraViewId;
  label: string;
};

const CAMERA_POSITIONS: Record<CameraViewId, [number, number, number]> = {
  iso: [0.28, 0.28, 0.3],
  top: [0, 0.46, 0.001],
  front: [0, 0.14, 0.46],
  right: [0.46, 0.14, 0],
  left: [-0.46, 0.14, 0],
  back: [0, 0.14, -0.46]
};

export const CAMERA_VIEWS: CameraView[] = [
  { id: "iso", label: "HOME" },
  { id: "top", label: "TOP" },
  { id: "front", label: "FRONT" },
  { id: "right", label: "RIGHT" },
  { id: "left", label: "LEFT" },
  { id: "back", label: "BACK" }
];

export function cameraViewPosition(id: CameraViewId): [number, number, number] {
  return CAMERA_POSITIONS[id];
}
