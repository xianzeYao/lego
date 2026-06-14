#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import mani_skill  # noqa: F401
import gymnasium as gym
from mani_skill.utils.wrappers.record import RecordEpisode
import mplib
import numpy as np
import sapien
from transforms3d import quaternions

ARM_JOINT_NAMES = [f"joint_{i}" for i in range(1, 8)]
GRIPPER_ACTIVE_NAMES = ["gripper_Left_1_Joint", "gripper_Right_1_Joint"]
GRIPPER_PASSIVE_NAMES = [
    "gripper_Left_2_Joint",
    "gripper_Right_2_Joint",
    "gripper_Left_Support_Joint",
    "gripper_Right_Support_Joint",
]
ALL_GRIPPER_JOINT_NAMES = set(GRIPPER_ACTIVE_NAMES + GRIPPER_PASSIVE_NAMES)


def flatten(x):
    return np.asarray(x, dtype=np.float64).reshape(-1)


def find_existing_urdf(default_path=None):
    if default_path and os.path.exists(default_path):
        return default_path
    cands = [
        os.path.join(os.getcwd(), "RM75-B.urdf"),
        os.path.expanduser("~/.maniskill/data/robots/RM75_gripper/RM75-B/urdf/RM75-B.urdf"),
    ]
    for p in cands:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Cannot locate RM75-B.urdf. Pass --urdf-path explicitly.")


def tiny_box_size_for_link(link_name: str) -> np.ndarray:
    lname = link_name.lower()
    if lname == "gripper_tcp":
        return np.array([0.001, 0.001, 0.001], dtype=np.float64)
    return np.array([0.005, 0.005, 0.005], dtype=np.float64)


def generate_near_collision_free_planning_urdf(source_urdf_path: str, planning_urdf_path: str) -> None:
    # 完全沿用你原始 RM75 demo 的版本，避免 setJointOrder 配置漂掉
    src_root = ET.parse(source_urdf_path).getroot()
    dst_root = ET.Element("robot", {"name": src_root.attrib.get("name", "RM75_planning_tiny")})
    for link in src_root.findall("link"):
        lname = link.attrib["name"]
        new_link = ET.SubElement(dst_root, "link", {"name": lname})
        has_geom = (link.find("visual") is not None) or (link.find("collision") is not None)
        has_inertial = link.find("inertial") is not None
        if (not has_geom and not has_inertial) or lname == "gripper_tcp":
            continue
        inertial = ET.SubElement(new_link, "inertial")
        ET.SubElement(inertial, "origin", {"xyz": "0 0 0", "rpy": "0 0 0"})
        ET.SubElement(inertial, "mass", {"value": "0.001"})
        ET.SubElement(
            inertial,
            "inertia",
            {"ixx": "1e-7", "ixy": "0", "ixz": "0", "iyy": "1e-7", "iyz": "0", "izz": "1e-7"},
        )
        size = tiny_box_size_for_link(lname)
        size_str = f"{size[0]:.6f} {size[1]:.6f} {size[2]:.6f}"
        visual = ET.SubElement(new_link, "visual")
        ET.SubElement(visual, "origin", {"xyz": "0 0 0", "rpy": "0 0 0"})
        vgeom = ET.SubElement(visual, "geometry")
        ET.SubElement(vgeom, "box", {"size": size_str})
        collision = ET.SubElement(new_link, "collision")
        ET.SubElement(collision, "origin", {"xyz": "0 0 0", "rpy": "0 0 0"})
        cgeom = ET.SubElement(collision, "geometry")
        ET.SubElement(cgeom, "box", {"size": size_str})

    for joint in src_root.findall("joint"):
        attrs = dict(joint.attrib)
        if attrs.get("name") in ALL_GRIPPER_JOINT_NAMES:
            attrs["type"] = "fixed"
        new_joint = ET.SubElement(dst_root, "joint", attrs)
        for child in list(joint):
            if attrs.get("type") == "fixed" and child.tag in {"axis", "limit", "dynamics", "mimic", "calibration", "safety_controller"}:
                continue
            new_joint.append(child)

    ET.indent(dst_root, space="  ")
    ET.ElementTree(dst_root).write(planning_urdf_path, encoding="utf-8", xml_declaration=True)


def parse_link_names(urdf_path: str):
    root = ET.parse(urdf_path).getroot()
    return [x.attrib["name"] for x in root.findall("link")]


