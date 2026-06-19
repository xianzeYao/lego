from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sapien
from scipy.spatial.transform import Rotation


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGO_MESH_DIR = (
    REPO_ROOT / "third_party" / "Robot_Digital_Twin" / "gazebo" / "meshes" / "lego"
)

STUD_PITCH = 0.008
BRICK_BODY_HEIGHT = 0.0096
STUD_HEIGHT = 0.0016
BRICK_BOTTOM_LOCAL_Z = -BRICK_BODY_HEIGHT
BASEPLATE_HALF_THICKNESS = 0.0016


@dataclass(frozen=True)
class LegoBrickSpec:
    name: str
    studs_x: int
    studs_y: int
    mesh_name: str

    @property
    def mesh_path(self) -> Path:
        return LEGO_MESH_DIR / self.mesh_name


LEGO_1X1 = LegoBrickSpec("lego_1x1", studs_x=1, studs_y=1, mesh_name="b1x1.stl")
LEGO_1X2 = LegoBrickSpec("lego_1x2", studs_x=2, studs_y=1, mesh_name="b1x2.stl")
LEGO_1X4 = LegoBrickSpec("lego_1x4", studs_x=4, studs_y=1, mesh_name="b1x4.stl")
LEGO_1X6 = LegoBrickSpec("lego_1x6", studs_x=6, studs_y=1, mesh_name="b1x6.stl")
LEGO_1X8 = LegoBrickSpec("lego_1x8", studs_x=8, studs_y=1, mesh_name="b1x8.stl")
LEGO_2X2 = LegoBrickSpec("lego_2x2", studs_x=2, studs_y=2, mesh_name="b2x2.stl")
LEGO_2X4 = LegoBrickSpec("lego_2x4", studs_x=4, studs_y=2, mesh_name="b2x4.stl")
LEGO_2X6 = LegoBrickSpec("lego_2x6", studs_x=6, studs_y=2, mesh_name="b2x6.stl")
LEGO_2X8 = LegoBrickSpec("lego_2x8", studs_x=8, studs_y=2, mesh_name="b2x8.stl")

LEGO_BRICK_SPECS = (
    LEGO_1X1,
    LEGO_1X2,
    LEGO_1X4,
    LEGO_1X6,
    LEGO_1X8,
    LEGO_2X2,
    LEGO_2X4,
    LEGO_2X6,
    LEGO_2X8,
)


@dataclass(frozen=True)
class LegoGridPose:
    x: int
    y: int
    z: int = 0
    ori: int = 0


@dataclass(frozen=True)
class LegoPickTarget:
    contact_pose: np.ndarray
    contact_point: np.ndarray
    selected_stud_centers: np.ndarray
    stud_pair_center: np.ndarray
    edge_point: np.ndarray
    outward_normal: np.ndarray
    tangent: np.ndarray


