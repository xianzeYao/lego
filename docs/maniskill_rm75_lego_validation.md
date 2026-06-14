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

## ManiSkill 安装和环境检查

第一版建议用独立 conda 环境，不和 ROS、Isaac Sim、BrickSim 混在一起。

推荐 Linux/NVIDIA 环境；macOS 可以先做代码和轻量 smoke test，但图形、物理后端、
GPU 加速和部分依赖更容易遇到兼容问题。真正验证机器人运动建议放到 Linux 机器上。

推荐安装流程：

```bash
conda create -n maniskill-lego python=3.10 -y
conda activate maniskill-lego
python -m pip install --upgrade pip setuptools wheel
pip install mani-skill
```

如果机器上有 `mamba`，可以把第一行换成：

```bash
mamba create -n maniskill-lego python=3.10 -y
```

如果要测试 motion planning，确认 `mplib` 可用：

```bash
python - <<'PY'
import mani_skill
import sapien
import mplib
print("mani_skill", mani_skill.__file__)
print("sapien", sapien.__version__ if hasattr(sapien, "__version__") else sapien.__file__)
print("mplib", mplib.__file__)
PY
```

安装后先跑官方环境，不要直接上 RM75：

```bash
python -m mani_skill.examples.demo_random_action -e PickCube-v1 --render-mode human
```

如果 headless 机器没有显示器，先用 offscreen/rgb_array 模式确认能 step：

```bash
python -m mani_skill.examples.demo_random_action -e PickCube-v1 --render-mode rgb_array
```

通过标准：

```text
ManiSkill 能 import，官方 demo 能 reset/step/render，没有 Vulkan/GPU/display 报错。
```

如果这里失败，先不要调 RM75 URDF。优先解决 Python 版本、显卡驱动、Vulkan、
显示后端或 ManiSkill 安装问题。

## 验证目标

先搭一个最小 ManiSkill 场景，回答四个工程问题：

1. ManiSkill 能不能正常加载我们的 RM75 LEGO-tool URDF，mesh 路径、尺度、
   inertia、joint 是否有明显问题。
2. 机械臂能不能到达 LEGO brick 周围的 approach、pick、place、press、
   retreat 位姿。
3. 能不能按 APEX-MR 的 LEGO 动作语义生成 pick/drop/press/twist waypoint，
   只把物体 attach/release 事件临时 fake 掉。
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

## 换臂后的 Frame 标定

换成 RM75 后，LEGO 动作结构可以沿用，但坐标系必须重新标定。

必须明确这些变换：

```text
world_T_robot_base
robot_base_T_flange        # 由 RM75 URDF + joint state / FK 决定
flange_T_lego_tool_link    # tool 如何装到法兰
lego_tool_link_T_tcp       # URDF 里的 lego_tool_tcp
tcp_T_contact              # TCP 到真实接触点
```

动作几何层只关心末端：

```text
brick pose -> contact pose -> tcp pose
```

执行层才关心整条机械臂：

```text
tcp pose -> IK / motion planning -> joint_1 ... joint_7
```

所以换臂时通常不需要重写 LEGO 网格、brick pose、pick/place/press/retreat
这些动作结构；要重做的是：

```text
base frame
tool mounting frame
TCP frame
contact frame
press axis
twist axis
IK/planner 配置
```

在 ManiSkill 里第一步应该可视化 4 个 marker：

```text
robot base frame
lego_tool_link
lego_tool_tcp
contact frame
```

如果 marker 不对，先修 URDF/tool frame，不要继续调动作参数。

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

## 实施顺序总览

按下面顺序推进，不要跳步：

```text
0. 安装 ManiSkill 并跑官方 demo
1. 只加载 RM75-B_lego_tool.urdf
2. 可视化 lego_tool_link / lego_tool_tcp / contact frame
3. 加载两块 baseplate 和一块 2x4 brick
4. 用手写 joint qpos 让 RM75 到几个安全姿态
5. 用手写 TCP waypoint 验证 pre_pick/contact/lift/pre_place/place
6. 按 APEX-MR 动作序列生成 pick/drop waypoint
7. 只对 attach/release 用 fake 事件
8. 加 APEX-MR 风格 press/twist，并重标定 RM75 的 axis/center
9. 再接 mplib 做 motion planning
```

