# APEX-MR LEGO Reference

日期：2026-06-15

本文件整理 `/home/yxz/lego/third_party/APEX-MR` 中对 RM75 LEGO ManiSkill 迁移有用的常量和动作语义。

对应 Python 参考模块：

```text
maniskill_rm75_lego/apex_mr_reference.py
```

## 来源文件

```text
third_party/APEX-MR/config/lego_tasks/lego_library.json
third_party/APEX-MR/src/lego/Lego.cpp
third_party/APEX-MR/src/exe/lego_assignment.cpp
third_party/APEX-MR/src/lego_policy.cpp
third_party/APEX-MR/config/lego_tasks/robot_properties/*tool*DH.txt
```

## 基础尺寸

APEX-MR 使用：

```text
P_len_ = 0.008
brick_height_m_ = 0.0096
lever_wall_height_ = 0.0032
knob_height_ = 0.0017
```

含义：

- LEGO stud pitch 是 `8 mm`。
- 一个 brick 层高是 `9.6 mm`。
- knob/stud 高度在 APEX 里近似 `1.7 mm`，Robot_Digital_Twin STL 顶部 stud 高度约 `1.6 mm`。

## Brick Library

APEX-MR `lego_library.json` 中 ID 到尺寸/重量：

```text
id 2:  2x4,  weight 0.00220 kg
id 3:  2x6,  weight 0.00328 kg
id 4:  1x8,  weight 0.00308 kg
id 5:  1x4,  weight 0.00150 kg
id 6:  1x6,  weight 0.00230 kg
id 7:  1x4,  weight 0.00160 kg
id 8:  1x4,  weight 0.00160 kg
id 9:  1x2,  weight 0.00080 kg
id 10: 1x1,  weight 0.00044 kg
id 11: 1x2,  weight 0.00075 kg
id 12: 2x2,  weight 0.00120 kg
```

在我们的 Python 命名里：

```text
studs_x = APEX height
studs_y = APEX width
```

## Plate/Grid Pose

APEX-MR `calc_brick_loc(...)` 逻辑：

```text
plate.pose
  * Trans(-plate.width * 8mm / 2, -plate.height * 8mm / 2, 0)
  * Trans(grid_x * 8mm, grid_y * 8mm, grid_z * 9.6mm)
  * brick_center_offset
```

`ori=0`：

```text
brick_center_offset = [studs_x * 8mm / 2, studs_y * 8mm / 2, 0]
```

`ori=1`：

```text
先 RotZ(+90deg)，再使用 [studs_x * 8mm / 2, -studs_y * 8mm / 2, 0]
```

因此 `grid [x,y,z,ori]` 是旋转后 LEGO footprint 的起始角/左下角，不是 actor 中心。

## Press Side / Press Offset

APEX-MR `get_press_pt(...)`：

对于 `ori=0`：

```text
side 1: press_pt = (x,                 y + offset),     press_ori = 0
side 2: press_pt = (x + offset,        y + width - 1),  press_ori = 1
side 3: press_pt = (x + offset,        y),              press_ori = 1
side 4: press_pt = (x + height - 1,    y + offset),     press_ori = 0
```

对于 `ori=1`，APEX 先 `swap(height, width)`：

```text
side 1: press_pt = (x + height - 1 - offset, y),             press_ori = 1
side 2: press_pt = (x,                       y + offset),    press_ori = 0
side 3: press_pt = (x + height - 1,          y + offset),    press_ori = 0
side 4: press_pt = (x + height - 1 - offset, y + width - 1), press_ori = 1
```

我们对应实现：

```text
maniskill_rm75_lego.apex_mr_reference.apex_press_point_grid
maniskill_rm75_lego.lego_grid.press_point_grid
```

## Grab Pose Local Offset

APEX-MR `calc_brick_grab_pose(...)` 在 brick pose 上叠 `grab_offset_mtx`。

对于 pick/take brick 时：

