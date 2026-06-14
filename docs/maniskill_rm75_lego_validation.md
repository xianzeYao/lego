# ManiSkill RM75 LEGO 验证路线

这份文档定义一个最快的 ROS-free 验证路线，用来确认我们的单臂 RM75
和自定义 LEGO tool 能不能在 ManiSkill 里完成拿起、移动、放下、下压、
释放这些底层动作。

## 当前判断

当前阶段不需要把 `intelligent-control-lab/Robotic_Lego_Manipulation`
加入 `third_party/`。

原因：

- 现在目标不是复现旧的 ROS/Gazebo manipulation pipeline。
- `third_party/APEX-MR` 已经有我们需要借鉴的 LEGO action 概念：
  `pick_down`、`drop_down`、`press_down`、support pose、LEGO task JSON、
  LEGO library metadata 和多套 tool frame。
- `Robotic_Lego_Manipulation` 主要会再引入一个 ROS 取向的旧实现。只有当
  我们之后需要对比早期 Fanuc/Yaskawa LEGO manipulation baseline 时，才值得补。

当前优先参考这些 APEX-MR 文件：

```text
third_party/APEX-MR/include/lego_policy.h
third_party/APEX-MR/src/lego_policy.cpp
third_party/APEX-MR/config/lego_tasks/assembly_tasks/test.json
third_party/APEX-MR/config/lego_tasks/lego_library.json
third_party/APEX-MR/config/lego_tasks/robot_properties/
```

## 验证目标

先搭一个最小 ManiSkill 场景，回答四个工程问题：

1. ManiSkill 能不能正常加载我们的 RM75 LEGO-tool URDF，mesh 路径、尺度、
   inertia、joint 是否有明显问题。
2. 机械臂能不能到达 LEGO brick 周围的 approach、pick、place、press、
   retreat 位姿。
3. 能不能用 fake attach/release 机制验证抓取、搬运、放置动作。
4. 在做更复杂 LEGO assembly 之前，URDF、tool frame、TCP、collision、
   motion planning 里有哪些坑。

这个验证不证明真实 LEGO 卡合、stud-tube 插入、结构稳定性或 collapse。
这些是后续 BrickSim/Isaac Sim 级别的问题。

## 机器人和 Tool 资产

主机器人：

```text
assets/rm75_gripper/RM75-B/urdf/RM75-B_lego_tool.urdf
```

重要 link 和 joint：

```text
joint_1 ... joint_7
lego_tool_link
lego_tool_tcp
```

当前 URDF 里的 TCP：

```xml
<joint name="lego_tool_tcp_joint" type="fixed">
  <origin xyz="0 0 0.075000" rpy="0 0 0" />
  <parent link="lego_tool_link" />
  <child link="lego_tool_tcp" />
</joint>
```

当前 tool mesh：

```text
assets/rm75_gripper/RM75-B/meshes/lego_test_open_fixed.stl
```

这个 STL 原始坐标是毫米级，URDF 里通过下面的 scale 转成米：

```xml
<mesh filename="../meshes/lego_test_open_fixed.stl" scale="0.001 0.001 0.001" />
```

当前 visual/collision origin 是：

```xml
<origin xyz="0.109847 -0.021913 0.111532"
        rpy="1.57079632679 0 3.14159265359" />
```

按这个 URDF 变换后，tool mesh 在 `lego_tool_link` 坐标系下大约是：

```text
min:    [-0.0375, -0.0375, 0.0000]
max:    [ 0.0375,  0.0375, 0.0599]
center: [ 0.0000,  0.0000, 0.0300]
```

也就是说，当前 mesh 大致以 `lego_tool_link` 为中心，沿 +Z 方向伸出约
60 mm；而 `lego_tool_tcp` 在 `z = 0.075 m`，比 mesh 顶端高约 15 mm。

这不一定是错的，但它说明：**现在的 TCP 不等于 tool 几何接触点**。后续
pick、place、press、twist 都必须明确一个 contact frame，例如：

