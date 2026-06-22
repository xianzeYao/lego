import { BRICK_TYPES, LEGO_BRICK_SPECS } from "../domain/brickSpecs";
import { createSampleScene, type SampleDifficulty } from "../domain/sampleScenes";
import { EDITOR_BUILD_ID } from "../buildInfo";
import type { EditorAction, EditorState } from "../state/editorStore";
import { DEFAULT_COLORS } from "../state/editorStore";

type Props = {
  state: EditorState;
  dispatch: React.Dispatch<EditorAction>;
};

function rgbaToCss(color: [number, number, number, number]): string {
  const [r, g, b, a] = color;
  return `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(
    b * 255
  )}, ${a})`;
}

export function BrickLibrary({ state, dispatch }: Props) {
  const samples: Array<{ id: SampleDifficulty; label: string }> = [
    { id: "easy", label: "Easy" },
    { id: "middle", label: "Middle" },
    { id: "hard", label: "Hard" }
  ];

  return (
    <div className="library">
      <div className="panel-title">
        <h1>LEGO Editor</h1>
        <span>{EDITOR_BUILD_ID}</span>
      </div>

      <section className="panel-section">
        <h2>Brick Type</h2>
        <div className="brick-type-grid">
          {BRICK_TYPES.map((type) => (
            <button
              className={type === state.selectedType ? "tool-button active" : "tool-button"}
              key={type}
              type="button"
              onClick={() => dispatch({ type: "selectType", brickType: type })}
            >
              {LEGO_BRICK_SPECS[type].label}
            </button>
          ))}
        </div>
      </section>

      <section className="panel-section">
        <h2>Color</h2>
        <div className="color-row">
          {DEFAULT_COLORS.map((color) => (
            <button
              aria-label={`Select color ${rgbaToCss(color)}`}
              className={
                color === state.selectedColor ? "color-swatch active" : "color-swatch"
              }
              key={rgbaToCss(color)}
              style={{ background: rgbaToCss(color) }}
              type="button"
              onClick={() => dispatch({ type: "selectColor", color })}
            />
          ))}
        </div>
      </section>

      <section className="panel-section">
        <h2>Placement</h2>
        <div className="selected-summary">
          <span>Scene</span>
          <strong>{state.scene.bricks.length} bricks synced</strong>
        </div>
        <div className="selected-summary">
          <span>Selected</span>
          <strong>{LEGO_BRICK_SPECS[state.selectedType].label}</strong>
        </div>
        <div className="segmented-control">
          <button
            className={state.selectedOrientation === 0 ? "active" : ""}
            type="button"
            onClick={() =>
              state.selectedOrientation === 1 && dispatch({ type: "rotate" })
            }
          >
            0 deg
          </button>
          <button
            className={state.selectedOrientation === 1 ? "active" : ""}
            type="button"
            onClick={() =>
              state.selectedOrientation === 0 && dispatch({ type: "rotate" })
            }
          >
            90 deg
          </button>
        </div>
        <p className="hint">
          Click the baseplate or an existing brick top to place. Left drag rotates,
          middle/right drag pans, wheel zooms, and the view cube switches camera
          direction.
        </p>
      </section>

      <section className="panel-section">
        <h2>Samples</h2>
        <div className="sample-actions">
          {samples.map((sample) => (
            <button
              key={sample.id}
              type="button"
              onClick={() =>
                dispatch({
                  type: "replaceScene",
                  scene: createSampleScene(sample.id),
                  revision: 0
                })
              }
            >
              {sample.label}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
