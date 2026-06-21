import { useEffect, useReducer, useRef } from "react";

import { BrickLibrary } from "./components/BrickLibrary";
import { Inspector } from "./components/Inspector";
import { LegoScene } from "./components/LegoScene";
import { createInitialEditorState, editorReducer } from "./state/editorStore";
import { makeSyncedScenePayload } from "./state/editorSync";

export default function App() {
  const [state, dispatch] = useReducer(editorReducer, undefined, createInitialEditorState);
  const hydratedRef = useRef(false);
  const knownRevisionRef = useRef(0);
  const skipNextPostRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function loadSharedState() {
      const response = await fetch("/api/editor-state");
      if (!response.ok || cancelled) {
        return;
      }
      const payload = await response.json();
      hydratedRef.current = true;
      if (payload.scene && payload.revision > knownRevisionRef.current) {
        knownRevisionRef.current = payload.revision;
        skipNextPostRef.current = true;
        dispatch({
          type: "replaceScene",
          scene: payload.scene,
          revision: payload.revision
        });
      }
    }

    loadSharedState().catch(() => {
      hydratedRef.current = true;
    });

    const interval = window.setInterval(() => {
      loadSharedState().catch(() => undefined);
    }, 1000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!hydratedRef.current) {
      return;
    }

    if (skipNextPostRef.current) {
      skipNextPostRef.current = false;
      return;
    }

    const nextRevision = knownRevisionRef.current + 1;
    knownRevisionRef.current = nextRevision;

    fetch("/api/editor-state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(makeSyncedScenePayload(state, nextRevision))
    }).catch(() => undefined);
  }, [state.scene]);

  return (
    <main className="app-shell">
      <aside className="panel panel-left">
        <BrickLibrary state={state} dispatch={dispatch} />
      </aside>
      <section className="scene-shell">
        <LegoScene state={state} dispatch={dispatch} />
      </section>
      <aside className="panel panel-right">
        <Inspector state={state} dispatch={dispatch} />
      </aside>
    </main>
  );
}