每一步都要能单独跑通。比如 robot load 不稳定时，不要继续加 brick；TCP/contact
marker 不对时，不要继续写 pick/drop；APEX-MR 风格 waypoint 没跑稳时，
不要调真实接触。

## Step 0：环境 Smoke Test

目标：

```text
确认 ManiSkill/SAPIEN 能正常 import、reset、step、render。
```

命令：

```bash
conda activate maniskill-lego
python - <<'PY'
import mani_skill
import sapien
print("mani_skill:", mani_skill.__file__)
print("sapien:", sapien.__version__ if hasattr(sapien, "__version__") else sapien.__file__)
PY
```

再跑官方 demo：

```bash
python -m mani_skill.examples.demo_random_action -e PickCube-v1 --render-mode human
```

headless 机器：

```bash
python -m mani_skill.examples.demo_random_action -e PickCube-v1 --render-mode rgb_array
```

通过标准：

```text
能创建环境、reset、step、render，不出现 Vulkan/display/import 错误。
```

失败优先查：

```text
Python 版本
conda 环境是否激活
NVIDIA driver / Vulkan
DISPLAY / headless 渲染配置
mani-skill 是否装在当前 conda 环境
```

## Step 1：资产存在性和尺度检查

目标：

```text
在进入 ManiSkill 前，先确认所有验证资产路径存在，尺度符合预期。
```

必须存在：

```text
assets/rm75_gripper/RM75-B/urdf/RM75-B_lego_tool.urdf
assets/rm75_gripper/RM75-B/meshes/lego_test_open_fixed.stl
assets/generated_urdf/robot_digital_twin/lego_baseplate.urdf
assets/generated_urdf/robot_digital_twin/lego_2x4.urdf
```

预期尺度：

```text
baseplate: 384 mm x 384 mm x 3.2 mm
2x4 brick: 32 mm x 16 mm x 9.6 mm
RM75 tool mesh: 约 75 mm x 75 mm x 60 mm after URDF transform
```

通过标准：

```text
URDF mesh 路径能解析；STL scale 不出现 1000 倍错误；baseplate 和 brick 都是米单位场景可用尺寸。
```

失败优先查：

```text
URDF 相对路径
STL 是否毫米单位但漏了 scale=0.001
ManiSkill/SAPIEN 是否支持该 mesh 格式
是否需要复制一份带绝对 mesh 路径的临时 URDF
```

## Step 2：RM75 单独加载

目标：

```text
只加载 RM75，不放 baseplate，不放 brick。
```

加载文件：

```text
assets/rm75_gripper/RM75-B/urdf/RM75-B_lego_tool.urdf
```

检查：

```text
active joints = joint_1 ... joint_7
fixed links 包含 flange_spacer_8mm、lego_tool_link、lego_tool_tcp
robot base 不穿地
neutral qpos 下不抖、不炸
```

第一版 controller：

```text
PDJointPosController(joint_1 ... joint_7)
```

通过标准：

```text
RM75 能保持 neutral qpos 3 秒；单独给每个 joint 一个小位移时，运动方向和 URDF 预期一致。
```

失败优先查：

```text
joint axis 是否正确
joint limit 是否太紧或错误
inertial 是否导致不稳定
collision mesh 是否太复杂
tool STL scale 是否被正确应用
```

## Step 3：Frame Marker 验证

目标：

```text
确认动作要绑定的 frame，不要靠肉眼猜 mesh。
```

至少画 4 个 marker：

```text
robot_base
lego_tool_link
lego_tool_tcp
contact_frame
```

当前估计：

```text
lego_tool_link_T_tcp = Trans(0, 0, 0.075)
lego_tool_tcp_T_contact = Trans(0, 0, -0.015)   # 初值，必须验证
```

要看清楚：

