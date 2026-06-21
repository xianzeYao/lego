export type CameraViewId = "iso" | "top" | "front" | "right";

export type CameraView = {
  id: CameraViewId;
  label: string;
};

const CAMERA_POSITIONS: Record<CameraViewId, [number, number, number]> = {
  iso: [0.28, 0.28, 0.3],
  top: [0, 0.46, 0.001],
  front: [0, 0.14, 0.46],
  right: [0.46, 0.14, 0]
};

export const CAMERA_VIEWS: CameraView[] = [
  { id: "iso", label: "ISO" },
  { id: "top", label: "TOP" },
  { id: "front", label: "FRONT" },
  { id: "right", label: "RIGHT" }
];

export function cameraViewPosition(id: CameraViewId): [number, number, number] {
  return CAMERA_POSITIONS[id];
}