```text
side 1:
  p = [ height * 8mm / 2,
       -width  * 8mm / 2 + (offset + 1) * 8mm,
        0]
  yaw = 180deg

side 2:
  p = [ height * 8mm / 2 - (offset + 1) * 8mm,
        width  * 8mm / 2,
        0]
  yaw = -90deg

side 3:
  p = [ height * 8mm / 2 - (offset + 1) * 8mm,
       -width  * 8mm / 2,
        0]
  yaw = +90deg

side 4:
  p = [-height * 8mm / 2,
       -width  * 8mm / 2 + (offset + 1) * 8mm,
        0]
  yaw = 0deg
```

我们对应实现：

```text
apex_grab_offset_local(...)
```

注意：我们 Stage 4 当前的 pick target 使用“两个 selected studs + 邻边垂线交点”的几何解释，比 APEX 的 `grab_offset_mtx` 更贴近实体工具讨论，但两者共享 `press_side/press_offset` 语义。

## Action Offsets

APEX-MR 在 `lego_assignment.cpp` 中定义：

```text
pick_offset =
  [-0.005,  0.005, -0.005,    # place brick offset
   -0.005,  0.005, -0.0028]   # grab brick offset
```

也就是：

```text
place offset = [-5mm, +5mm, -5mm]
grab offset  = [-5mm, +5mm, -2.8mm]
```

Pick waypoint：

```text
pick_tilt_up = cart_T * [grab_x, grab_y, grab_z - abs(grab_z)]
pick_up      = cart_T * [0, 0, grab_z]
pick         = cart_T
pick_twist   = FK(pick, tool_disassemble) * RotY(+twist)
pick_twist_up: world z + 15mm using tool_assemble
```

Drop/place waypoint：

```text
drop_offset = cart_T * [place_x, place_y * attack_dir, place_z - abs(place_z)]
drop_up     = cart_T * [0, 0, place_z]
drop        = cart_T
drop_twist  = FK(drop, tool_assemble) * RotY(-twist)
drop_twist_up: world z + 15mm
```

Place tilt branch also contains:

```text
place_tilt_down_pre:
  [-(grab_z - abs(grab_z)), attack_dir * (-grab_y), grab_x - 0.02]

place_tilt_down:
  [-(grab_z - abs(grab_z)), attack_dir * (-grab_y), grab_x]

place_down:
  [-grab_z, 0, 0]

place_twist_down:
  [0.015, 0, -0.015]
```

## Twist

APEX-MR default:

```text
twist_rad = 0.244346 rad ~= 14 deg
handover_twist_rad = 0.314159 rad ~= 18 deg
```

Matrices:

```text
pick twist  = RotY(+twist_rad)
drop twist  = RotY(-twist_rad)
handover    = RotY(-handover_twist_rad)
```

## Tool DH Variants

APEX-MR uses multiple tool DH files to encode different effective work frames:

```text
tool:                  last row [0, -0.1830,  0.0000, pi]
tool_assemble:         last row [0, -0.1825,  0.0078, pi]
tool_disassemble:      last row [0, -0.1920,  0.0000, pi]
tool_alt:              last row [0, -0.1784, -0.0174, pi]
tool_alt_assemble:     last row [0, -0.1784, -0.0078, pi]
tool_handover_assemble:last row [0, -0.1815,  0.0078, pi]
```

对于 RM75，我们目前先不复制这些 DH，而是显式使用：

```text
T_tcp_contact = Trans(0, 0, -0.015)
```

后续如果要更接近 APEX-MR，可以把 assemble/disassemble/alt 这些工作点差异改成不同的 `T_tcp_contact_*`。

## 对当前 Stage 4 的意义

当前 Stage 4 先做：

```text
grid + brick type + press_side/press_offset
  -> selected studs
  -> stud pair center
  -> 邻边 pick target
  -> T_world_contact
  -> T_world_tcp
```

下一步可以把 APEX-MR 的这些 offset 用作候选参数：

```text
pre_height / approach offset
press_depth
twist angle
pick_up height
place/drop release path
```

但物理接触前，不应盲目复制 APEX 的 tool DH，因为我们的 RM75 tool 几何和 GP4 tool 不完全相同。
