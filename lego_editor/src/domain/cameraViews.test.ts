import { describe, expect, it } from "vitest";

import { CAMERA_VIEWS, cameraViewPosition } from "./cameraViews";

describe("camera view presets", () => {
  it("defines Fusion-style named view presets", () => {
    expect(CAMERA_VIEWS.map((view) => view.id)).toEqual([
      "iso",
      "top",
      "front",
      "right"
    ]);
  });

  it("returns a stable camera position for the isometric view", () => {
    expect(cameraViewPosition("iso")).toEqual([0.28, 0.28, 0.3]);
  });
});