```text
lego_tool_tcp 是否在 tool 外侧合理位置
contact_frame 是否落在真实接触面附近
contact_frame 的 Z 轴是否能作为 press 方向候选
contact_frame 的 X/Y/Z 哪个适合作为 twist axis
```

通过标准：

```text
marker 和 tool mesh 的相对关系符合直觉；能明确说出 press_axis 和 twist_axis 的候选。
```

失败优先查：

```text
URDF fixed joint origin
mesh visual/collision origin
STL 原始坐标是否远离原点
tcp_T_contact 初值是否方向反了
```

## Step 3.5：Tool Calibration 逐步标定

目标：

```text
把新 tool 的几何关系收敛成一组参数，而不是每个动作里到处写 magic offset。
```

最终动作函数只读这一组参数：

```text
ToolCalibration:
  tcp_T_contact
  press_axis_contact
  twist_axis_contact
  twist_center_contact
  grab_offset_brick
  place_offset_brick
  approach_height
  lift_height
  press_depth
  twist_angle
```

建议按下面顺序标定，不要一次性调所有量。

### 1. 标定 `tcp_T_contact`

含义：

```text
TCP 到真实接触点的刚体变换。
```

它不是 brick pose，也不是 tool mesh 原点。它只描述：

```text
当 planner 把 lego_tool_tcp 放到某个位姿时，真实接触面/接触边在哪里。
```

当前 RM75 tool 的初值可以从包围盒估：

```text
tcp_T_contact = Trans(0, 0, -0.015)
```

逐步做法：

```text
1. 在 ManiSkill 里同时画 lego_tool_tcp 和 contact_frame marker。
2. 手动给一个安全 joint qpos，让 tool 靠近一块静止 LEGO brick。
3. 不做 press/twist，只让 contact_frame 对准 brick 顶面或侧边候选接触点。
4. 如果 TCP 看起来对了但接触面悬空/穿模，只改 tcp_T_contact。
5. 先只调 z；如果接触点横向偏了，再调 x/y。
6. 如果 tool 方向不对，再调 tcp_T_contact 的 rotation。
```

通过标准：

```text
contact_frame 落在 tool 真实接触面上；把 contact_frame 对到 brick 接触点时，
tool mesh 不明显穿 brick，也不会离 brick 很远。
```

### 2. 标定 `press_axis_contact` 和 `press_depth`

含义：

```text
press_axis_contact 是在 contact frame 下的下压方向。
press_depth 是每次压实要沿这个方向走多深。
```

初值：

```text
press_axis_contact = contact local -Z 或 +Z，取决于 marker 方向
press_depth = 0.002 m
```

逐步做法：

```text
1. 禁用 twist，只做 press_up -> press_down -> press_retreat。
2. 从 1 mm 开始，不要一上来用 5 mm。
3. 如果 tool 离开 brick，说明 press_axis 方向反了。
4. 如果明显穿透或把 brick 打飞，说明 press_depth 太大或 contact_frame 偏了。
5. 稳定后从 1 mm 增到 2 mm，再看是否需要 3-5 mm。
```

通过标准：

```text
press_down 后 brick 目标 pose 误差变小或保持稳定；tool 没有明显横向刮碰。
```

### 3. 标定 `twist_axis_contact`、`twist_center_contact` 和 `twist_angle`

含义：

```text
twist_axis_contact 是撬/扭时绕哪根轴转。
twist_center_contact 是绕哪个点转，通常先设为 contact point。
twist_angle 是扭转角度，APEX-MR 可给 14 deg 初值。
```

APEX-MR 的经验可以这样迁移：

```text
pick_twist 和 drop_twist 方向相反
twist_angle 初值 14 deg
轴不要照搬原 robot local Y，必须在 RM75 contact frame 里重新选
```

候选搜索：

```text
RotX(+14), RotX(-14)
RotY(+14), RotY(-14)
RotZ(+14), RotZ(-14)
```

逐步做法：

