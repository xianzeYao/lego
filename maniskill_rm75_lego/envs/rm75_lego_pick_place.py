from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sapien
import torch

from mani_skill.utils.registration import register_env
from mani_skill.utils.structs.pose import Pose

from maniskill_rm75_lego.envs.rm75_lego_smoke import RM75LegoSmokeEnv
from maniskill_rm75_lego.lego_grid import (
    BASEPLATE_HALF_THICKNESS,
    BRICK_BODY_HEIGHT,
    LEGO_1X1,
    LEGO_1X2,
    LEGO_1X4,
    LEGO_1X6,
    LEGO_1X8,
    LEGO_2X2,
    LEGO_2X4,
    LEGO_2X6,
    LEGO_2X8,
    LEGO_BRICK_SPECS,
    LEGO_MESH_DIR,
    LegoBrickSpec,
    LegoGridPose,
    STUD_HEIGHT,
    STUD_PITCH,
    apex_brick_actor_pose,
    apex_brick_bottom_pose,
    baseplate_origin_from_top,
    matrix_to_sapien_pose,
    plate_grid_point_world,
    press_point_grid,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ROBOT_DIGITAL_TWIN_URDF_DIR = REPO_ROOT / "generated_urdf" / "robot_digital_twin"
LEGO_1X2_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_1x2.urdf"
LEGO_1X4_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_1x4.urdf"
LEGO_1X6_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_1x6.urdf"
LEGO_1X8_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_1x8.urdf"
LEGO_1X1_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_1x1.urdf"
LEGO_2X2_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_2x2.urdf"
LEGO_2X4_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_2x4.urdf"
LEGO_2X6_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_2x6.urdf"
LEGO_2X8_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_2x8.urdf"
LEGO_BASEPLATE32_URDF_PATH = ROBOT_DIGITAL_TWIN_URDF_DIR / "lego_baseplate32.urdf"
LEGO_BRICK_URDF_PATHS = {
    spec.name: ROBOT_DIGITAL_TWIN_URDF_DIR / f"{spec.name}.urdf"
    for spec in LEGO_BRICK_SPECS
}

BASEPLATE32_MESH_PATH = LEGO_MESH_DIR / "base32x32.stl"
LEGO_1X2_MESH_PATH = LEGO_1X2.mesh_path
LEGO_1X4_MESH_PATH = LEGO_1X4.mesh_path
LEGO_2X4_MESH_PATH = LEGO_2X4.mesh_path

PLATE_SIZE_XY = (32, 32)
PLATE_TOP_POS = np.array([0.3, 0.0, 0.0032], dtype=np.float32)
PLATE_YAW = 0.0
PLATE_ORIGIN_POS = baseplate_origin_from_top(PLATE_TOP_POS).astype(np.float32)
PLATE_AXIS_VISUAL_Z_LIFT = 0.004
PLATE_AXIS_LENGTH = 0.08
PLATE_AXIS_THICKNESS = 0.0012

BRICK_MESH_SIZE = np.array([0.016, 0.008, 0.0112], dtype=np.float32)
BRICK_MESH_BOUNDS_MIN = np.array([-0.008, -0.004, -0.0096], dtype=np.float32)
BRICK_MESH_BOUNDS_MAX = np.array([0.008, 0.004, 0.0016], dtype=np.float32)
STUD_DIAMETER = 0.0048
STUD_MARKER_HEIGHT = 0.0018
BRICK_URDF_ORIGIN_Z_ON_GROUND = BRICK_BODY_HEIGHT


@dataclass(frozen=True)
class Stage2BrickPlacement:
    key: str
    brick: LegoBrickSpec
    grid: LegoGridPose
    color: tuple[float, float, float, float]

    @property
    def actor_name(self) -> str:
        return f"{self.key}_on_baseplate32"


STAGE2_BRICK_PLACEMENTS = (
    Stage2BrickPlacement(
        key="lego_1x4",
        brick=LEGO_1X4,
        grid=LegoGridPose(x=2, y=2, z=0, ori=0),
        color=(0.1, 0.75, 0.25, 1.0),
    ),
    Stage2BrickPlacement(
        key="lego_2x4",
        brick=LEGO_2X4,
        grid=LegoGridPose(x=14, y=15, z=0, ori=0),
        color=(0.95, 0.12, 0.08, 1.0),
    ),
)


def stage2_placement_by_key(key: str) -> Stage2BrickPlacement:
    for placement in STAGE2_BRICK_PLACEMENTS:
        if placement.key == key:
            return placement
    raise KeyError(key)


BRICK_INITIAL_POS = np.asarray(
    apex_brick_actor_pose(
        PLATE_TOP_POS,
        PLATE_SIZE_XY,
        LEGO_1X4,
        stage2_placement_by_key("lego_1x4").grid,
        PLATE_YAW,
    ).p,
    dtype=np.float32,
)
TARGET_GRID_POSE = LegoGridPose(x=14, y=15, z=1, ori=0)
TARGET_POS = np.asarray(
    apex_brick_actor_pose(PLATE_TOP_POS, PLATE_SIZE_XY, LEGO_1X4, TARGET_GRID_POSE, PLATE_YAW).p,
    dtype=np.float32,
)


def yaw_quat(yaw: float) -> list[float]:
    return [float(np.cos(yaw / 2.0)), 0.0, 0.0, float(np.sin(yaw / 2.0))]


def build_colored_mesh_actor(
    scene,
    name: str,
    mesh_path: Path,
    color,
    pose: sapien.Pose,
    body_type: str = "kinematic",
):
    builder = scene.create_actor_builder()
    material = sapien.render.RenderMaterial(base_color=color)
    builder.add_visual_from_file(
        filename=str(mesh_path),
        scale=[0.001, 0.001, 0.001],
        material=material,
    )
    builder.set_initial_pose(pose)
    if body_type == "static":
        return builder.build_static(name=name)
    if body_type == "kinematic":
        return builder.build_kinematic(name=name)
    return builder.build(name=name)


def build_axis_marker(scene, name: str, axis: str, length: float, thickness: float, color):
    builder = scene.create_actor_builder()
    material = sapien.render.RenderMaterial(base_color=color)
    if axis == "x":
        pose = sapien.Pose(p=[length / 2.0, 0.0, 0.0])
        half_size = [length / 2.0, thickness, thickness]
    elif axis == "y":
        pose = sapien.Pose(p=[0.0, length / 2.0, 0.0])
        half_size = [thickness, length / 2.0, thickness]
    elif axis == "z":
        pose = sapien.Pose(p=[0.0, 0.0, length / 2.0])
        half_size = [thickness, thickness, length / 2.0]
    else:
        raise ValueError(axis)
    builder.add_box_visual(pose=pose, half_size=half_size, material=material)
    builder.set_initial_pose(sapien.Pose())
    return builder.build_kinematic(name=name)


def baseplate_pose() -> sapien.Pose:
    return sapien.Pose(p=PLATE_ORIGIN_POS.tolist(), q=yaw_quat(PLATE_YAW))


def plate_axis_pose() -> sapien.Pose:
    pos = np.asarray(PLATE_TOP_POS, dtype=np.float64).copy()
    pos[2] += PLATE_AXIS_VISUAL_Z_LIFT
    return sapien.Pose(p=pos.tolist(), q=yaw_quat(PLATE_YAW))


def brick_pose_for_placement(placement: Stage2BrickPlacement) -> sapien.Pose:
    return apex_brick_actor_pose(
        PLATE_TOP_POS,
        PLATE_SIZE_XY,
        placement.brick,
        placement.grid,
        PLATE_YAW,
    )


def target_pose() -> sapien.Pose:
    return apex_brick_actor_pose(
        PLATE_TOP_POS,
        PLATE_SIZE_XY,
        LEGO_1X4,
        TARGET_GRID_POSE,
        PLATE_YAW,
    )


def describe_stage2_placements() -> list[dict]:
    rows = []
    for placement in STAGE2_BRICK_PLACEMENTS:
        bottom_pose = apex_brick_bottom_pose(
            PLATE_TOP_POS,
            PLATE_SIZE_XY,
            placement.brick,
            placement.grid,
            PLATE_YAW,
        )
        actor_pose = brick_pose_for_placement(placement)
        rows.append(
            {
                "key": placement.key,
                "studs": [placement.brick.studs_x, placement.brick.studs_y],
                "grid": [
                    placement.grid.x,
                    placement.grid.y,
                    placement.grid.z,
                    placement.grid.ori,
                ],
                "bottom_pos": np.asarray(bottom_pose[:3, 3], dtype=np.float64),
                "actor_pos": np.asarray(actor_pose.p, dtype=np.float64),
                "press_side_1_offset_0": press_point_grid(
                    placement.brick, placement.grid, press_side=1, press_offset=0
                ),
            }
        )
    return rows


def describe_plate_grid_points() -> list[dict]:
    points = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (31, 31, 0), (0, 0, 1)]
    return [
        {
            "grid": [x, y, z],
            "world": plate_grid_point_world(
                PLATE_TOP_POS, PLATE_SIZE_XY, x=x, y=y, z=z, plate_yaw=PLATE_YAW
            ),
        }
        for x, y, z in points
    ]


