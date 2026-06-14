from __future__ import annotations

from dataclasses import dataclass

import numpy as np


APEX_STUD_PITCH = 0.008
APEX_BRICK_HEIGHT = 0.0096
APEX_LEVER_WALL_HEIGHT = 0.0032
APEX_KNOB_HEIGHT = 0.0017

APEX_TWIST_RAD = 0.244346
APEX_TWIST_DEG = float(np.rad2deg(APEX_TWIST_RAD))
APEX_HANDOVER_TWIST_RAD = 0.314159
APEX_HANDOVER_TWIST_DEG = float(np.rad2deg(APEX_HANDOVER_TWIST_RAD))

APEX_PLACE_BRICK_OFFSET = np.array([-0.005, 0.005, -0.005], dtype=np.float64)
APEX_GRAB_BRICK_OFFSET = np.array([-0.005, 0.005, -0.0028], dtype=np.float64)
APEX_PICK_TWIST_UP_WORLD_Z = 0.015
APEX_DROP_TWIST_UP_WORLD_Z = 0.015


@dataclass(frozen=True)
class ApexBrickLibraryEntry:
    brick_id: int
    studs_x: int
    studs_y: int
    weight_kg: float


APEX_BRICK_LIBRARY = {
    2: ApexBrickLibraryEntry(2, studs_x=4, studs_y=2, weight_kg=0.0022),
    3: ApexBrickLibraryEntry(3, studs_x=6, studs_y=2, weight_kg=0.00328),
    4: ApexBrickLibraryEntry(4, studs_x=8, studs_y=1, weight_kg=0.00308),
    5: ApexBrickLibraryEntry(5, studs_x=4, studs_y=1, weight_kg=0.0015),
    6: ApexBrickLibraryEntry(6, studs_x=6, studs_y=1, weight_kg=0.0023),
    7: ApexBrickLibraryEntry(7, studs_x=4, studs_y=1, weight_kg=0.0016),
    8: ApexBrickLibraryEntry(8, studs_x=4, studs_y=1, weight_kg=0.0016),
    9: ApexBrickLibraryEntry(9, studs_x=2, studs_y=1, weight_kg=0.0008),
    10: ApexBrickLibraryEntry(10, studs_x=1, studs_y=1, weight_kg=0.00044),
    11: ApexBrickLibraryEntry(11, studs_x=2, studs_y=1, weight_kg=0.00075),
    12: ApexBrickLibraryEntry(12, studs_x=2, studs_y=2, weight_kg=0.0012),
}


APEX_TOOL_DH_LAST_ROWS = {
    "tool": np.array([0.0, -0.1830, 0.0, np.pi], dtype=np.float64),
    "tool_assemble": np.array([0.0, -0.1825, 0.0078, np.pi], dtype=np.float64),
    "tool_disassemble": np.array([0.0, -0.1920, 0.0, np.pi], dtype=np.float64),
    "tool_alt": np.array([0.0, -0.1784, -0.0174, np.pi], dtype=np.float64),
    "tool_alt_assemble": np.array([0.0, -0.1784, -0.0078, np.pi], dtype=np.float64),
    "tool_handover_assemble": np.array([0.0, -0.1815, 0.0078, np.pi], dtype=np.float64),
}


def apex_valid_press_offsets(studs_x: int, studs_y: int, press_side: int) -> range:
    if press_side in (1, 4):
        return range(max(0, studs_y - 1))
    if press_side in (2, 3):
        return range(max(0, studs_x - 1))
    raise ValueError(f"Unsupported press_side {press_side}; expected 1..4")