```text
1. 先把 tcp_T_contact 和 press_axis 调到基本正确。
2. 固定 brick，不 fake attach，只看 tool 运动轨迹是否像撬。
3. 试 6 个 twist 候选，观察 tool 尖端是否绕接触边/接触点运动。
4. 选出不穿模、不远离 brick、方向符合“撬起”的候选轴。
5. 再把角度从 5 deg、10 deg、14 deg 逐步增大。
6. 如果轨迹像绕 TCP 空转，改 twist_center_contact。
```

通过标准：

```text
pick_twist 能制造合理的撬起趋势；drop_twist 方向相反，能把 brick 放回目标位姿附近。
```

### 4. 标定 `grab_offset_brick` 和 `place_offset_brick`

含义：

```text
这些 offset 是 brick 坐标系到期望 contact pose 的经验偏置。
它们和 tool 尖端厚度、LEGO 容差、目标 press_side 有关。
```

APEX-MR 初值只能作为参考：

```text
grab_offset_brick  ~= [-5 mm, +5 mm, -2.8 mm]
place_offset_brick ~= [-5 mm, +5 mm, -5.0 mm]
```

RM75 第一版建议更保守：

```text
1. 先用 brick 顶面中心或边缘中心作为 contact pose。
2. 能稳定接近后，再按 press_side 把 contact pose 移到 brick 边缘。
3. x/y 每次只改 1-2 mm。
4. z 每次只改 0.5-1 mm。
5. 调到 pick 不刮旁边 studs，drop 能落到目标格附近。
```

通过标准：

```text
同一块 2x4 brick 能在 3 个目标位置重复 pick/drop/press，
放置后 xy <= 2 mm，z <= 2 mm，yaw <= 5 deg。
```

### 5. 换新头时怎么复用

如果新头只是长度变了，且接触面方向、撬动方式、press/twist 轴都没变，通常只改：

```text
tcp_T_contact.z
```

如果新头改变了接触面或安装角度，需要重新标定：

```text
tcp_T_contact rotation
press_axis_contact
twist_axis_contact
twist_center_contact
grab_offset_brick
place_offset_brick
```

动作函数本身不要因为换头而重写。正确边界是：

```text
动作函数：brick pose + target pose + ToolCalibration -> TCP waypoint
planner：TCP waypoint -> joint trajectory
```

## Step 4：双 Baseplate 场景

目标：

```text
加载 RM75 + source plate + target plate，不放 brick。
```

建议 layout 初值：

```text
source_plate_pose = Trans(+0.35, -0.12, 0.0)
target_plate_pose = Trans(+0.35, +0.18, 0.0)
```

这里的 `z = 0.0` 是 plate mesh 中心高度；因为 baseplate 高 3.2 mm，所以：

```text
baseplate_top_z = 0.0016
```

通过标准：

```text
两块 plate 在 RM75 前方可见；RM75 不和 plate 初始穿模；两个 plate 都在可达空间附近。
```

失败优先查：

```text
plate pose 是否太近导致碰撞
plate 是否超出 RM75 工作空间
world z / plate center z / top z 是否混淆
```

## Step 5：放置 2x4 Brick

目标：

```text
在 source plate 上放一块 2x4 brick，并在 target plate 上画目标 marker。
```

资产：

```text
assets/generated_urdf/robot_digital_twin/lego_2x4.urdf
```

第一版推荐：

```text
visual 使用 lego_2x4 的 mesh
collision 使用 32 mm x 16 mm x 9.6 mm box
```

高度：

```text
brick_center_z = baseplate_top_z + 0.0096 / 2
               = plate_pose.z + 0.0016 + 0.0048
               = plate_pose.z + 0.0064
```

如果 `plate_pose.z = 0.0`：

```text
brick_center_z = 0.0064 m
```

通过标准：

```text
source brick 稳定放在 source plate 上；target marker 位于 target plate 上方同样高度；
brick 和 plate 没有明显穿模。
```

失败优先查：

```text
brick origin 是中心还是底面
brick mesh scale 是否正确
baseplate top z 是否算错
collision box 是否和 visual mesh 对齐
```

