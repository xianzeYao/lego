
# 阶段 3.5：Tool Frame 可视化与标定

日期：2026-06-14

对应主路线：

```text
docs/maniskill_rm75_lego_validation.md
```

## 目标

在进入 press 和 twist 前，先确认 RM75 LEGO tool 的任务 frame：

- `lego_tool_tcp` 在哪里。
- 凹槽中心 / contact origin 应该在 TCP 的哪个 offset。
- 有柱侧和无柱侧分别是哪一边。
- press 方向是不是沿正确的工具局部轴。
- pick/place twist 的轴和符号是否符合实体工具语义。

本阶段不验证 IK、真实接触、真实撬起或放置，只提供人工标定 viewer。

## 新增代码

```text
maniskill_rm75_lego/scripts/run_stage3_5_tool_frame_calibration.py
```

## 颜色约定

```text
blue sphere         = lego_tool_tcp_marker，来自环境，唯一 TCP marker / 工具三轴交点
red sphere          = lego_tool_contact_marker，来自环境，唯一 contact marker
yellow sphere       = stud/pillar side，有柱侧
purple sphere       = empty side，无柱侧
orange sphere       = optional press end，仅使用 --show-press-end 时显示
orange long rod     = enlarged press direction
red/green/blue rods = contact frame X/Y/Z axes
orange short rod    = pick twist ghost：旋转后有柱侧朝向
cyan short rod      = place twist ghost：旋转后有柱侧朝向
white LEGO         = Robot_Digital_Twin lego_1x2.urdf
green LEGO         = target pose marker
```

## 默认参数

```text
contact_offset_tcp = [0.0, 0.0, -0.015]  # 暂定工具工作点：TCP 局部 -Z 方向 15 mm
side_axis/sign/distance = x, +1, 0.018
press_axis/sign/depth = z, +1, 0.005
press_visual_length = 0.06
twist_axis = y
pick_twist_deg = -14
place_twist_deg = +14
twist_visual_length = 0.04
marker_radius = 0.0015
show_press_end = false
```

APEX-MR 参考：

```text
twist_rad = 0.244346 rad ~= 14 deg
pick/place 初值用 14 deg 量级
```

其中 `contact_offset_tcp` 暂时定为阶段 3.5 结论；后续 pick pose 目标点由 LEGO 几何和
APEX-MR 风格的 `press_side/press_offset` 计算，不再在本阶段继续横向扫 contact offset。

## APEX-MR 参考语义

已检查 `/home/yxz/lego/third_party/APEX-MR`：

```text
src/exe/lego_assignment.cpp
src/lego/Lego.cpp
config/lego_tasks/robot_properties/*tool*DH.txt
```

结论：

- APEX-MR 不是把 TCP、contact、press end 都当作接触点。
- 它先通过 `press_side + press_offset` 选 brick 上的 press/grab 格点。
- `calc_brick_grab_pose(...)` / `assemble_pose_from_top(...)` 生成一个工具工作 pose；这个 pose 可理解为接触/抓取/按压动作的参考原点。
- 后续 `pick_offset` 在该 pose 的局部坐标系下叠加 approach、up、down 偏移。
- twist 是在当前工具工作 pose 上右乘 `RotY(+/-14deg)`，不是绕另一个独立球旋转。
- APEX-MR 的不同 `*tool*DH.txt` 已经把不同工具工作点编码进工具 DH 末端，例如 assemble/disassemble/alt tool 的末端偏移不同。

所以 RM75 这边采用的语义应改成：

```text
blue sphere = lego_tool_tcp 的几何/URDF frame 原点，接近法兰盘中心轴
red sphere  = 工具工作 pose / contact origin，应该移动到实际和 LEGO 作用的位置
orange rod  = 从 red sphere 出发的 press/down 方向；方向可对，即使 red 不在法兰中心轴上
yellow/purple = 有柱侧/无柱侧方向
orange/cyan short rods = 在 red sphere 处做 twist 后，有柱侧方向会转到哪里
```

默认不显示 orange press-end sphere，避免误以为存在第二个 contact 点。需要看按压深度时才加 `--show-press-end`。

实体工具观察与阶段结论：