def write_permissive_srdf(urdf_path: str, srdf_path: str):
    # 也完全沿用你原始 RM75 demo 的版本
    root = ET.parse(urdf_path).getroot()
    link_names = [x.attrib["name"] for x in root.findall("link")]
    adjacent = set()
    for joint in root.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is not None and child is not None:
            a = parent.attrib["link"]
            b = child.attrib["link"]
            adjacent.add(tuple(sorted((a, b))))

    lines = ['<?xml version="1.0" ?>', '<robot name="RM75-B">', '  <group name="rm75_arm">']
    for j in ARM_JOINT_NAMES:
        lines.append(f'    <joint name="{j}"/>')
    lines += [
        '  </group>',
        '  <group name="tool_end">',
        '    <joint name="gripper_tcp_joint"/>',
        '  </group>',
        '  <end_effector group="tool_end" name="end_effector" parent_link="gripper_base_link"/>',
    ]
    for a, b in sorted(adjacent):
        lines.append(f'  <disable_collisions link1="{a}" link2="{b}" reason="Adjacent"/>')
    hand_like = [n for n in link_names if any(k in n.lower() for k in ["gripper", "pad", "flange"])]
    arm_like = ["base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6", "link_7"]
    for i in range(len(hand_like)):
        for j in range(i + 1, len(hand_like)):
            a, b = sorted((hand_like[i], hand_like[j]))
            lines.append(f'  <disable_collisions link1="{a}" link2="{b}" reason="DebugPermissive"/>')
    for a in arm_like:
        for b in hand_like:
            x, y = sorted((a, b))
            lines.append(f'  <disable_collisions link1="{x}" link2="{y}" reason="DebugPermissive"/>')
    lines.append('</robot>\n')
    Path(srdf_path).write_text("\n".join(lines), encoding="utf-8")


def build_official_style_grasp_pose_visual(scene):
    builder = scene.create_actor_builder()
    grasp_pose_visual_width = 0.01
    grasp_width = 0.05
    builder.add_sphere_visual(
        pose=sapien.Pose(p=[0, 0, 0.0]),
        radius=grasp_pose_visual_width,
        material=sapien.render.RenderMaterial(base_color=[0.3, 0.4, 0.8, 0.7]),
    )
    builder.add_box_visual(
        pose=sapien.Pose(p=[0, 0, -0.08]),
        half_size=[grasp_pose_visual_width, grasp_pose_visual_width, 0.02],
        material=sapien.render.RenderMaterial(base_color=[0, 1, 0, 0.7]),
    )
    builder.add_box_visual(
        pose=sapien.Pose(p=[0, 0, -0.05]),
        half_size=[grasp_pose_visual_width, grasp_width, grasp_pose_visual_width],
        material=sapien.render.RenderMaterial(base_color=[0, 1, 0, 0.7]),
    )
    builder.add_box_visual(
        pose=sapien.Pose(
            p=[0.03 - grasp_pose_visual_width * 3, grasp_width + grasp_pose_visual_width, 0.03 - 0.05],
            q=quaternions.axangle2quat(np.array([0, 1, 0]), theta=np.pi / 2),
        ),
        half_size=[0.04, grasp_pose_visual_width, grasp_pose_visual_width],
        material=sapien.render.RenderMaterial(base_color=[0, 0, 1, 0.7]),
    )
    builder.add_box_visual(
        pose=sapien.Pose(
            p=[0.03 - grasp_pose_visual_width * 3, -grasp_width - grasp_pose_visual_width, 0.03 - 0.05],
            q=quaternions.axangle2quat(np.array([0, 1, 0]), theta=np.pi / 2),
        ),
        half_size=[0.04, grasp_pose_visual_width, grasp_pose_visual_width],
        material=sapien.render.RenderMaterial(base_color=[1, 0, 0, 0.7]),
    )
    return builder.build_kinematic(name="grasp_pose_visual")


def quat_angle_deg(q1, q2):
    q1 = flatten(q1)[:4]
    q2 = flatten(q2)[:4]
    q1 = q1 / max(np.linalg.norm(q1), 1e-12)
    q2 = q2 / max(np.linalg.norm(q2), 1e-12)
    dot = float(np.clip(abs(np.dot(q1, q2)), -1.0, 1.0))
    angle = 2.0 * np.arccos(dot)
    return float(np.degrees(angle))