def apex_press_point_grid(
    brick_x: int,
    brick_y: int,
    studs_x: int,
    studs_y: int,
    brick_ori: int,
    press_side: int,
    press_offset: int,
) -> tuple[int, int, int]:
    """Port of APEX-MR Lego::get_press_pt."""
    height = studs_x
    width = studs_y
    if brick_ori == 0:
        if press_side == 1:
            return brick_x, brick_y + press_offset, 0
        if press_side == 2:
            return brick_x + press_offset, brick_y + width - 1, 1
        if press_side == 3:
            return brick_x + press_offset, brick_y, 1
        if press_side == 4:
            return brick_x + height - 1, brick_y + press_offset, 0
    elif brick_ori == 1:
        height, width = width, height
        if press_side == 1:
            return brick_x + height - 1 - press_offset, brick_y, 1
        if press_side == 2:
            return brick_x, brick_y + press_offset, 0
        if press_side == 3:
            return brick_x + height - 1, brick_y + press_offset, 0
        if press_side == 4:
            return brick_x + height - 1 - press_offset, brick_y + width - 1, 1
    raise ValueError(
        f"Unsupported brick_ori/press_side: ori={brick_ori}, side={press_side}"
    )


def apex_grab_offset_local(
    studs_x: int,
    studs_y: int,
    press_side: int,
    press_offset: int,
    p_len: float = APEX_STUD_PITCH,
    brick_len_offset: float = 0.0,
) -> tuple[np.ndarray, float]:
    """Local translation/yaw used by APEX calc_brick_grab_pose before action offsets.

    Returns local translation and yaw rotation around local z. The yaw summarizes the
    z_180 / z_90 combinations in the C++ implementation.
    """
    height = studs_x
    width = studs_y
    if press_side == 1:
        p = np.array(
            [
                (height * p_len - brick_len_offset) / 2.0,
                -(width * p_len) / 2.0 + (press_offset + 1) * p_len,
                0.0,
            ],
            dtype=np.float64,
        )
        yaw = np.pi
    elif press_side == 2:
        p = np.array(
            [
                (height * p_len) / 2.0 - (press_offset + 1) * p_len,
                (width * p_len - brick_len_offset) / 2.0,
                0.0,
            ],
            dtype=np.float64,
        )
        yaw = -np.pi / 2.0
    elif press_side == 3:
        p = np.array(
            [
                (height * p_len) / 2.0 - (press_offset + 1) * p_len,
                -(width * p_len - brick_len_offset) / 2.0,
                0.0,
            ],
            dtype=np.float64,
        )
        yaw = np.pi / 2.0
    elif press_side == 4:
        p = np.array(
            [
                -(height * p_len - brick_len_offset) / 2.0,
                -(width * p_len) / 2.0 + (press_offset + 1) * p_len,
                0.0,
            ],
            dtype=np.float64,
        )
        yaw = 0.0
    else:
        raise ValueError(f"Unsupported press_side {press_side}; expected 1..4")
    return p, yaw


def apex_pick_waypoint_offsets() -> dict[str, np.ndarray]:
    return {
        "pick_tilt_up": np.array(
            [
                APEX_GRAB_BRICK_OFFSET[0],
                APEX_GRAB_BRICK_OFFSET[1],
                APEX_GRAB_BRICK_OFFSET[2] - abs(APEX_GRAB_BRICK_OFFSET[2]),
            ],
            dtype=np.float64,
        ),
        "pick_up": np.array([0.0, 0.0, APEX_GRAB_BRICK_OFFSET[2]], dtype=np.float64),
        "pick": np.zeros(3, dtype=np.float64),
        "pick_twist_up_world": np.array([0.0, 0.0, APEX_PICK_TWIST_UP_WORLD_Z], dtype=np.float64),
    }


def apex_drop_waypoint_offsets(attack_dir: int = 1) -> dict[str, np.ndarray]:
    return {
        "drop_offset": np.array(
            [
                APEX_PLACE_BRICK_OFFSET[0],
                APEX_PLACE_BRICK_OFFSET[1] * attack_dir,
                APEX_PLACE_BRICK_OFFSET[2] - abs(APEX_PLACE_BRICK_OFFSET[2]),
            ],
            dtype=np.float64,
        ),
        "drop_up": np.array([0.0, 0.0, APEX_PLACE_BRICK_OFFSET[2]], dtype=np.float64),
        "drop": np.zeros(3, dtype=np.float64),
        "drop_twist_up_world": np.array([0.0, 0.0, APEX_DROP_TWIST_UP_WORLD_Z], dtype=np.float64),
    }
