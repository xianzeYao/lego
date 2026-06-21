import { Html, OrbitControls } from "@react-three/drei";
import { Canvas, ThreeEvent, useFrame, useLoader, useThree } from "@react-three/fiber";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { EDITOR_BUILD_ID } from "../buildInfo";
import { BASEPLATE_ASSET_PATHS, LEGO_ASSET_PATHS } from "../domain/assetPaths";
import { LEGO_BRICK_SPECS } from "../domain/brickSpecs";
import { CAMERA_VIEWS, cameraViewPosition, type CameraViewId } from "../domain/cameraViews";
import {
  formatBooleanStatus,
  summarizeAssetStatus,
  webglUnavailableMessage
} from "../domain/clientDiagnostics";
import { BRICK_BODY_HEIGHT, STUD_PITCH, footprintStuds } from "../domain/grid";
import { brickAssetOriginWorld, brickCenterWorld, worldPointToGrid } from "../domain/sceneGeometry";
import type { BrickInstance, GridPose, RgbaColor } from "../domain/types";
import { validateCandidate } from "../domain/validators";
import type { EditorAction, EditorState } from "../state/editorStore";

type Props = {
  state: EditorState;
  dispatch: React.Dispatch<EditorAction>;
};

type HoverCandidate = {
  grid: GridPose;
  valid: boolean;
  messages: string[];
};
type ScenePointerEvent = ThreeEvent<MouseEvent | PointerEvent>;
type DiagnosticState = {
  webgl: boolean;
  rendererFrame: boolean;
  assetChecked: number;
  assetFailed: number;
  viewport: string;
};

const STL_SCALE = 0.001;
const PRELOAD_ASSET_PATHS = [
  BASEPLATE_ASSET_PATHS[48],
  ...Object.values(LEGO_ASSET_PATHS)
];
let cachedWebglSupport: boolean | null = null;

function detectWebglSupport(): boolean {
  if (cachedWebglSupport !== null) {
    return cachedWebglSupport;
  }

  if (typeof document === "undefined") {
    return false;
  }

  const previousConsoleError = console.error;
  try {
    const canvas = document.createElement("canvas");
    console.error = () => undefined;
    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      canvas,
      powerPreference: "high-performance"
    });
    renderer.dispose();
    cachedWebglSupport = true;
    return cachedWebglSupport;
  } catch {
    cachedWebglSupport = false;
    return cachedWebglSupport;
  } finally {
    console.error = previousConsoleError;
  }
}

function colorToThree(color: RgbaColor): string {
  const [r, g, b] = color;
  return new THREE.Color(r, g, b).getStyle();
}

function dimensions(brick: Pick<BrickInstance, "type" | "grid">) {
  const spec = LEGO_BRICK_SPECS[brick.type];
  const widthStuds = brick.grid[3] === 0 ? spec.studsX : spec.studsY;
  const depthStuds = brick.grid[3] === 0 ? spec.studsY : spec.studsX;
  return {
    widthStuds,
    depthStuds,
    width: widthStuds * STUD_PITCH,
    depth: depthStuds * STUD_PITCH,
    height: BRICK_BODY_HEIGHT
  };
}

function RenderReady({ onReady }: { onReady: () => void }) {
  const readyRef = useRef(false);

  useFrame(() => {
    if (readyRef.current) {
      return;
    }
    readyRef.current = true;
    onReady();
  });

  return null;
}

function AssetModel({
  path,
  color,
  opacity = 1
}: {
  path: string;
  color: string;
  opacity?: number;
}) {
  const geometry = useLoader(STLLoader, path);
  const prepared = useMemo(() => {
    const clone = geometry.clone();
    clone.rotateX(-Math.PI / 2);
    clone.computeVertexNormals();
    clone.computeBoundingBox();
    return clone;
  }, [geometry]);

  return (
    <mesh geometry={prepared} scale={STL_SCALE} raycast={() => null}>
      <meshStandardMaterial
        color={color}
        opacity={opacity}
        transparent={opacity < 1}
        roughness={0.48}
      />
    </mesh>
  );
}

function BaseplateAsset({ baseplate }: { baseplate: { width: number; depth: number } }) {
  return (
    <group position={[0, -0.0016, 0]}>
      <AssetModel path={BASEPLATE_ASSET_PATHS[48]} color="#8f9aa8" />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.0018, 0]}>
        <planeGeometry args={[baseplate.width * STUD_PITCH, baseplate.depth * STUD_PITCH]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
}

