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
  scripts/check_load_robot.py
  scripts/run_pick_place.py
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

## 阶段 2：单块 LEGO 场景

先用一个简单 LEGO 尺寸刚体，不要一开始就上复杂 stud/tube 几何。

建议初始 brick：

```text
1x2 brick
size: 16 mm x 8 mm x 9.6 mm
mass: 参考 APEX-MR brick_id 9，约 0.0008 kg
collision: box 或简单 convex mesh
visual: box 或 LEGO mesh
```

坐标约定：

```text
stud pitch: 8 mm
brick height: 9.6 mm
world z: up
baseplate top: z = 0
brick placed center z: 4.8 mm
```

第一版把 brick 放在 RM75 前方一个手写的可达位置。先不要解析完整装配 JSON。

通过标准：

```text
场景里有一个 brick、一个目标位姿 marker，初始状态没有明显穿模。
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

## 阶段 4：下压 Press 验证

ManiSkill 第一版的 press 只验证几何和可达性，不验证真实卡合。

press 要检查：

- press 方向是否和 LEGO 插入方向一致。
- press 距离是否小且可控，先 2 mm，再 5 mm。
- press pose 是否导致腕部姿态不可达。
- retreat 是否会穿过已经放下的 brick。

建议把 press 写成沿 tool 局部轴的小位移，而不是永远沿 world z：

```text
world_T_tcp_press = world_T_tcp_contact * Trans(press_axis_tcp * press_depth)
```

初始参数可以设成：

```text
press_axis_tcp = [0, 0, -1]   # 需要 marker 验证
press_depth = 0.002 到 0.005 m
```

如果仿真里发现 `lego_tool_tcp` 的 +Z 才是插入方向，就把 axis 改成 `[0, 0, 1]`。

几何成功条件：

```text
abs(placed_xy_error) <= 2 mm
abs(placed_yaw_error) <= 5 deg
abs(placed_z_error) <= 2 mm
press_depth >= configured_min_depth
```

通过标准：

```text
同一个手写目标下，完整 pick-place-press-release-retreat 连续 10 次成功。
```

## 阶段 5：Twist 验证

APEX-MR 的 twist 是绕 tool 局部 Y 轴做小角度旋转：

```text
pick_twist  = contact_pose * RotY(+twist_angle)
place_twist = contact_pose * RotY(-twist_angle)
```

默认量级：

```text
twist_angle ≈ 14 deg
handover_twist ≈ 18 deg
```

但这不是 LEGO 物理强制要求，而是原作者 tool frame 下的定义。我们的 RM75
tool 必须先看 marker：

```text
lego_tool_tcp 的 X/Y/Z 轴
contact frame 的 X/Y/Z 轴
tool mesh 的真实接触面
brick 顶面法向
```

如果实际应该绕局部 Z 轴扭，就把 twist axis 改成 Z；如果应该绕局部 X 轴，
就改成 X。抽象层里不要把轴写死在仿真器代码里。

建议参数化：

```text
twist_axis_tcp = [0, 1, 0]    # 先继承 APEX-MR
twist_angle = 14 deg
```

## 阶段 6：Motion Planning 检查

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