```text
取 LEGO 时，目标点应由选中的两个 stud 和邻边几何关系确定。
RM75 TCP 到工具工作点暂时只保留轴向偏移：
T_tcp_contact = Trans(0, 0, -0.015)
```

## 运行命令

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage3_5_tool_frame_calibration.py \
  --render --render-sleep 0.03 --wait-at-end
```

保留的调参示例：

```bash
# 阶段 3.5 暂定结论；不传参时也是这个默认值
--contact-offset 0 0 -0.015

# 有柱侧方向反过来
--side-axis x --side-sign -1

# 如果有柱侧更像工具局部 y 方向
--side-axis y --side-sign 1

# press 方向反过来
--press-axis z --press-sign -1

# 红点仍然太大时继续缩小
--marker-radius 0.001

# 如需查看 press_depth 的终点，再显示橙色 press-end 球
--show-press-end

# twist 轴改成 x 或 z
--twist-axis x
--twist-axis z
```

## 人工判断清单

本阶段已经完成的人工判断：

- contact offset 暂定为 `--contact-offset 0 0 -0.015`。
- 黄色 marker 是否指向有柱侧。
- 紫色 marker 是否指向无柱侧。
- 橙色 press rod 是否沿工具实际按下方向。
- 如使用 `--show-press-end`，橙色 press end 是否只是沿 press 方向的深度预览，不应被当作第二个 contact。
- 橙色 pick twist ghost：pick 旋转完成后，有柱侧是否朝向正确。
- 青色 place twist ghost：place 旋转完成后，有柱侧是否朝向正确。

后续不在 3.5 里继续凭视觉挪 contact origin。真正的 pick/contact 目标点应在下一阶段由
LEGO grid pose、brick type、`press_side`、`press_offset` 和工具轴向偏移共同计算。

如需重新打开 viewer 复查，可以用自然语言反馈：

```text
红点再往工具里面 5 mm
黄色有柱侧反了
press 方向对
pick twist 方向反了
place twist 看起来对
```

## Headless 检查结果

运行命令：

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage3_5_tool_frame_calibration.py --steps 1
```

通过。

关键输出：

```text
contact_offset_tcp: [0.0, 0.0, -0.015]
side_axis/sign/distance: x 1.0 0.018
press_axis/sign/depth/visual_length: z 1.0 0.005 0.06
twist_axis pick/place deg visual_length: y -14.0 14.0 0.04
tcp p: [0.0, -0.21, 0.2695]
contact p: [0.0, -0.21, 0.2845]
stud_side p: [-0.018, -0.21, 0.2845]
empty_side p: [0.018, -0.21, 0.2845]
brick p: [0.32, 0.0, 0.0096]
target p: [0.32, 0.08, 0.0096]
```

注意：在当前 home 姿态下，TCP 局部 `-Z` 对应 world `+Z`，所以默认
`--contact-offset 0 0 -0.015` 会让 contact marker 在 world 中比 TCP 更高。

已观察到的候选点：

```text
SAPIEN selected entity: scene-0_lego_tool_contact_marker
pose.p ~= [0.000, -0.210, 0.285]
radius was 0.009 during visual check; then reduced to 0.002 to avoid occlusion.
```

该位置作为阶段 3.5 暂定 contact offset。后续目标点不再靠 red sphere 横向移动得到，
而是由 LEGO studs 和邻边几何计算得到。

TCP marker：

```text
SAPIEN selected entity: scene-0_lego_tool_tcp_marker
pose.p ~= [0.000, -0.210, 0.270]
radius was 0.012 during visual check; then reduced to 0.0025 to avoid occlusion.
```

该位置表示 `lego_tool_tcp` 的原点，即工具局部三轴的交点，不等同于实际 press/contact 点。

为避免两套 marker 重叠，标定脚本不再额外创建 `calib_tcp_blue` /
`calib_contact_red`；TCP/contact 只保留环境自带的蓝/红 marker。

## 阶段状态

阶段 3.5 完成。

当前结论：

```text
T_tcp_contact = Trans(0, 0, -0.015)
```

下一阶段应处理 pick 目标点计算：根据 LEGO `grid [x,y,z,ori]`、brick type、
`press_side/press_offset` 计算两个 studs 与邻边对应的几何目标点，然后令
`T_world_contact` 对齐该目标点。