function preloadEditorAssets() {
  PRELOAD_ASSET_PATHS.forEach((path) => {
    useLoader.preload(STLLoader, path);
  });
}

function BrickMesh({
  brick,
  baseplate,
  selected,
  onTopHover,
  onTopClick,
  ghost = false,
  valid = true
}: {
  brick: BrickInstance;
  baseplate: { width: number; depth: number };
  selected?: boolean;
  onTopHover?: (event: ScenePointerEvent, layer: number, surfaceBrick: BrickInstance) => void;
  onTopClick?: (event: ScenePointerEvent, layer: number, surfaceBrick: BrickInstance) => void;
  ghost?: boolean;
  valid?: boolean;
}) {
  const size = dimensions(brick);
  const color = ghost ? (valid ? "#2f80ed" : "#d64545") : colorToThree(brick.color);
  const assetOrigin = brickAssetOriginWorld(brick.grid, brick.type, baseplate);
  const topCenter = brickCenterWorld(brick.grid, brick.type, baseplate);

  return (
    <group>
      <group
        position={assetOrigin}
        rotation={[0, brick.grid[3] === 0 ? 0 : Math.PI / 2, 0]}
      >
        <Suspense fallback={null}>
          <AssetModel
            path={LEGO_ASSET_PATHS[brick.type]}
            color={color}
            opacity={ghost ? 0.46 : 1}
          />
        </Suspense>
      </group>
      <mesh
        position={[topCenter[0], brick.grid[2] * BRICK_BODY_HEIGHT + BRICK_BODY_HEIGHT + 0.001, topCenter[2]]}
        rotation={[-Math.PI / 2, 0, 0]}
        raycast={ghost ? () => null : undefined}
        onPointerMove={(event) => {
          event.stopPropagation();
          onTopHover?.(event, brick.grid[2] + 1, brick);
        }}
        onClick={(event) => {
          event.stopPropagation();
          onTopClick?.(event, brick.grid[2] + 1, brick);
        }}
      >
        <planeGeometry args={[size.width + STUD_PITCH * 1.25, size.depth + STUD_PITCH * 1.25]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      {selected ? (
        <mesh position={brickCenterWorld(brick.grid, brick.type, baseplate)}>
          <boxGeometry args={[size.width + 0.001, size.height + 0.001, size.depth + 0.001]} />
          <meshBasicMaterial color="#111827" wireframe />
        </mesh>
      ) : null}
    </group>
  );
}

function PlacementLabel({
  candidate,
  selectedType,
  baseplate
}: {
  candidate: HoverCandidate;
  selectedType: BrickInstance["type"];
  baseplate: { width: number; depth: number };
}) {
  const [x, y, z] = candidate.grid;
  const position = brickCenterWorld(candidate.grid, selectedType, baseplate);
  const firstMessage = candidate.messages[0];

  return (
    <Html
      center
      position={[position[0], position[1] + BRICK_BODY_HEIGHT * 0.85, position[2]]}
      style={{ pointerEvents: "none" }}
    >
      <div className={candidate.valid ? "placement-label ok" : "placement-label error"}>
        <strong>{candidate.valid ? "Place" : "Blocked"}</strong>
        <span>[{x}, {y}, {z}]</span>
        {firstMessage ? <em>{firstMessage}</em> : null}
      </div>
    </Html>
  );
}

function SceneContent({
  state,
  dispatch,
  onRendered,
  activeCameraView
}: Props & { onRendered: () => void; activeCameraView: CameraViewId }) {
  const [hover, setHover] = useState<HoverCandidate | null>(null);
  const ghostBrick: BrickInstance | null = hover
    ? {
        id: "ghost",
        type: state.selectedType,
        grid: hover.grid,
        color: state.selectedColor,
        placedAt: 0
      }
    : null;

  function candidateFromEvent(
    event: ScenePointerEvent,
    layer: number,
    autoElevate = false,
    surfaceBrick?: BrickInstance
  ): HoverCandidate {
    const worldPoint: [number, number] = [event.point.x, event.point.z];

    const candidateFromGrid = (grid: GridPose): HoverCandidate => {
      const validation = validateCandidate(state.scene, {
        type: state.selectedType,
        grid
      });
      return {
        grid,
        valid: validation.valid,
        messages: [...validation.errors, ...validation.warnings]
      };
    };
    const makeCandidate = (candidateLayer: number): HoverCandidate =>
      candidateFromGrid(
        worldPointToGrid(
          worldPoint,
          candidateLayer,
          state.selectedOrientation,
          state.scene.baseplate
        )
      );

    if (surfaceBrick) {
      const directCandidate = makeCandidate(layer);
      if (directCandidate.valid) {
        return directCandidate;
      }

      return candidateFromGrid([
        surfaceBrick.grid[0],
        surfaceBrick.grid[1],
        layer,
        state.selectedOrientation
      ]);
    }

    if (autoElevate) {
      const maxLayer = Math.max(0, ...state.scene.bricks.map((brick) => brick.grid[2]));
      let lastCandidate = makeCandidate(layer);

      for (let candidateLayer = layer; candidateLayer <= maxLayer + 1; candidateLayer += 1) {
        const candidate = makeCandidate(candidateLayer);
        if (candidate.valid) {
          return candidate;
        }
        lastCandidate = candidate;
        const onlyBlockedBySameLayerOverlap =
          candidate.messages.length > 0 &&
          candidate.messages.every((message) => message.startsWith("Footprint overlaps"));
        if (!onlyBlockedBySameLayerOverlap) {
          return candidate;
        }
      }

      return lastCandidate;
    }

    const grid = worldPointToGrid(
      worldPoint,
      layer,
      state.selectedOrientation,
      state.scene.baseplate
    );
    const validation = validateCandidate(state.scene, {
      type: state.selectedType,
      grid
    });
    return {
      grid,
      valid: validation.valid,
      messages: [...validation.errors, ...validation.warnings]
    };
  }

  function updateHover(
    event: ScenePointerEvent,
    layer: number,
    autoElevate = false,
    surfaceBrick?: BrickInstance
  ) {
    setHover(candidateFromEvent(event, layer, autoElevate, surfaceBrick));
  }

  function placeCandidate(candidate: HoverCandidate | null) {
    if (!candidate) {
      return;
    }
    dispatch({ type: "placeCandidate", grid: candidate.grid });
    setHover(null);
  }

  return (
    <>
      <ambientLight intensity={0.7} />
      <RenderReady onReady={onRendered} />
      <CameraController activeView={activeCameraView} />
      <directionalLight position={[0.15, 0.25, 0.18]} intensity={1.2} />
      <BaseplateAsset baseplate={state.scene.baseplate} />
      <mesh
        position={[0, 0.002, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        onPointerMove={(event) => updateHover(event, 0, true)}
        onPointerLeave={() => setHover(null)}
        onClick={(event) => {
          event.stopPropagation();
          placeCandidate(candidateFromEvent(event, 0, true));
        }}
      >
        <planeGeometry
          args={[
            state.scene.baseplate.width * STUD_PITCH,
            state.scene.baseplate.depth * STUD_PITCH
          ]}
        />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      {state.scene.bricks.map((brick) => (
        <BrickMesh
          brick={brick}
          baseplate={state.scene.baseplate}
          key={brick.id}
          selected={state.selectedBrickId === brick.id}
          onTopHover={(event, layer, surfaceBrick) =>
            updateHover(event, layer, false, surfaceBrick)
          }
          onTopClick={(event, layer, surfaceBrick) => {
            const candidate = candidateFromEvent(event, layer, false, surfaceBrick);
            setHover(candidate);
            placeCandidate(candidate);
          }}
        />
      ))}
      {ghostBrick ? (
        <>
          <BrickMesh
            brick={ghostBrick}
            baseplate={state.scene.baseplate}
            ghost
            valid={hover?.valid ?? false}
          />
          {hover ? (
            <PlacementLabel
              candidate={hover}
              selectedType={state.selectedType}
              baseplate={state.scene.baseplate}
            />
          ) : null}
        </>
      ) : null}
    </>
  );
}

function CameraController({ activeView }: { activeView: CameraViewId }) {
  const { camera, controls } = useThree();
  const lastViewRef = useRef<CameraViewId | null>(null);

  useEffect(() => {
    if (lastViewRef.current === activeView) {
      return;
    }
    lastViewRef.current = activeView;
    const [x, y, z] = cameraViewPosition(activeView);
    camera.position.set(x, y, z);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();

    if (controls && "target" in controls) {
      const orbitControls = controls as unknown as {
        target: THREE.Vector3;
        update: () => void;
      };
      orbitControls.target.set(0, 0, 0);
      orbitControls.update();
    }
  }, [activeView, camera, controls]);

  return (
    <OrbitControls
      makeDefault
      enableDamping
      enablePan
      enableRotate
      enableZoom
      maxPolarAngle={Math.PI / 2.02}
      minDistance={0.12}
      maxDistance={0.9}
      mouseButtons={{
        LEFT: THREE.MOUSE.ROTATE,
        MIDDLE: THREE.MOUSE.PAN,
        RIGHT: THREE.MOUSE.PAN
      }}
      touches={{
        ONE: THREE.TOUCH.ROTATE,
        TWO: THREE.TOUCH.DOLLY_PAN
      }}
    />
  );
}

export function LegoScene({ state, dispatch }: Props) {
  const [sceneRendered, setSceneRendered] = useState(false);
  const [activeCameraView, setActiveCameraView] = useState<CameraViewId>("iso");
  const [diagnostics, setDiagnostics] = useState<DiagnosticState>(() => ({
    webgl: detectWebglSupport(),
    rendererFrame: false,
    assetChecked: 0,
    assetFailed: 0,
    viewport:
      typeof window === "undefined" ? "server" : `${window.innerWidth}x${window.innerHeight}`
  }));
  const webglWarning = webglUnavailableMessage(diagnostics.webgl);

  useLayoutEffect(() => {
    if (!diagnostics.webgl) {
      return;
    }
    preloadEditorAssets();
  }, [diagnostics.webgl]);

  useLayoutEffect(() => {
    const updateViewport = () => {
      const webgl = detectWebglSupport();
      setDiagnostics((current) => ({
        ...current,
        webgl,
        viewport: `${window.innerWidth}x${window.innerHeight}`
      }));
    };

    updateViewport();
    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  useLayoutEffect(() => {
    let cancelled = false;
    const paths = [
      BASEPLATE_ASSET_PATHS[48],
      ...state.scene.bricks.map((brick) => LEGO_ASSET_PATHS[brick.type]),
      LEGO_ASSET_PATHS[state.selectedType]
    ];
    const uniquePaths = [...new Set(paths)];

    Promise.all(
      uniquePaths.map(async (path) => {
        try {
          const response = await fetch(path, { method: "HEAD" });
          return response.ok;
        } catch {
          return false;
        }
      })
    ).then((results) => {
      if (cancelled) {
        return;
      }
      setDiagnostics((current) => ({
        ...current,
        assetChecked: results.length,
        assetFailed: results.filter((ok) => !ok).length
      }));
    });

    return () => {
      cancelled = true;
    };
  }, [state.scene.bricks, state.selectedType]);

  return (
    <div className="scene-canvas">
      <div className="scene-diagnostics">
        <strong>{EDITOR_BUILD_ID}</strong>
        <span>viewport {diagnostics.viewport}</span>
        <span>webgl {formatBooleanStatus(diagnostics.webgl)}</span>
        <span>frame {formatBooleanStatus(diagnostics.rendererFrame)}</span>
        <span>
          assets{" "}
          {summarizeAssetStatus({
            checked: diagnostics.assetChecked,
            failed: diagnostics.assetFailed
          })}
        </span>
      </div>
      <div className="view-cube" aria-label="Camera views">
        {CAMERA_VIEWS.map((view) => (
          <button
            aria-pressed={activeCameraView === view.id}
            className={activeCameraView === view.id ? "active" : ""}
            key={view.id}
            type="button"
            onClick={() => setActiveCameraView(view.id)}
          >
            {view.label}
          </button>
        ))}
      </div>
      <div
        className={
          sceneRendered
            ? "scene-baseplate-fallback hidden"
            : "scene-baseplate-fallback"
        }
        aria-hidden="true"
      />
      {webglWarning ? (
        <div className="scene-webgl-warning" role="status">
          <strong>WebGL unavailable</strong>
          <span>{webglWarning}</span>
        </div>
      ) : (
        <Canvas
          camera={{ position: [0.28, 0.28, 0.3], fov: 38 }}
          gl={{ alpha: true, antialias: true }}
          onCreated={({ scene }) => {
            scene.background = null;
          }}
        >
          <SceneContent
            state={state}
            dispatch={dispatch}
            activeCameraView={activeCameraView}
            onRendered={() => {
              setSceneRendered(true);
              setDiagnostics((current) => ({ ...current, rendererFrame: true }));
            }}
          />
        </Canvas>
      )}
    </div>
  );
}