```text
lego_tool_tcp_T_contact = Trans(0, 0, -0.015)
```

这个 15 mm 只是从包围盒估出来的初值，必须在 ManiSkill 里用 marker 验证。

## 最小 ManiSkill 代码结构

建议新建我们自己的验证包，不放在 `third_party/`：

```text
maniskill_rm75_lego/
  agents/rm75_lego_tool.py
  envs/rm75_lego_pick_place.py
  scripts/run_stage1_robot_load_smoke.py
  scripts/run_stage2_baseplate_scene.py
  scripts/run_stage3_fake_attach_pick_place.py
  scripts/run_stage3_5_tool_frame_calibration.py
  scripts/run_stage4_pick_2x4.py
```

第一版 controller 建议用：

```text
PDJointPosController for joint_1 ... joint_7
```

先不要急着上 end-effector pose controller。先确认 joint-position control
稳定后，再接 IK 或 mplib。

## 阶段 1：机器人加载 Smoke Test

加载 `RM75-B_lego_tool.urdf` 作为 custom ManiSkill agent。

检查项：

- 机器人能出现在地面上方，不炸、不穿地。
- mesh 尺度正确。
- active joints 正好是 `joint_1` 到 `joint_7`。
- `link_7` 后面能看到固定的 tool chain。
- `lego_tool_tcp` 能被查询，或者能通过 `lego_tool_link` 复原出来。
- neutral keyframe 能稳定保持至少 3 秒。
- 在 `lego_tool_tcp` 和估计的 contact frame 上各放一个 marker，确认它们
  和 tool mesh 的相对位置合理。

常见问题：

- DAE/STL 相对路径解析失败。
- collision mesh 太细，导致仿真慢或者接触不稳定。
- inertial 参数对 SAPIEN 不友好。
- `lego_test_open_fixed.stl` 是毫米单位，必须确认 ManiSkill/SAPIEN 的
  URDF loader 正确应用了 `scale="0.001 0.001 0.001"`。

通过标准：

```text
机器人能加载，neutral qpos 能稳定保持，每个 joint 都能在 PD joint position
control 下正常运动。
```

## 阶段 2：baseplate 网格 LEGO 场景

从 Robot_Digital_Twin 加载 `base32x32.stl`，并把 `1x2`、`1x4`、`2x4`
LEGO brick 按 APEX-MR 风格的 8 mm 网格坐标摆在 baseplate 上。

核心代码：

```text
maniskill_rm75_lego/lego_grid.py
maniskill_rm75_lego/envs/rm75_lego_pick_place.py
maniskill_rm75_lego/scripts/run_stage2_baseplate_scene.py
```

坐标约定：

```text
stud pitch: 8 mm
brick height: 9.6 mm
world z: up
baseplate bottom: z = 0
baseplate top/grid reference: z = 0.0032
brick actor origin z: brick bottom z + 0.0096
```

当前放置：

```text
lego_1x1: grid [2, 2, 0, 0]
lego_1x2: grid [5, 3, 0, 1]
lego_1x4: grid [9, 2, 0, 0]
lego_1x6: grid [15, 3, 0, 1]
lego_1x8: grid [20, 2, 0, 0]
lego_2x2: grid [3, 12, 0, 0]
lego_2x4: grid [8, 12, 0, 1]
lego_2x6: grid [14, 13, 0, 0]
lego_2x8: grid [22, 13, 0, 1]
target:   1x2 grid [25, 23, 0, 0]
```

本阶段仍是几何/坐标检查，不验证真实 snap/contact。

通过标准：

```text
baseplate 和三块 LEGO 能按网格位置稳定初始化，grid pose 和 world pose
打印值一致，target marker 位于指定 1x2 目标格点。
```

## 阶段 3：Fake Attach Pick And Place

第一版动作序列：

```text
home
move pre_pick above brick
move pick/contact
fake_attach brick to contact frame
move lift
move pre_place above target
move place/contact
move press 2-5 mm
fake_release brick at target pose
move retreat
```

fake attach 推荐第一版用任务逻辑实现：