def normalize(v, eps=1e-8):
    v = flatten(v)
    n = np.linalg.norm(v)
    if n < eps:
        return None
    return v / n


def mat2quat_np(R: np.ndarray) -> np.ndarray:
    m = np.asarray(R, dtype=np.float64)
    t = np.trace(m)

    if t > 0.0:
        s = np.sqrt(t + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    else:
        if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
            s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
            w = (m[2, 1] - m[1, 2]) / s
            x = 0.25 * s
            y = (m[0, 1] + m[1, 0]) / s
            z = (m[0, 2] + m[2, 0]) / s
        elif m[1, 1] > m[2, 2]:
            s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
            w = (m[0, 2] - m[2, 0]) / s
            x = (m[0, 1] + m[1, 0]) / s
            y = 0.25 * s
            z = (m[1, 2] + m[2, 1]) / s
        else:
            s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
            w = (m[1, 0] - m[0, 1]) / s
            x = (m[0, 2] + m[2, 0]) / s
            y = (m[1, 2] + m[2, 1]) / s
            z = 0.25 * s

    q = np.array([w, x, y, z], dtype=np.float64)
    q = q / max(np.linalg.norm(q), 1e-12)
    return q


class RM75JiaobangPickMove:
    def __init__(self, env, urdf_path: str, srdf_path: str, args):
        self.env = env
        self.base_env = env.unwrapped
        self.robot = self.base_env.agent.robot
        self.tcp = self.base_env.agent.tcp
        self.tip_link_name = "gripper_tcp"
        self.action_dim = int(np.prod(env.action_space.shape))
        self.control_timestep = 1.0 / 20.0
        self.args = args

        self.link_names = parse_link_names(urdf_path)
        self.active_joint_names = [j.get_name() for j in self.robot.get_active_joints()]
        self.arm_indices = [self.active_joint_names.index(n) for n in ARM_JOINT_NAMES]

        self.planner = mplib.Planner(
            urdf=urdf_path,
            srdf=srdf_path,
            user_link_names=self.link_names,
            user_joint_names=ARM_JOINT_NAMES,
            move_group=self.tip_link_name,
            joint_vel_limits=np.ones(7, dtype=np.float64),
            joint_acc_limits=np.ones(7, dtype=np.float64),
        )
        base_pose = self.robot.pose
        self.planner.set_base_pose(np.hstack([flatten(base_pose.p)[:3], flatten(base_pose.q)[:4]]))
        self.grasp_pose_visual = build_official_style_grasp_pose_visual(self.base_env.scene)
        self.grasp_pose_visual.set_pose(self.tcp.pose)

    def current_arm_qpos(self):
        q = flatten(self.robot.get_qpos())
        return q[self.arm_indices]

    def compose_action(self, arm_target_q, gripper_value):
        action = np.zeros(self.action_dim, dtype=np.float32)
        action[:7] = flatten(arm_target_q)[:7].astype(np.float32)
        if self.action_dim > 7:
            action[7] = np.float32(gripper_value)
        return action

    def step_and_render(self, action):
        self.env.step(action)
        if self.args.vis:
            self.env.render()
            if self.args.render_sleep > 0:
                time.sleep(self.args.render_sleep)

    def hold_current_and_set_gripper(self, gripper_value, steps=20):
        q_hold = self.current_arm_qpos()
        action = self.compose_action(q_hold, gripper_value)
        for _ in range(steps):
            self.step_and_render(action)

    def preview_target_pose(self, pose):
        self.grasp_pose_visual.set_pose(sapien.Pose(flatten(pose.p)[:3], flatten(pose.q)[:4]))
        if self.args.vis:
            self.env.render()

    def make_target(self, pose, variant_name):
        p = flatten(pose.p)[:3]
        q_wxyz = flatten(pose.q)[:4]
        q_xyzw = q_wxyz[[1, 2, 3, 0]]
        pymp = getattr(mplib, "pymp", None)
        PoseCls = getattr(pymp, "Pose", None) if pymp is not None else None
        if variant_name == "array_wxyz":
            return np.concatenate([p, q_wxyz])
        if variant_name == "array_xyzw":
            return np.concatenate([p, q_xyzw])
        if variant_name == "pymp_pose_wxyz" and PoseCls is not None:
            return PoseCls(p, q_wxyz)
        if variant_name == "pymp_pose_xyzw" and PoseCls is not None:
            return PoseCls(p, q_xyzw)
        raise ValueError(f"Unsupported or unavailable variant: {variant_name}")

    def plan_terminal_q(self, pose, variant_name="array_wxyz"):
        start = self.current_arm_qpos()
        target = self.make_target(pose, variant_name)
        print("[planner] current arm q:", np.round(start, 6))
        print("[planner] target pose p:", np.round(flatten(pose.p)[:3], 6))
        print("[planner] target pose q:", np.round(flatten(pose.q)[:4], 6))
        result = self.planner.plan_qpos_to_pose(target, start, time_step=self.control_timestep, use_point_cloud=False)
        print("[planner] status:", result.get("status", result))
        if result.get("status", "") != "Success":
            return None
        if "position" not in result or len(result["position"]) == 0:
            print("[planner] planner returned no waypoints")
            return None
        last_q = flatten(result["position"][-1])[:7]
        print("[planner] last waypoint:", np.round(last_q, 6))
        return last_q

    def execute_linear(self, q_target, gripper_value, max_delta_per_step=0.05, hold_steps=20, tag=""):
        q_start = self.current_arm_qpos()
        q_target = flatten(q_target)[:7]
        q_delta = (q_target - q_start + np.pi) % (2 * np.pi) - np.pi
        q_target_short = q_start + q_delta
        num_steps = int(np.ceil(np.max(np.abs(q_delta)) / max_delta_per_step))
        num_steps = max(1, num_steps)
        print(f"[{tag}] execute_linear num_steps={num_steps}")
        for alpha in np.linspace(0.0, 1.0, num_steps):
            q = (1.0 - alpha) * q_start + alpha * q_target_short
            action = self.compose_action(q, gripper_value)
            self.step_and_render(action)
        final_action = self.compose_action(q_target_short, gripper_value)
        for _ in range(hold_steps):
            self.step_and_render(final_action)

    def get_obj_pose(self):
        obj_pose = self.base_env.obj.pose
        p = flatten(obj_pose.p)[:3]
        q = flatten(obj_pose.q)[:4]
        return p, q

    def get_goal_pose(self):
        goal_pose = self.base_env.goal_jiaobang.pose
        p = flatten(goal_pose.p)[:3]
        q = flatten(goal_pose.q)[:4]
        return p, q

    def get_shortest_edge_dir_xy(self):
        obj_pose = self.base_env.obj.pose
        obj_q = flatten(obj_pose.q)[:4]

        lo = np.asarray(self.base_env.obj_local_aabb_min[0], dtype=np.float64)
        hi = np.asarray(self.base_env.obj_local_aabb_max[0], dtype=np.float64)
        size_local = hi - lo
        sx = float(size_local[0])
        sy = float(size_local[1])

        R_obj = quaternions.quat2mat(obj_q)
        axis_x_world = R_obj[:, 0].copy()
        axis_y_world = R_obj[:, 1].copy()

        axis_x_world[2] = 0.0
        axis_y_world[2] = 0.0

        axis_x_world = normalize(axis_x_world)
        axis_y_world = normalize(axis_y_world)

        if axis_x_world is None and axis_y_world is None:
            return None
        if axis_x_world is None:
            v = axis_y_world
        elif axis_y_world is None:
            v = axis_x_world
        else:
            v = axis_x_world if sx <= sy else axis_y_world

        if v[0] < 0:
            v = -v
        return v

    def build_topdown_grasp_pose(self):
        obj_p, _ = self.get_obj_pose()

        closing = self.get_shortest_edge_dir_xy()
        if closing is None:
            raise RuntimeError('Failed to compute shortest-edge direction from obj AABB.')
        closing = normalize(closing)
        if closing is None:
            raise RuntimeError('Shortest-edge direction is degenerate.')

        approaching = np.array([0.0, 0.0, -1.0], dtype=np.float64)
        ortho = np.cross(closing, approaching)
        ortho = normalize(ortho)
        if ortho is None:
            raise RuntimeError('Failed to construct orthogonal grasp basis.')

        closing = np.cross(approaching, ortho)
        closing = normalize(closing)
        if closing is None:
            raise RuntimeError('Failed to re-orthogonalize closing axis.')

        R_tcp = np.stack([ortho, closing, approaching], axis=1)
        q = mat2quat_np(R_tcp)

        p = obj_p.copy()
        p[2] += self.args.grasp_z_offset
        return sapien.Pose(p, q)

    def build_pregrasp_pose(self, grasp_pose):
        p = flatten(grasp_pose.p)[:3].copy()
        q = flatten(grasp_pose.q)[:4].copy()
        p[2] += self.args.pregrasp_height
        return sapien.Pose(p, q)

    def build_goal_tcp_pose(self, grasp_pose):
        obj_p, _ = self.get_obj_pose()
        goal_p, _ = self.get_goal_pose()
        tcp_p = flatten(grasp_pose.p)[:3].copy()
        tcp_q = flatten(grasp_pose.q)[:4].copy()
        tcp_p = tcp_p + (goal_p - obj_p)
        tcp_p[2] += self.args.goal_z_offset
        return sapien.Pose(tcp_p, tcp_q)

    def is_grasped(self):
        try:
            g = self.base_env.agent.is_grasping(self.base_env.obj)
            if hasattr(g, "item"):
                return bool(g.item())
            return bool(g)
        except Exception:
            return False

    def report_final_error(self, target_pose):
        tcp_pose = self.base_env.agent.tcp.pose
        p_cur = flatten(tcp_pose.p)[:3]
        q_cur = flatten(tcp_pose.q)[:4]
        p_tgt = flatten(target_pose.p)[:3]
        q_tgt = flatten(target_pose.q)[:4]
        pos_err = float(np.linalg.norm(p_cur - p_tgt))
        ang_err = quat_angle_deg(q_cur, q_tgt)
        print("\n[final] tcp p:", np.round(p_cur, 6))
        print("[final] tcp q:", np.round(q_cur, 6))
        print("[final] target p:", np.round(p_tgt, 6))
        print("[final] target q:", np.round(q_tgt, 6))
        print(f"[final] position error: {pos_err:.6f} m")
        print(f"[final] orientation error: {ang_err:.3f} deg")
        print(f"[final] is_grasped = {self.is_grasped()}")

    def run_demo(self):
        # 0. 一开始完全张开夹爪
        print("\n[open gripper]")
        self.hold_current_and_set_gripper(self.args.gripper_open, steps=self.args.open_steps)

        grasp_pose = self.build_topdown_grasp_pose()
        pregrasp_pose = self.build_pregrasp_pose(grasp_pose)
        goal_tcp_pose = self.build_goal_tcp_pose(grasp_pose)

        print("\n[poses]")
        print("grasp p:", np.round(flatten(grasp_pose.p)[:3], 6), "q:", np.round(flatten(grasp_pose.q)[:4], 6))
        print("pregrasp p:", np.round(flatten(pregrasp_pose.p)[:3], 6), "q:", np.round(flatten(pregrasp_pose.q)[:4], 6))
        print("goal tcp p:", np.round(flatten(goal_tcp_pose.p)[:3], 6), "q:", np.round(flatten(goal_tcp_pose.q)[:4], 6))

        # 1. 到预抓取位置
        print("\n[move to pregrasp]")
        self.preview_target_pose(pregrasp_pose)
        q_pre = self.plan_terminal_q(pregrasp_pose, variant_name=self.args.variant)
        if q_pre is None:
            print("[FAIL] pregrasp planning failed")
            return False
        self.execute_linear(q_pre, gripper_value=self.args.gripper_open, max_delta_per_step=self.args.max_delta_per_step, hold_steps=0, tag="pregrasp")

        # 2. 到抓取位置
        print("\n[move to grasp]")
        self.preview_target_pose(grasp_pose)
        q_grasp = self.plan_terminal_q(grasp_pose, variant_name=self.args.variant)
        if q_grasp is None:
            print("[FAIL] grasp planning failed")
            return False
        self.execute_linear(q_grasp, gripper_value=self.args.gripper_open, max_delta_per_step=self.args.max_delta_per_step, hold_steps=self.args.hold_steps, tag="grasp")

        # 3. 闭合夹爪抓住 obj
        print("\n[env.ste gripper]")
        self.hold_current_and_set_gripper(self.args.gripper_close, steps=self.args.close_steps)
        print("[close gripper] is_grasped =", self.is_grasped())

        # 4. 移动到目标位置
        print("\n[move to goal]")
        self.preview_target_pose(goal_tcp_pose)
        q_goal = self.plan_terminal_q(goal_tcp_pose, variant_name=self.args.variant)
        if q_goal is None:
            print("[FAIL] goal planning failed")
            return False
        self.execute_linear(q_goal, gripper_value=self.args.gripper_close, max_delta_per_step=self.args.max_delta_per_step, hold_steps=self.args.hold_steps, tag="goal")
        self.report_final_error(goal_tcp_pose)
        return True

    def run_tests(self):
        print("\n[test_env_creation]")
        assert self.robot is not None
        assert self.tcp is not None
        print("pass")

        print("\n[test_planner_creation]")
        assert self.planner is not None
        print("pass")

        grasp_pose = self.build_topdown_grasp_pose()
        pregrasp_pose = self.build_pregrasp_pose(grasp_pose)
        goal_tcp_pose = self.build_goal_tcp_pose(grasp_pose)

        print("\n[test_pose_build]")
        assert len(flatten(grasp_pose.p)) == 3
        assert len(flatten(grasp_pose.q)) == 4
        assert abs(flatten(pregrasp_pose.p)[2] - flatten(grasp_pose.p)[2] - self.args.pregrasp_height) < 1e-8
        assert len(flatten(goal_tcp_pose.p)) == 3
        print("pass")

        print("\n[test_pregrasp_plan]")
        assert self.plan_terminal_q(pregrasp_pose, variant_name=self.args.variant) is not None
        print("pass")

        print("\n[test_grasp_plan]")
        assert self.plan_terminal_q(grasp_pose, variant_name=self.args.variant) is not None
        print("pass")

        print("\n[test_goal_plan]")
        assert self.plan_terminal_q(goal_tcp_pose, variant_name=self.args.variant) is not None
        print("pass")

        print("\nAll tests passed.")
        return True


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="demo", choices=["demo", "test"])
    parser.add_argument("--urdf-path", default=None)
    parser.add_argument("--srdf-path", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variant", default="array_wxyz", choices=["array_wxyz", "array_xyzw", "pymp_pose_wxyz", "pymp_pose_xyzw"])
    parser.add_argument("--pregrasp-height", type=float, default=0.05)
    parser.add_argument("--grasp-z-offset", type=float, default=0.0)
    parser.add_argument("--goal-z-offset", type=float, default=0.0)
    parser.add_argument("--yaw-offset-deg", type=float, default=180.0)
    parser.add_argument("--max-delta-per-step", type=float, default=0.05)
    parser.add_argument("--hold-steps", type=int, default=15)
    parser.add_argument("--open-steps", type=int, default=0)
    parser.add_argument("--close-steps", type=int, default=100)
    parser.add_argument("--gripper-open", type=float, default=-10.0)
    parser.add_argument("--gripper-close", type=float, default=10.0)
    parser.add_argument("--video-dir", default="./rm75_jiaobang_pick_move_v5")
    parser.add_argument("--vis", action="store_true")
    parser.add_argument("--render-sleep", type=float, default=0.03)
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.video_dir, exist_ok=True)

    sim_urdf_path = find_existing_urdf(args.urdf_path)
    env = gym.make(
        "Two_finger_PickJiaobang-v1",
        robot_uids="RM75",
        obs_mode="none",
        control_mode="pd_joint_pos",
        render_mode="human" if args.vis else "rgb_array",
    )
    env = RecordEpisode(
        env,
        output_dir=args.video_dir,
        save_trajectory=False,
        save_video=True,
        source_type="motionplanning",
        source_desc="RM75 jiaobang pick move v5",
    )
    env.reset(seed=args.seed)

    tmpdir = tempfile.mkdtemp(prefix="rm75_jiaobang_pick_move_v5_")
    planning_urdf_path = os.path.join(tmpdir, "RM75-B.planning.tiny.urdf")
    srdf_path = args.srdf_path or os.path.join(tmpdir, "RM75-B.permissive.srdf")
    generate_near_collision_free_planning_urdf(sim_urdf_path, planning_urdf_path)
    if args.srdf_path is None:
        write_permissive_srdf(planning_urdf_path, srdf_path)

    print("Sim URDF     :", sim_urdf_path)
    print("Planning URDF:", planning_urdf_path)
    print("SRDF         :", srdf_path)

    demo = RM75JiaobangPickMove(env, planning_urdf_path, srdf_path, args)
    ok = demo.run_tests() if args.mode == "test" else demo.run_demo()
    print("\nfinal success =", ok)

    try:
        env.flush_video()
    except Exception:
        pass
    try:
        env.flush()
    except Exception:
        pass
    try:
        env.close()
    except Exception as e:
        print("close warning:", e)


if __name__ == "__main__":
    main()