def yaw_matrix(yaw: float) -> np.ndarray:
    c = float(np.cos(yaw))
    s = float(np.sin(yaw))
    mat = np.eye(4, dtype=np.float64)
    mat[:3, :3] = [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
    return mat


def translation_matrix(xyz) -> np.ndarray:
    mat = np.eye(4, dtype=np.float64)
    mat[:3, 3] = np.asarray(xyz, dtype=np.float64)
    return mat


def matrix_to_sapien_pose(mat: np.ndarray) -> sapien.Pose:
    rot = mat[:3, :3]
    qx, qy, qz, qw = Rotation.from_matrix(rot).as_quat()
    return sapien.Pose(p=mat[:3, 3].tolist(), q=[float(qw), float(qx), float(qy), float(qz)])


def brick_origin_from_bottom_pose(bottom_pose: np.ndarray) -> np.ndarray:
    return bottom_pose @ translation_matrix([0.0, 0.0, -BRICK_BOTTOM_LOCAL_Z])


def baseplate_origin_from_top(plate_top_pos) -> np.ndarray:
    pos = np.asarray(plate_top_pos, dtype=np.float64).copy()
    pos[2] -= BASEPLATE_HALF_THICKNESS
    return pos


def plate_grid_point_world(
    plate_top_pos,
    plate_size_xy: tuple[int, int],
    x: int,
    y: int,
    z: int = 0,
    plate_yaw: float = 0.0,
) -> np.ndarray:
    plate_width_x, plate_width_y = plate_size_xy
    refpose = translation_matrix(plate_top_pos) @ yaw_matrix(plate_yaw)
    local = np.array(
        [
            x * STUD_PITCH - (plate_width_x * STUD_PITCH) / 2.0,
            y * STUD_PITCH - (plate_width_y * STUD_PITCH) / 2.0,
            z * BRICK_BODY_HEIGHT,
            1.0,
        ],
        dtype=np.float64,
    )
    return (refpose @ local)[:3]


def apex_brick_bottom_pose(
    plate_top_pos,
    plate_size_xy: tuple[int, int],
    brick: LegoBrickSpec,
    grid: LegoGridPose,
    plate_yaw: float = 0.0,
) -> np.ndarray:
    """Port of APEX-MR calc_brick_loc for the brick bottom frame.

    The returned frame is centered at the brick bottom. Its local x/y axes follow the
    LEGO brick studs. The brick mesh origin is BRICK_BODY_HEIGHT above this frame.
    """
    plate_width_x, plate_width_y = plate_size_xy
    refpose = translation_matrix(plate_top_pos) @ yaw_matrix(plate_yaw)
    topleft_offset = translation_matrix(
        [
            -(plate_width_x * STUD_PITCH) / 2.0,
            -(plate_width_y * STUD_PITCH) / 2.0,
            0.0,
        ]
    )
    brick_offset = translation_matrix(
        [
            grid.x * STUD_PITCH,
            grid.y * STUD_PITCH,
            grid.z * BRICK_BODY_HEIGHT,
        ]
    )

    if grid.ori == 0:
        brick_center_offset = translation_matrix(
            [
                brick.studs_x * STUD_PITCH / 2.0,
                brick.studs_y * STUD_PITCH / 2.0,
                0.0,
            ]
        )
        return refpose @ topleft_offset @ brick_offset @ brick_center_offset
    if grid.ori == 1:
        brick_center_offset = translation_matrix(
            [
                brick.studs_x * STUD_PITCH / 2.0,
                -brick.studs_y * STUD_PITCH / 2.0,
                0.0,
            ]
        )
        return refpose @ topleft_offset @ brick_offset @ yaw_matrix(np.pi / 2.0) @ brick_center_offset
    raise ValueError(f"Unsupported LEGO orientation {grid.ori}; expected 0 or 1")


def apex_brick_actor_pose(
    plate_top_pos,
    plate_size_xy: tuple[int, int],
    brick: LegoBrickSpec,
    grid: LegoGridPose,
    plate_yaw: float = 0.0,
) -> sapien.Pose:
    bottom_pose = apex_brick_bottom_pose(
        plate_top_pos=plate_top_pos,
        plate_size_xy=plate_size_xy,
        brick=brick,
        grid=grid,
        plate_yaw=plate_yaw,
    )
    return matrix_to_sapien_pose(brick_origin_from_bottom_pose(bottom_pose))


def brick_stud_centers_world(
    plate_top_pos,
    plate_size_xy: tuple[int, int],
    brick: LegoBrickSpec,
    grid: LegoGridPose,
    plate_yaw: float = 0.0,
) -> np.ndarray:
    bottom_pose = apex_brick_bottom_pose(
        plate_top_pos=plate_top_pos,
        plate_size_xy=plate_size_xy,
        brick=brick,
        grid=grid,
        plate_yaw=plate_yaw,
    )
    centers = []
    for ix in range(brick.studs_x):
        for iy in range(brick.studs_y):
            local = np.array(
                [
                    -brick.studs_x * STUD_PITCH / 2.0 + (ix + 0.5) * STUD_PITCH,
                    -brick.studs_y * STUD_PITCH / 2.0 + (iy + 0.5) * STUD_PITCH,
                    BRICK_BODY_HEIGHT + STUD_HEIGHT,
                    1.0,
                ],
                dtype=np.float64,
            )
            centers.append((bottom_pose @ local)[:3])
    return np.asarray(centers, dtype=np.float64)


def pick_target_from_press_side(
    plate_top_pos,
    plate_size_xy: tuple[int, int],
    brick: LegoBrickSpec,
    grid: LegoGridPose,
    press_side: int,
    press_offset: int | list[int] | tuple[int, ...],
    plate_yaw: float = 0.0,
) -> LegoPickTarget:
    """Compute the top-view pick target used by the LEGO tool.

    The selected studs are reported at the stud top for visualization/reference.
    The actual contact point is on the brick top plane beside those studs,
    matching the calibrated tool contact frame rather than the stud cap height.
    """
    bottom_pose = apex_brick_bottom_pose(
        plate_top_pos=plate_top_pos,
        plate_size_xy=plate_size_xy,
        brick=brick,
        grid=grid,
        plate_yaw=plate_yaw,
    )
    length = brick.studs_x * STUD_PITCH
    width = brick.studs_y * STUD_PITCH
    stud_z = BRICK_BODY_HEIGHT + STUD_HEIGHT
    contact_z = BRICK_BODY_HEIGHT

    def selected_offsets(stud_count: int) -> tuple[int, ...]:
        if isinstance(press_offset, int):
            offsets = (press_offset,)
        elif isinstance(press_offset, (list, tuple)):
            offsets = tuple(int(offset) for offset in press_offset)
        else:
            raise TypeError(
                f"press_offset must be an int or a list of two adjacent ints, got {type(press_offset).__name__}"
            )
        if len(offsets) not in (1, 2):
            raise ValueError(f"press_offset={press_offset!r} must select one stud or two adjacent studs")
        if len(offsets) == 1 and stud_count > 1:
            raise ValueError(
                f"press_offset={press_offset!r} selects one stud on side {press_side} of {brick.name}, "
                f"but that side has {stud_count} studs; use two adjacent stud indices"
            )
        if any(offset < 0 for offset in offsets):
            raise ValueError(f"press_offset={press_offset!r} must not contain negative stud indices")
        if any(offset >= stud_count for offset in offsets):
            raise ValueError(
                f"press_offset={press_offset!r} invalid for side {press_side} and {brick.name}; "
                f"expected stud indices 0..{stud_count - 1}"
            )
        if len(offsets) == 2 and abs(offsets[0] - offsets[1]) != 1:
            raise ValueError(f"press_offset={press_offset!r} must contain adjacent stud indices")
        return offsets

    if press_side in (1, 4):
        offsets = selected_offsets(brick.studs_y)
        y_values = [-width / 2.0 + (offset + 0.5) * STUD_PITCH for offset in offsets]
        x_stud = length / 2.0 - STUD_PITCH / 2.0 if press_side == 1 else -length / 2.0 + STUD_PITCH / 2.0
        edge_x = length / 2.0 if press_side == 1 else -length / 2.0
        selected_local = np.array([[x_stud, y, stud_z, 1.0] for y in y_values], dtype=np.float64)
        edge_local = np.array([edge_x, float(np.mean(y_values)), contact_z, 1.0])
        outward_local = np.array([1.0 if press_side == 1 else -1.0, 0.0, 0.0])
        tangent_local = np.array([0.0, 1.0, 0.0])
    elif press_side in (2, 3):
        offsets = selected_offsets(brick.studs_x)
        x_values = [length / 2.0 - (offset + 0.5) * STUD_PITCH for offset in offsets]
        y_stud = width / 2.0 - STUD_PITCH / 2.0 if press_side == 2 else -width / 2.0 + STUD_PITCH / 2.0
        edge_y = width / 2.0 if press_side == 2 else -width / 2.0
        selected_local = np.array([[x, y_stud, stud_z, 1.0] for x in x_values], dtype=np.float64)
        edge_local = np.array([float(np.mean(x_values)), edge_y, contact_z, 1.0])
        outward_local = np.array([0.0, 1.0 if press_side == 2 else -1.0, 0.0])
        tangent_local = np.array([1.0, 0.0, 0.0])
    else:
        raise ValueError(f"Unsupported press_side {press_side}; expected 1..4")

    rot = bottom_pose[:3, :3]
    selected_world = (bottom_pose @ selected_local.T).T[:, :3]
    stud_pair_center = np.mean(selected_world, axis=0)
    edge_point = (bottom_pose @ edge_local)[:3]
    outward = rot @ outward_local
    outward = outward / np.linalg.norm(outward)
    tangent = rot @ tangent_local
    tangent = tangent / np.linalg.norm(tangent)

    z_axis = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    x_axis = outward
    y_axis = np.cross(z_axis, x_axis)
    if np.linalg.norm(y_axis) < 1e-8:
        y_axis = tangent
    y_axis = y_axis / np.linalg.norm(y_axis)
    x_axis = np.cross(y_axis, z_axis)
    x_axis = x_axis / np.linalg.norm(x_axis)

    contact_pose = np.eye(4, dtype=np.float64)
    contact_pose[:3, 0] = x_axis
    contact_pose[:3, 1] = y_axis
    contact_pose[:3, 2] = z_axis
    contact_pose[:3, 3] = edge_point

    return LegoPickTarget(
        contact_pose=contact_pose,
        contact_point=edge_point,
        selected_stud_centers=selected_world,
        stud_pair_center=stud_pair_center,
        edge_point=edge_point,
        outward_normal=outward,
        tangent=tangent,
    )


def press_point_grid(
    brick: LegoBrickSpec,
    grid: LegoGridPose,
    press_side: int,
    press_offset: int,
) -> tuple[int, int, int]:
    """Port of APEX-MR get_press_pt for a brick placed on the plate grid."""
    height = brick.studs_x
    width = brick.studs_y
    if grid.ori == 0:
        if press_side == 1:
            return grid.x, grid.y + press_offset, 0
        if press_side == 2:
            return grid.x + press_offset, grid.y + width - 1, 1
        if press_side == 3:
            return grid.x + press_offset, grid.y, 1
        if press_side == 4:
            return grid.x + height - 1, grid.y + press_offset, 0
    elif grid.ori == 1:
        height, width = width, height
        if press_side == 1:
            return grid.x + height - 1 - press_offset, grid.y, 1
        if press_side == 2:
            return grid.x, grid.y + press_offset, 0
        if press_side == 3:
            return grid.x + height - 1, grid.y + press_offset, 0
        if press_side == 4:
            return grid.x + height - 1 - press_offset, grid.y + width - 1, 1
    raise ValueError(
        f"Unsupported press side/orientation: side={press_side}, ori={grid.ori}"
    )
