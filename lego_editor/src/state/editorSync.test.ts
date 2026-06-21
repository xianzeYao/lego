import { describe, expect, it } from "vitest";

import { createInitialEditorState, editorReducer } from "./editorStore";
import {
  applySyncedScene,
  getSceneRevision,
  makeSyncedScenePayload
} from "./editorSync";

describe("editor sync payloads", () => {
  it("serializes scene state with a revision", () => {
    const state = editorReducer(createInitialEditorState(), {
      type: "placeCandidate",
      grid: [24, 24, 0, 0]
    });
    const payload = makeSyncedScenePayload(state, 7);

    expect(payload.revision).toBe(7);
    expect(payload.scene.bricks).toHaveLength(1);
    expect(payload.scene.placementHistory).toHaveLength(1);
  });

  it("applies a newer synced scene without changing selected tool controls", () => {
    const local = editorReducer(createInitialEditorState(), {
      type: "selectType",
      brickType: "lego_1x1"
    });
    const remote = editorReducer(createInitialEditorState(), {
      type: "placeCandidate",
      grid: [24, 24, 0, 0]
    });

    const updated = applySyncedScene(local, makeSyncedScenePayload(remote, 3));

    expect(updated.selectedType).toBe("lego_1x1");
    expect(updated.scene.bricks).toHaveLength(1);
    expect(getSceneRevision(updated)).toBe(3);
  });
});
