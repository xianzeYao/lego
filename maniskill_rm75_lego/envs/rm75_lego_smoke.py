from __future__ import annotations

import numpy as np
import sapien
import torch

from mani_skill.envs.sapien_env import BaseEnv
from mani_skill.sensors.camera import CameraConfig
from mani_skill.utils import sapien_utils
from mani_skill.utils.building import actors
from mani_skill.utils.building.ground import build_ground
from mani_skill.utils.registration import register_env

from maniskill_rm75_lego.agents.rm75_lego_tool import ARM_JOINT_NAMES, RM75LegoTool


CONTACT_OFFSET_TCP = [0.0, 0.0, 0.0]


@register_env("RM75LegoSmoke-v1", max_episode_steps=200)
class RM75LegoSmokeEnv(BaseEnv):
    SUPPORTED_REWARD_MODES = ["none"]
    SUPPORTED_ROBOTS = ["rm75_lego_tool"]
    agent: RM75LegoTool

    def __init__(self, *args, robot_uids="rm75_lego_tool", **kwargs):
        super().__init__(*args, robot_uids=robot_uids, **kwargs)

    @property
    def _default_sensor_configs(self):
        pose = sapien_utils.look_at(eye=[0.9, -0.9, 0.8], target=[0.0, 0.0, 0.25])
        return [CameraConfig("base_camera", pose, 256, 256, np.pi / 3, 0.01, 100)]

    @property
    def _default_human_render_camera_configs(self):
        pose = sapien_utils.look_at(eye=[0.45, -0.62, 0.42], target=[0.0, -0.3, 0.06])
        return CameraConfig("render_camera", pose, 1280, 960, np.pi / 4, 0.005, 100)

    def _load_agent(self, options: dict):
        super()._load_agent(options, sapien.Pose())

    def _load_scene(self, options: dict):
        self.ground = build_ground(self.scene)
        self.tcp_marker = actors.build_sphere(
            self.scene,
            radius=0.0025,
            color=[0.1, 0.35, 1.0, 0.8],
            name="lego_tool_tcp_marker",
            body_type="kinematic",
            add_collision=False,
            initial_pose=sapien.Pose(),
        )
        self.contact_marker = actors.build_sphere(
            self.scene,
            radius=0.002,
            color=[1.0, 0.15, 0.1, 0.8],
            name="lego_tool_contact_marker",
            body_type="kinematic",
            add_collision=False,
            initial_pose=sapien.Pose(),
        )

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        qpos = torch.as_tensor(
            RM75LegoTool.keyframes["neutral"].qpos,
            device=self.device,
            dtype=torch.float32,
        ).repeat(len(env_idx), 1)
        self.agent.robot.set_qpos(qpos)
        self.agent.robot.set_qvel(torch.zeros_like(qpos))
        self.update_markers()

    def update_markers(self):
        tcp_pose = self.agent.tcp.pose
        contact_offset_tcp = getattr(self, "contact_offset_tcp", CONTACT_OFFSET_TCP)
        contact_pose = tcp_pose * sapien.Pose(p=contact_offset_tcp)
        self.tcp_marker.set_pose(tcp_pose)
        self.contact_marker.set_pose(contact_pose)

    def evaluate(self):
        return {}

    def _get_obs_extra(self, info: dict):
        return dict()

    def active_joint_names(self):
        return [joint.name for joint in self.agent.robot.get_active_joints()]

    def expected_joint_names(self):
        return ARM_JOINT_NAMES
