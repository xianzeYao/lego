import { OrbitControls } from "@react-three/drei";
import { Canvas, ThreeEvent } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { LEGO_BRICK_SPECS } from "../domain/brickSpecs";
import { BRICK_BODY_HEIGHT, STUD_PITCH, footprintStuds } from "../domain/grid";
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

const STUD_HEIGHT = 0.0016;
const STUD_RADIUS = 0.0024;
const BASEPLATE_STUD_HEIGHT = 0.0009;
const BASEPLATE_STUD_RADIUS = 0.0018;

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

function brickCenter(grid: GridPose, type: BrickInstance["type"]): [number, number, number] {
  const size = dimensions({ type, grid });
  return [
    (grid[0] + size.widthStuds / 2 - 16) * STUD_PITCH,
    grid[2] * BRICK_BODY_HEIGHT + BRICK_BODY_HEIGHT / 2,
    (grid[1] + size.depthStuds / 2 - 16) * STUD_PITCH
  ];
}

function pointToGrid(point: THREE.Vector3, layer: number, orientation: 0 | 1): GridPose {
  return [
    Math.max(0, Math.min(31, Math.floor(point.x / STUD_PITCH + 16))),
    Math.max(0, Math.min(31, Math.floor(point.z / STUD_PITCH + 16))),
    layer,
    orientation
  ];
}

function BaseplateStuds() {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  useLayoutEffect(() => {
    if (!meshRef.current) {
      return;
    }
    let index = 0;
    for (let x = 0; x < 32; x += 1) {
      for (let y = 0; y < 32; y += 1) {
        dummy.position.set(
          (x + 0.5 - 16) * STUD_PITCH,
          BASEPLATE_STUD_HEIGHT / 2,
          (y + 0.5 - 16) * STUD_PITCH
        );
        dummy.updateMatrix();
        meshRef.current.setMatrixAt(index, dummy.matrix);
        index += 1;
      }
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [dummy]);

  return (
    <instancedMesh
      args={[undefined, undefined, 32 * 32]}
      ref={meshRef}
      raycast={() => null}
    >
      <cylinderGeometry
        args={[BASEPLATE_STUD_RADIUS, BASEPLATE_STUD_RADIUS, BASEPLATE_STUD_HEIGHT, 12]}
      />
      <meshStandardMaterial color="#7f8b9b" roughness={0.58} />
    </instancedMesh>
  );
}

function Studs({ brick }: { brick: BrickInstance }) {
  const studs = useMemo(() => footprintStuds(LEGO_BRICK_SPECS[brick.type], brick.grid), [brick]);
  const topY = brick.grid[2] * BRICK_BODY_HEIGHT + BRICK_BODY_HEIGHT + STUD_HEIGHT / 2;

  return (
    <>
      {studs.map(([x, y, z]) => (
        <mesh
          key={`${x}:${y}:${z}`}
          position={[(x + 0.5 - 16) * STUD_PITCH, topY, (y + 0.5 - 16) * STUD_PITCH]}
        >
          <cylinderGeometry args={[STUD_RADIUS, STUD_RADIUS, STUD_HEIGHT, 20]} />
          <meshStandardMaterial color={colorToThree(brick.color)} roughness={0.52} />
        </mesh>
      ))}
    </>
  );
}

function BrickMesh({
  brick,
  selected,
  onSelect,
  onTopClick,
  ghost = false,
  valid = true
}: {
  brick: BrickInstance;
  selected?: boolean;
  onSelect?: () => void;
  onTopClick?: (event: ScenePointerEvent, layer: number) => void;
  ghost?: boolean;
  valid?: boolean;
}) {
  const size = dimensions(brick);
  const color = ghost ? (valid ? "#2f80ed" : "#d64545") : colorToThree(brick.color);

  return (
    <group>
      <mesh
        position={brickCenter(brick.grid, brick.type)}
        raycast={ghost ? () => null : undefined}
        onClick={(event) => {
          event.stopPropagation();
          onSelect?.();
          onTopClick?.(event, brick.grid[2] + 1);
        }}
      >
        <boxGeometry args={[size.width, size.height, size.depth]} />
        <meshStandardMaterial
          color={color}
          opacity={ghost ? 0.38 : 1}
          transparent={ghost}
          roughness={0.48}
        />
      </mesh>
      {!ghost ? <Studs brick={brick} /> : null}
      {selected ? (
        <mesh position={brickCenter(brick.grid, brick.type)}>
          <boxGeometry args={[size.width + 0.001, size.height + 0.001, size.depth + 0.001]} />
          <meshBasicMaterial color="#111827" wireframe />
        </mesh>
      ) : null}
    </group>
  );
}

function SceneContent({ state, dispatch }: Props) {
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
    const grid = pointToGrid(event.point, layer, state.selectedOrientation);
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
      <directionalLight position={[0.15, 0.25, 0.18]} intensity={1.2} />
      <mesh
        position={[0, -0.0022, 0]}
        onPointerMove={(event) => updateHover(event, 0)}
        onClick={(event) => {
          event.stopPropagation();
          placeCandidate(candidateFromEvent(event, 0));
        }}
      >
        <boxGeometry args={[32 * STUD_PITCH, 0.0044, 32 * STUD_PITCH]} />
        <meshStandardMaterial color="#a7b0bd" roughness={0.64} />
      </mesh>
      <BaseplateStuds />
      {state.scene.bricks.map((brick) => (
        <BrickMesh
          brick={brick}
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
      {ghostBrick ? <BrickMesh brick={ghostBrick} ghost valid={hover?.valid ?? false} /> : null}
      <gridHelper args={[0.256, 32, "#4b5563", "#d9dde4"]} position={[0, 0.001, 0]} />
      <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.05} minDistance={0.18} />
    </>
  );
}

export function LegoScene({ state, dispatch }: Props) {
  return (
    <div className="scene-canvas">
      <Canvas
        camera={{ position: [0.2, 0.24, 0.24], fov: 42 }}
        gl={{ alpha: false, antialias: true }}
        onCreated={({ scene }) => {
          scene.background = new THREE.Color("#ffffff");
        }}
      >
        <SceneContent state={state} dispatch={dispatch} />
      </Canvas>
    </div>
  );
}
