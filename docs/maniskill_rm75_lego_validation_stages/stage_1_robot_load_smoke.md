# 阶段 1：机器人加载 Smoke Test

日期：2026-06-14

对应主路线：

```text
docs/maniskill_rm75_lego_validation.md
```

## 目标

验证 `RM75-B_lego_tool.urdf` 能在 ManiSkill/SAPIEN 中加载，并且：

- active joints 正好是 `joint_1` 到 `joint_7`。
- `lego_tool_link` 和 `lego_tool_tcp` 能被查询。
- `pd_joint_pos` 能稳定保持指定 home qpos。

统一 home：

```text
home_q_rad = [1.5707964, 0.0, 0.0, -1.5707964, 0.0, -1.5707964, 1.0471976]
home_q_deg = [90, 0, 0, -90, 0, -90, 60]
```
- TCP/contact marker 机制已经接入，后续可用于可视化校准。

## 新增代码

```text
maniskill_rm75_lego/
  agents/rm75_lego_tool.py
  envs/rm75_lego_smoke.py
  scripts/run_stage1_robot_load_smoke.py
```

## 运行命令

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage1_robot_load_smoke.py --steps 60
```

## 结果

通过。

关键输出：

```text
URDF: /home/yxz/lego/assets/rm75_gripper/RM75-B/urdf/RM75-B_lego_tool.urdf
active joints: ['joint_1', 'joint_2', 'joint_3', 'joint_4', 'joint_5', 'joint_6', 'joint_7']
link count: 11
has lego_tool_link: True
has lego_tool_tcp: True
initial qpos: [1.570796, 0.0, 0.0, -1.570796, 0.0, -1.570796, 1.047198]
initial qvel max abs: 0.0
tcp pose p: [0.0, -0.21, 0.2695]
final max qpos error from neutral: 0.0
final max qvel: 0.0
final tcp pose p: [0.0, -0.21, 0.2695]
PASS: RM75 LEGO tool loads and holds neutral under pd_joint_pos
```

## 判断

阶段 1 的 headless smoke test 通过。

这说明：

- URDF mesh 相对路径至少没有阻止加载。
- ManiSkill active joint 识别正确，没有把 fixed tool chain 当 active joint。
- `lego_tool_tcp` fixed link 没有在加载时丢失。
- 指定 home 姿态可以作为后续 scripted motion 的底座。

## 注意事项

- 当前机器没有可用 CUDA/NVML，ManiSkill fallback 到 CPU render device。
- 这次只证明 headless 加载和控制稳定；mesh 尺度、TCP/contact marker 的视觉关系还需要 GUI render 或截图补验。
- 当前 `mplib` 导入会因为 `toppra` 与 `numpy 2.2.6` ABI 不兼容失败；阶段 6 前需要把环境修到 `numpy<2` 或重装兼容版本。
