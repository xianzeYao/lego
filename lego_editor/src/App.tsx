import { useReducer } from "react";

import { BrickLibrary } from "./components/BrickLibrary";
import { Inspector } from "./components/Inspector";
import { LegoScene } from "./components/LegoScene";
import { createInitialEditorState, editorReducer } from "./state/editorStore";

export default function App() {
  const [state, dispatch] = useReducer(editorReducer, undefined, createInitialEditorState);

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
