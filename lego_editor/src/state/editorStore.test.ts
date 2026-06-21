import { describe, expect, it } from "vitest";

import { createInitialEditorState, editorReducer, selectExportPayload } from "./editorStore";

describe("editor reducer", () => {
  it("places a valid baseplate brick and records history", () => {
    const state = editorReducer(createInitialEditorState(), {
      type: "placeCandidate",
      grid: [4, 4, 0, 0]
    });

    expect(state.scene.bricks).toHaveLength(1);
    expect(state.scene.bricks[0]).toMatchObject({
      id: "B001",
      type: "lego_2x4",
      grid: [4, 4, 0, 0]
    });
    expect(state.scene.placementHistory).toHaveLength(1);
    expect(state.lastValidation.valid).toBe(true);
  });

  it("does not place an invalid overlapping brick", () => {
    const withBrick = editorReducer(createInitialEditorState(), {
      type: "placeCandidate",
      grid: [4, 4, 0, 0]
    });
    const overlapped = editorReducer(withBrick, {
      type: "placeCandidate",
      grid: [5, 4, 0, 0]
    });

    expect(overlapped.scene.bricks).toHaveLength(1);
    expect(overlapped.lastValidation.valid).toBe(false);
    expect(overlapped.lastValidation.errors[0]).toContain("Footprint overlaps");
  });

  it("prepares export payload with a buildable order", () => {
    const base = editorReducer(createInitialEditorState(), {
      type: "placeCandidate",
      grid: [4, 4, 0, 0]
    });
    const stacked = editorReducer(base, {
      type: "placeCandidate",
      grid: [4, 4, 1, 0]
    });

    const payload = selectExportPayload(stacked);

    expect(payload.ok).toBe(true);
    expect(payload.task?.steps.map((step) => step.object)).toEqual(["B001", "B002"]);
  });

  it("places the currently selected type on a supported upper layer", () => {
    const selected = editorReducer(createInitialEditorState(), {
      type: "selectType",
      brickType: "lego_1x1"
    });
    const lower = editorReducer(selected, {
      type: "placeCandidate",
      grid: [24, 24, 0, 0]
    });

    const placed = editorReducer(lower, {
      type: "placeCandidate",
      grid: [24, 24, 1, 0]
    });

    expect(placed.scene.bricks).toHaveLength(2);
    expect(placed.scene.bricks[1]).toMatchObject({
      id: "B002",
      type: "lego_1x1",
      grid: [24, 24, 1, 0]
    });
  });
});