```text
attached 时，每个 step 手动设置：
world_T_brick = world_T_contact * contact_T_brick
```

不要第一版就靠摩擦/碰撞真实夹住 LEGO。那会把 tool frame 问题、接触参数问题、
质量问题混在一起，很难定位。

通过标准：

```text
brick 在 lift 和 transfer 阶段跟随 tool，release 后停在目标位置。
```

## 阶段 4：2x4 Pick + Twist Motion

先解决取 LEGO 的几何目标和基础 IK 动作。这个阶段只验证 motion 是否
按实体动作语义走通，不验证 LEGO 是否真的被物理撬起来。

Pick 动作总结：

```text
brick type + grid [x,y,z,ori] + press_side + press_offset
    -> 选出邻边附近的两个 selected studs
    -> 计算 stud pair center
    -> 从 stud pair center 向邻边作垂线得到 pick contact target
    -> 构造 contact frame
       +X: 工具有墙/工作侧方向，和邻边 outward normal 同向
       +Z: press direction，和当前 lego_tool_tcp 的 +Z 同向，也就是 world down
    -> T_world_tcp = T_world_contact * inverse(T_tcp_contact)
    -> IK 求 pre_pick、pick_down、pick_twist、pick_twist_up
```

Motion waypoint：

```text
home
pre_pick        # contact 点在 pick target 正上方
pick_down       # 沿 press direction 下压到目标附近
pick_twist      # 绕 contact frame 局部 Y 轴 twist，当前 RM75 默认 -14 deg
pick_twist_up   # 保持 twist 后姿态，沿 world +Z 抬起
```

当前第一版默认：

```text
brick: lego_2x4
grid: [8, 12, 0, 1]
press_side: 1
press_offset: 0
T_tcp_contact = Trans(0, 0, -0.015)
tcp_orientation = apex
```

APEX-MR 风格下，当前 RM75 迁移后的约定是：

```text
tool wall side direction = +contact_frame.x
press direction          = +contact_frame.z
```

它应该和 `outward normal` 同向。当前严格 APEX 姿态 IK 未收敛时，脚本会自动 fallback 到
`executed_tcp_orientation = home` 执行动作，但仍显示 APEX 几何方向供检查。

对应脚本：

```text
maniskill_rm75_lego/scripts/run_stage4_pick_2x4.py
```

通过标准：

```text
pre_pick -> pick_down -> pick_twist -> pick_twist_up 四个 waypoint IK 成功，
viewer 中 selected studs、pick target、contact/TCP/pre/twist frame 显示合理。
```

## 阶段 5：Pick Dynamic 验证

在阶段 4 motion 已经确认的基础上，开始验证真实接触/动力学下 pick 是否能成立。
这个阶段要回答：

- LEGO brick 是否可以从 baseplate 上被工具真实撬起。
- 下压深度、twist 角度、contact offset、摩擦/碰撞参数是否足够稳定。
- 机械臂 base 固定、baseplate 固定时，目标 brick 是否能从 plate 脱离并跟随工具。
- 不再用 fake attach 作为成功条件；fake attach 只能作为 debug 对照。

建议第一版 success metric：

```text
pick_down 后有合理接触
pick_twist 后 brick 姿态/高度发生符合撬起方向的变化
pick_twist_up 后 brick 离开 baseplate 且相对 tool 位姿变化小
```

需要重点调：

```text
collision shape
friction / restitution
brick mass / inertia
press_depth
pick_twist_deg
contact_offset_tcp
```

## 阶段 6：Place + Twist Motion

在 pick motion 的坐标计算稳定后，再做 place motion。这个阶段仍然只验证
几何和 IK，不验证真实卡合。

Place 动作预期：

```text
home 或 picked pose
pre_place       # contact/brick 目标在目标格点上方
place_down      # 对齐目标 studs 后下压
place_twist     # 使用无柱/释放侧方向 twist，让 LEGO 完成 place 语义
place_up        # 保持或解除接触后抬起
```

本阶段需要复用阶段 2 的 LEGO grid pose 计算：

