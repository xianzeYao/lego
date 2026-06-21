import type { SceneState } from "../domain/types";
import type { EditorState } from "./editorStore";

export type SyncedScenePayload = {
  revision: number;
  scene: SceneState;
};

const sceneRevisions = new WeakMap<EditorState, number>();

export function getSceneRevision(state: EditorState): number {
  return sceneRevisions.get(state) ?? 0;
}

export function makeSyncedScenePayload(
  state: EditorState,
  revision: number
): SyncedScenePayload {
  return {
    revision,
    scene: state.scene
  };
}

export function applySyncedScene(
  state: EditorState,
  payload: SyncedScenePayload
): EditorState {
  const next = {
    ...state,
    selectedBrickId: payload.scene.bricks.some(
      (brick) => brick.id === state.selectedBrickId
    )
      ? state.selectedBrickId
      : null,
    scene: payload.scene
  };
  sceneRevisions.set(next, payload.revision);
  return next;
}

export function rememberSceneRevision(
  state: EditorState,
  revision: number
): EditorState {
  sceneRevisions.set(state, revision);
  return state;
}