## Step 6：按 APEX-MR 动作语义生成 Waypoint

目标：

```text
先不接 planner，但 waypoint 结构要参考 APEX-MR 的已有 LEGO 动作，
不是随便写一个普通 pick-place。
```

APEX-MR 里相关动作定义在：

```text
third_party/APEX-MR/include/task.h
third_party/APEX-MR/src/lego_policy.cpp
third_party/APEX-MR/src/exe/lego_assignment.cpp
third_party/APEX-MR/src/lego/Lego.cpp
```

第一版要迁移的动作语义：

```text
pick_tilt_up / pick_up / pick_down / pick_twist / pick_twist_up
drop_tilt_up / drop_up / drop_down / drop_twist / drop_twist_up
press_down
```

对应到 ManiSkill 的 source -> target 任务：

```text
pick_tilt_up    = source_contact_pose 加 APEX-MR grab offset 的预接近姿态
pick_up         = source_contact_pose 上方安全高度
pick_down       = source_contact_pose，沿 tool/contact 方向压到接触
pick_twist      = pick_down 后绕重标定的 twist_axis 扭动
pick_twist_up   = twist 后抬起

drop_tilt_up    = target_contact_pose 加 APEX-MR place offset 的预接近姿态
drop_up         = target_contact_pose 上方安全高度
drop_down       = target_contact_pose，沿 tool/contact 方向压到放置接触
drop_twist      = drop_down 后反向扭动
drop_twist_up   = twist 后回撤
press_down      = 放置后做小距离压紧
```

核心关系：

```text
world_T_tcp = world_T_contact * inverse(tcp_T_contact)
```

如果暂时不用完整 4x4 变换，只做竖直场景，可先用：

```text
tcp_z = contact_z + 0.015
```

APEX-MR 的经验参数要作为初值：

```text
grab brick offset:  [-5 mm, +5 mm, -2.8 mm]
place brick offset: [-5 mm, +5 mm, -5 mm]
twist_angle:        约 14 deg
press/down motion:  先不要照搬 50 mm，ManiSkill 第一版用 2-5 mm 验证接触附近动作
```

注意：APEX-MR 代码里的 50 mm 下压/抬起包含了它们的 tool frame、任务姿态和硬件执行语义。
RM75/ManiSkill 第一版不要机械照搬这个距离；动作结构要参考，具体深度要重标定。

通过标准：

```text
RM75 可以到达 pick_up、pick_down、pick_twist_up、drop_up、drop_down、
drop_twist_up；contact pose 不明显穿模。
```

失败优先查：

```text
contact_frame 是否放错
TCP 是否比 contact 多补了 15 mm
waypoint 是否超出 RM75 可达空间
tool 是否撞 plate 或 brick
是否把 APEX-MR 的 tool axis 直接套到了 RM75 tool frame
```

## 动作函数接口定义

第一版要把 LEGO 操作抽象成函数。函数不直接输出 joint，也不直接调用仿真器。
函数只输出：

```text
TCP waypoint list
attach/release event
每个 waypoint 的动作语义标签
```

motion planning 层再负责：

```text
TCP waypoint -> IK / trajectory / collision check -> joint trajectory
```

### 通用输入

每个动作函数都接受同一类输入：

```text
SceneFrames:
  world_T_robot_base
  world_T_source_plate
  world_T_target_plate

BrickTask:
  brick_id
  source_brick_pose
  target_brick_pose
  press_side
  press_offset
  brick_orientation

BrickSpec:
  studs_x
  studs_y
  height_m
  mass

ToolCalibration:
  tcp_frame_name
  tcp_T_contact
  press_axis_contact
  twist_axis_contact
  twist_center
  grab_offset
  place_offset
  approach_height
  lift_height
  press_depth
  twist_angle
```

输入来源：

```text
brick_id / press_side / press_offset / brick_orientation:
  参考 APEX-MR task JSON 和 lego_assignment 里的字段。

brick size / mass:
  参考 APEX-MR lego_library.json。

grab_offset / place_offset / twist_angle:
  参考 APEX-MR 初值，但 RM75 必须重标定。

tcp_T_contact / press_axis / twist_axis / twist_center:
  由 RM75 tool marker 和实际 tool 形状标定。
```