```text
target brick type
target grid [x,y,z,ori]
target occupied studs
place contact target
place contact frame
pre_place / place_down / place_twist / place_up TCP frame
```

place twist 的符号和轴不要直接照搬 pick。它要按实体工具的无柱一侧释放逻辑
单独确认。

## 阶段 7：Place Dynamic 验证

在阶段 6 place motion 通过后，验证真实动力学下 LEGO 是否能放稳/卡上。

这个阶段要回答：

- brick 是否能对齐 baseplate 或已有 LEGO 的目标 studs。
- 下压和 twist 后 brick 是否停在目标 grid pose 附近。
- 工具抬起后 brick 是否留在 plate/目标结构上，而不是跟着工具走或弹飞。
- pick dynamic 成功得到的接触参数，能不能迁移到 place。

建议第一版 success metric：

```text
place_down 后 brick 与目标 studs 对齐
place_twist 后 brick 姿态接近目标 grid pose
place_up 后 brick 留在目标位置
位置误差 < 2-3 mm
yaw/ori 误差在可接受范围内
```

## 阶段 8：Motion Planning 检查

scripted joint targets 能跑通后，再测试 `mplib` 能不能规划同样的 waypoint。

先测这些点：

```text
pre_pick
pick/contact
lift
pre_place
place/contact
press
retreat
```

如果 `mplib` 失败，先检查：

- collision mesh 是否太复杂。
- self-collision pair 是否需要 disable。
- planning end-effector frame 是否应该是 `lego_tool_tcp` 或 contact frame。
- approach/place pose 是否超出 RM75 工作空间。
- URDF joint limit 是否正确。

通过标准：

```text
至少 pre_pick、lift、pre_place、retreat 可以由 planner 生成。
```

## APEX-MR 动作如何迁移

APEX-MR 不是纯硬编码 waypoint。它大致是：

```text
LEGO 网格坐标 + brick 尺寸 + press_side/press_offset
    -> 计算 brick/contact pose

tool DH / tool frame variants
    -> 计算机器人 TCP pose

经验 offset / twist angle
    -> 生成 pre-pick、pick、twist、press、retreat
```

其中 LEGO 尺寸常量是：

```text
P_len = 0.008 m
brick_height = 0.0096 m
lever_wall_height = 0.0032 m
```

`press_side` 表示从 brick 的哪一侧压，`press_offset` 表示沿那一侧选哪个压点。
这些可以迁移成我们自己的 `brick_T_contact` 或 `brick_T_tcp` 计算。

APEX-MR 里也有经验 offset，例如：

```text
place brick offset: [-5 mm, +5 mm, -5 mm]
grab brick offset:  [-5 mm, +5 mm, -2.8 mm]
```

这些不是从 STL 自动算出来的，而是和 tool、真实实验、装配容差有关的手工标定值。
我们的 RM75 tool 必须重新标定，不能直接照搬。

## 已知坑

- `lego_tool_tcp` 现在比 tool mesh 顶端高约 15 mm。它可以作为规划 TCP，但不一定是
  物理接触点。
- 下压和 twist 应该围绕 contact frame 做，而不是围绕 mesh 原点做。
- URDF fixed link 在 ManiSkill/SAPIEN 里可能被处理得和预期不同，必须用 marker 验证。
- RM75 是 7 轴，很多 ManiSkill 例子默认 Panda 7 轴加 gripper finger，不要套错 controller。
- 高精度 collision mesh 可能导致接触很慢或不稳定。第一版优先用简单 collision。
- LEGO 质量很小。如果接触不稳定，先用 fake attach，或者临时增大质量。
- 第一版 success metric 用几何误差，不要用 force。

## 后续什么时候补 Robotic_Lego_Manipulation

只有以下情况发生时再补：

- 要和旧的轻量 LEGO manipulation paper code 对比。
- 要复现 Fanuc/Yaskawa 的旧 skill 参数。
- 要做 ROS/Gazebo baseline。

否则当前阶段继续用 APEX-MR 的动作概念即可。
