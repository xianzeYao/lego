import { OrbitControls } from "@react-three/drei";
import { Canvas, ThreeEvent, useFrame, useLoader } from "@react-three/fiber";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { Suspense, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { EDITOR_BUILD_ID } from "../buildInfo";
import { BASEPLATE_ASSET_PATHS, LEGO_ASSET_PATHS } from "../domain/assetPaths";
import { LEGO_BRICK_SPECS } from "../domain/brickSpecs";
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

function detectWebglSupport(): boolean {
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
      canvas
    });
    renderer.forceContextLoss();
    renderer.dispose();
    return true;
  } catch {
    return false;
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
  onSelect,
  onTopClick,
  ghost = false,
  valid = true
}: {
  brick: BrickInstance;
  baseplate: { width: number; depth: number };
  selected?: boolean;
  onSelect?: () => void;
  onTopClick?: (event: ScenePointerEvent, layer: number) => void;
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
        onClick={(event) => {
          event.stopPropagation();
          onSelect?.();
          onTopClick?.(event, brick.grid[2] + 1);
        }}
      >
        <planeGeometry args={[size.width, size.depth]} />
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

function SceneContent({
  state,
  dispatch,
  onRendered
}: Props & { onRendered: () => void }) {
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

  function candidateFromEvent(event: ScenePointerEvent, layer: number): HoverCandidate {
    const grid = worldPointToGrid(
      [event.point.x, event.point.z],
      layer,
      state.selectedOrientation,
      state.scene.baseplate
    );
    const validation = validateCandidate(state.scene, {
      type: state.selectedType,
      grid
    });
    return { grid, valid: validation.valid };
  }

  function updateHover(event: ScenePointerEvent, layer: number) {
    setHover(candidateFromEvent(event, layer));
  }

  function placeCandidate(candidate: HoverCandidate | null) {
    if (!candidate) {
      return;
    }
    dispatch({ type: "placeCandidate", grid: candidate.grid });
  }

  return (
    <>
      <ambientLight intensity={0.7} />
      <RenderReady onReady={onRendered} />
      <directionalLight position={[0.15, 0.25, 0.18]} intensity={1.2} />
      <BaseplateAsset baseplate={state.scene.baseplate} />
      <mesh
        position={[0, 0.002, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        onPointerMove={(event) => updateHover(event, 0)}
        onClick={(event) => {
          event.stopPropagation();
          placeCandidate(candidateFromEvent(event, 0));
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
          onSelect={() => dispatch({ type: "selectBrick", brickId: brick.id })}
          onTopClick={(event, layer) => {
            const candidate = candidateFromEvent(event, layer);
            setHover(candidate);
            placeCandidate(candidate);
          }}
        />
      ))}
      {ghostBrick ? (
        <BrickMesh
          brick={ghostBrick}
          baseplate={state.scene.baseplate}
          ghost
          valid={hover?.valid ?? false}
        />
      ) : null}
      <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.05} minDistance={0.22} />
    </>
  );
}

export function LegoScene({ state, dispatch }: Props) {
  const [sceneRendered, setSceneRendered] = useState(false);
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