@register_env("RM75LegoPickPlace-v1", max_episode_steps=200)
class RM75LegoPickPlaceEnv(RM75LegoSmokeEnv):
    def _load_scene(self, options: dict):
        super()._load_scene(options)
        self.baseplate = build_colored_mesh_actor(
            self.scene,
            name="lego_baseplate32",
            mesh_path=BASEPLATE32_MESH_PATH,
            color=[0.06, 0.06, 0.06, 1.0],
            pose=baseplate_pose(),
            body_type="kinematic",
        )
        self.plate_axis_x = build_axis_marker(
            self.scene,
            name="stage2_plate_axis_x",
            axis="x",
            length=PLATE_AXIS_LENGTH,
            thickness=PLATE_AXIS_THICKNESS,
            color=[1.0, 0.0, 0.0, 0.9],
        )
        self.plate_axis_y = build_axis_marker(
            self.scene,
            name="stage2_plate_axis_y",
            axis="y",
            length=PLATE_AXIS_LENGTH,
            thickness=PLATE_AXIS_THICKNESS,
            color=[0.0, 1.0, 0.0, 0.9],
        )
        self.plate_axis_z = build_axis_marker(
            self.scene,
            name="stage2_plate_axis_z",
            axis="z",
            length=PLATE_AXIS_LENGTH,
            thickness=PLATE_AXIS_THICKNESS,
            color=[0.0, 0.2, 1.0, 0.9],
        )
        self.bricks = {}
        for placement in STAGE2_BRICK_PLACEMENTS:
            self.bricks[placement.key] = build_colored_mesh_actor(
                self.scene,
                name=placement.actor_name,
                mesh_path=placement.brick.mesh_path,
                color=placement.color,
                pose=brick_pose_for_placement(placement),
                body_type="kinematic",
            )
        self.brick = self.bricks["lego_1x4"]
        self.goal_marker = build_colored_mesh_actor(
            self.scene,
            color=[0.1, 0.9, 0.15, 0.35],
            name="lego_1x4_target_grid_marker",
            mesh_path=LEGO_1X4_MESH_PATH,
            pose=target_pose(),
            body_type="kinematic",
        )

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        super()._initialize_episode(env_idx, options)
        b = len(env_idx)
        self.baseplate.set_pose(Pose.create_from_pq(
            torch.as_tensor(PLATE_ORIGIN_POS, device=self.device, dtype=torch.float32).repeat(b, 1),
            torch.as_tensor(yaw_quat(PLATE_YAW), device=self.device, dtype=torch.float32).repeat(b, 1),
        ))
        axis_pose = plate_axis_pose()
        axis_p = torch.as_tensor(axis_pose.p, device=self.device, dtype=torch.float32).repeat(b, 1)
        axis_q = torch.as_tensor(axis_pose.q, device=self.device, dtype=torch.float32).repeat(b, 1)
        self.plate_axis_x.set_pose(Pose.create_from_pq(axis_p, axis_q))
        self.plate_axis_y.set_pose(Pose.create_from_pq(axis_p, axis_q))
        self.plate_axis_z.set_pose(Pose.create_from_pq(axis_p, axis_q))
        for placement in STAGE2_BRICK_PLACEMENTS:
            pose = brick_pose_for_placement(placement)
            self.bricks[placement.key].set_pose(Pose.create_from_pq(
                torch.as_tensor(pose.p, device=self.device, dtype=torch.float32).repeat(b, 1),
                torch.as_tensor(pose.q, device=self.device, dtype=torch.float32).repeat(b, 1),
            ))
        t_pose = target_pose()
        self.goal_marker.set_pose(Pose.create_from_pq(
            torch.as_tensor(t_pose.p, device=self.device, dtype=torch.float32).repeat(b, 1),
            torch.as_tensor(t_pose.q, device=self.device, dtype=torch.float32).repeat(b, 1),
        ))

    def stage2_plate_top_pose(self) -> sapien.Pose:
        return matrix_to_sapien_pose(
            np.array(
                [
                    [1.0, 0.0, 0.0, PLATE_TOP_POS[0]],
                    [0.0, 1.0, 0.0, PLATE_TOP_POS[1]],
                    [0.0, 0.0, 1.0, PLATE_TOP_POS[2]],
                    [0.0, 0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            )
        )