### 通用输出

输出统一为：

```text
LegoMotionPlan:
  waypoints:
    - name
    - world_T_tcp
    - semantic_type
    - expected_event_before
    - expected_event_after
  events:
    - attach_brick
    - release_brick
  success_checks:
    - tcp_pose_tolerance
    - brick_pose_tolerance
    - collision_free_required
```

其中 `world_T_tcp` 是 motion planner 的输入。planner 不需要知道 LEGO 语义，
只需要把每个 TCP pose 解成可执行轨迹。

### 必须实现的动作函数

第一版至少实现 5 个函数：

```text
make_pick_sequence(task, brick_spec, tool_calib) -> LegoMotionPlan
make_transfer_sequence(task, brick_spec, tool_calib) -> LegoMotionPlan
make_drop_sequence(task, brick_spec, tool_calib) -> LegoMotionPlan
make_press_sequence(task, brick_spec, tool_calib) -> LegoMotionPlan
make_pick_drop_task(task, brick_spec, tool_calib) -> LegoMotionPlan
```

`make_pick_sequence` 输出：

```text
pick_tilt_up
pick_up
pick_down
pick_twist
pick_twist_up
event: attach_brick after pick_twist 或 pick_down
```

`make_transfer_sequence` 输出：

```text
lift / transfer_safe / pre_drop
```

`make_drop_sequence` 输出：

```text
drop_tilt_up
drop_up
drop_down
drop_twist
drop_twist_up
event: release_brick after drop_twist 或 press_down
```

`make_press_sequence` 输出：

```text
press_up
press_down
press_retreat
```

`make_pick_drop_task` 把上面串起来：

```text
pick sequence
transfer sequence
drop sequence
press sequence
retreat
```

### 函数边界

动作函数不做：

```text
IK
轨迹插值
碰撞检测
仿真 step
真实接触求解
```

动作函数只做：

```text
根据 APEX-MR 动作语义和 RM75 tool 标定，计算动作结束时 TCP 应该去的点。
```

这意味着如果换仿真器，只需要复用这些 `world_T_tcp` waypoint；如果换机械臂，
动作函数尽量不变，更新 `ToolCalibration` 和 planner/IK 即可。

## Step 7：Fake Attach / Release 只替代物体连接事件

目标：

```text
保留 APEX-MR 的 pick/drop/press/twist waypoint 结构，只把“积木是否被工具带走”
这个物理连接事件临时 fake 掉。
```

这里的 fake 不代表动作是假的。fake 的只有：

```text
真实摩擦抓取
真实 LEGO 卡合/脱开
真实 tool-brick 约束
```

仍然要按 APEX-MR 的动作顺序执行：

```text
pick_down -> pick_twist -> pick_twist_up -> transfer
drop_down -> drop_twist -> drop_twist_up -> press_down
```

attach 事件：

```text
在 pick_down / pick_twist 成功到达后记录：
contact_T_brick = inverse(world_T_contact) * world_T_brick

attached=True 后每个 step 更新：
world_T_brick = world_T_contact * contact_T_brick
```

release 事件：

```text
在 drop_down / drop_twist / press_down 后：
attached=False
world_T_brick = target_brick_pose
```

通过标准：

```text
brick 从 source plate 离开，lift/transfer 阶段跟着 tool，release 后落在 target plate 目标位置。
```

失败优先查：

```text
attach 时 contact_T_brick 是否记录反了
更新 brick pose 时是否用 TCP pose 代替了 contact pose
release 后 target_brick_pose 高度是否正确
fake attach 是否发生在 APEX-MR 语义里的 pick_down/pick_twist 后，而不是 pre_pick 阶段
```

## Step 8：APEX-MR 风格 Press 和 Twist

目标：

```text
把 APEX-MR 的 press/twist 语义迁移到 RM75 tool frame。
```

press 初值：

