import { selectExportPayload, type EditorAction, type EditorState } from "../state/editorStore";
import { downloadJson } from "../domain/exporters";

type Props = {
  state: EditorState;
  dispatch: React.Dispatch<EditorAction>;
};

export function Inspector({ state, dispatch }: Props) {
  const selected = state.scene.bricks.find((brick) => brick.id === state.selectedBrickId);
  const exportPayload = selectExportPayload(state);

  return (
    <div className="inspector">
      <div className="panel-title">
        <h2>Inspector</h2>
        <span>{state.scene.bricks.length} bricks</span>
      </div>

      <section className="panel-section">
        <h3>Legality</h3>
        <div className={state.lastValidation.valid ? "status ok" : "status error"}>
          {state.lastValidation.valid ? "Placement valid" : "Placement blocked"}
        </div>
        {state.lastValidation.errors.map((error) => (
          <p className="message error" key={error}>
            {error}
          </p>
        ))}
        {state.lastValidation.warnings.map((warning) => (
          <p className="message warning" key={warning}>
            {warning}
          </p>
        ))}
      </section>

      <section className="panel-section">
        <h3>Selected Brick</h3>
        {selected ? (
          <div className="property-list">
            <span>ID</span>
            <strong>{selected.id}</strong>
            <span>Type</span>
            <strong>{selected.type}</strong>
            <span>Grid</span>
            <strong>[{selected.grid.join(", ")}]</strong>
            <button
              className="danger-button"
              type="button"
              onClick={() => dispatch({ type: "removeBrick", brickId: selected.id })}
            >
              Delete
            </button>
          </div>
        ) : (
          <p className="hint">Select a brick in the scene to inspect it.</p>
        )}
      </section>

      <section className="panel-section">
        <h3>Placement Order</h3>
        <ol className="order-list">
          {state.scene.placementHistory.map((step) => (
            <li key={step.stepId}>
              <button
                type="button"
                onClick={() => dispatch({ type: "selectBrick", brickId: step.brickId })}
              >
                {step.brickId}
              </button>
              <span>{step.type}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel-section">
        <h3>Export</h3>
        {exportPayload.ok && exportPayload.reordered ? (
          <p className="message warning">
            Task steps will be reordered into a lower-before-upper build order.
          </p>
        ) : null}
        {!exportPayload.ok
          ? exportPayload.errors.map((error) => (
              <p className="message error" key={error}>
                {error}
              </p>
            ))
          : null}
        <div className="export-actions">
          <button
            type="button"
            onClick={() => downloadJson("settings.json", exportPayload.settings)}
          >
            settings.json
          </button>
          <button
            disabled={!exportPayload.ok}
            type="button"
            onClick={() =>
              exportPayload.ok && downloadJson("task.json", exportPayload.task)
            }
          >
            task.json
          </button>
        </div>
      </section>
    </div>
  );
}
