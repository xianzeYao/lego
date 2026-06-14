from __future__ import annotations

from pathlib import Path

import numpy as np
import sapien

from mani_skill.agents.base_agent import BaseAgent, Keyframe
from mani_skill.agents.controllers import PDJointPosControllerConfig
from mani_skill.agents.registration import register_agent


REPO_ROOT = Path(__file__).resolve().parents[2]
ARM_JOINT_NAMES = [f"joint_{i}" for i in range(1, 8)]
HOME_Q_DEG = np.array([90.0, 0.0, 0.0, -90.0, 0.0, -90.0, 60.0])
HOME_Q_RAD = np.array(
    [1.5707964, 0.0, 0.0, -1.5707964, 0.0, -1.5707964, 1.0471976],
    dtype=np.float32,
)


@register_agent()
class RM75LegoTool(BaseAgent):
    uid = "rm75_lego_tool"
    urdf_path = str(
        REPO_ROOT
        / "assets"
        / "rm75_gripper"
        / "RM75-B"
        / "urdf"
        / "RM75-B_lego_tool.urdf"
    )
    urdf_config = dict()
    fix_root_link = True

    keyframes = dict(
        neutral=Keyframe(
            pose=sapien.Pose(),
            qpos=HOME_Q_RAD,
        )
    )

    @property
    def _controller_configs(self):
        return dict(
            pd_joint_pos=PDJointPosControllerConfig(
                ARM_JOINT_NAMES,
                lower=None,
                upper=None,
                stiffness=1000,
                damping=100,
                force_limit=100,
                normalize_action=False,
            )
        )

    def _after_init(self):
        self.tcp = self.robot.links_map["lego_tool_tcp"]
        self.tool_link = self.robot.links_map["lego_tool_link"]

    @property
    def tcp_pose(self):
        return self.tcp.pose

    @property
    def tcp_pos(self):
        return self.tcp.pose.p