```text
press_depth = 0.002 m
press_axis = 先试 world -Z；再切到 contact local axis
```

twist 初值：

```text
twist_angle = 14 deg
twist_center = contact point
twist_axis = 从 6 个候选里选
```

候选：

```text
RotX(+14), RotX(-14)
RotY(+14), RotY(-14)
RotZ(+14), RotZ(-14)
```

APEX-MR 原始逻辑：

```text
pick_down / drop_down:
  先沿 tool/contact 方向压到接触
  再执行 twist

pick_twist:
  原系统绕 tool local Y 轴，角度约 +14 deg

drop_twist:
  原系统绕 tool local Y 轴，角度约 -14 deg

press_down:
  从 press_up / placed pose 再做一次压紧
```

RM75 迁移规则：

```text
保留 +14 / -14 deg 的角度初值
保留 pick 和 drop 方向相反的语义
重新标定 twist_axis
重新标定 twist_center
重新标定 press_axis 和 press_depth
```

通过标准：

```text
press 后 brick 仍在 target pose 附近；twist 不导致 tool 明显穿过 brick；
contact point 运动符合“撬/扭/释放”的直觉。
```

失败优先查：

```text
twist 是否绕 TCP 而不是 contact
twist_axis 是否和新 tool frame 不匹配
press_axis 是否方向反了
press_depth 是否过大
```

## Step 9：接入 mplib

目标：

```text
把动作函数输出的 `world_T_tcp` waypoint 交给 planner，而不是手写 joint qpos。
```

先规划这些点：

```text
pre_pick
lift
pre_place
retreat
```

再规划接触点：

```text
pick_contact
place_contact
press
twist
```

通过标准：

```text
planner 能把 `make_pick_drop_task(...)` 输出的每个 TCP waypoint 稳定生成非碰撞轨迹；
失败时能明确是 IK 不可达、collision 过紧还是 frame 错误。
```

失败优先查：

```text
planning end-effector 是否选了 lego_tool_tcp
self-collision 是否过严
tool collision mesh 是否过复杂
target pose 是否距离 singularity 太近
joint limit 是否和 URDF 一致
```

## 最终验收目标

最终验收不是“固定脚本只能搬一块固定 brick”，而是：

```text
用户可以选择 source plate 上任意一块可达 LEGO brick；
系统根据该 brick 的 pose / brick_id / press_side / press_offset 生成 APEX-MR 风格动作；
RM75 LEGO tool 把它撬/扭/取下；
motion planner 解出每个 TCP waypoint 的轨迹；
brick 被搬到 target plate 上用户指定的任意可达位置；
drop_twist + press_down 后放实；
release 后 brick 保持在目标 pose 附近。
```

第一版量化标准：

```text
支持 brick: 至少 2x4
支持场景: source plate -> target plate
支持目标: target plate 上任意手写可达 pose
动作来源: waypoint sequence 参考 APEX-MR pick/drop/press/twist 语义
抓取/卡合: attach/release 可以 fake
规划: 每个 world_T_tcp waypoint 由 motion planning/IK 求解
放置误差: xy <= 2 mm, z <= 2 mm, yaw <= 5 deg
稳定性: release 后 2 秒内 brick 不明显漂移或穿模
重复性: 同一块 brick 搬运到 3 个不同 target pose 均成功
```

后续升级标准：

```text
支持更多 brick_id
target pose 从手写坐标改为 LEGO grid 坐标
press_side / press_offset 自动从目标装配任务生成
fake attach/release 替换为更真实的约束或接触模型
接入 BrickSim/Isaac Sim 验证真实 LEGO interlocking
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

迁移时可以保留：

```text
动作结构：pre_pick -> contact -> twist -> lift -> place -> press -> release -> retreat
LEGO 尺寸：8 mm pitch, 9.6 mm brick height
twist_angle 初值：14 deg
press_depth 初值：2-5 mm
```

必须重标定：

```text
tcp_T_contact
press_axis
twist_axis
twist_center
tool mounting transform
机器人 base pose
```

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
