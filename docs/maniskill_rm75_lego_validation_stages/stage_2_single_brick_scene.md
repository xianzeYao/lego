# 阶段 2：baseplate 网格 LEGO 场景

日期：2026-06-14

对应主路线：

```text
docs/maniskill_rm75_lego_validation.md
```

## 目标

把阶段 2 从“单块 1x2 LEGO 尺寸检查”升级为“Robot_Digital_Twin baseplate + APEX-MR 风格网格坐标”检查。

本阶段验证：

- `base32x32.stl` 能放入 ManiSkill 场景。
- `1x2`、`1x4`、`2x4` LEGO 能按 plate 网格位置摆在 baseplate 上。
- 坐标计算使用和 APEX-MR 一致的 `8 mm` stud pitch。
- plate top/grid reference、baseplate mesh origin、brick mesh origin 三者不会混在一起。
- 后续 pick/place pose 可以复用同一套 LEGO grid helper。

本阶段仍不验证真实 snap/contact。当前 LEGO 和 baseplate 都是 kinematic visual actor。

## 新增/修改代码

```text
maniskill_rm75_lego/lego_grid.py
maniskill_rm75_lego/envs/rm75_lego_pick_place.py
maniskill_rm75_lego/scripts/run_stage2_baseplate_scene.py
```

## 坐标约定

APEX-MR 的核心参数：

```text
P_len_ = 0.008 m
brick_height_m_ = 0.0096 m
```

Python 版抽在：

```text
maniskill_rm75_lego/lego_grid.py
```

核心函数：

```text
apex_brick_bottom_pose(...)
apex_brick_actor_pose(...)
press_point_grid(...)
```

`apex_brick_bottom_pose` 是 APEX-MR `calc_brick_loc` 的 Python 版。它把：

```text
plate top pose
plate size
brick type
grid x/y/z
orientation
```

转换成 brick bottom frame。

注意：Robot_Digital_Twin 的 brick STL mesh origin 不在 brick bottom，而是在 bottom 上方 `9.6 mm`：

```text
b1x2/b1x4/b2x4 mesh z bounds: [-9.6 mm, +1.6 mm]
```

所以 actor pose z = brick bottom z + `0.0096`。

baseplate STL:

```text
base32x32.stl bounds: [-128, -128, -1.6] 到 [128, 128, 1.6] mm
size: 256 mm x 256 mm x 3.2 mm
```

当前 Stage 2 约定：

```text
plate top/grid pos:    [0.32, 0.00, 0.0032]
baseplate mesh origin: [0.32, 0.00, 0.0016]
plate size:            32 x 32 studs
```

也就是 baseplate bottom 在 `z=0`，top/grid reference 在 `z=3.2 mm`。

`grid [x, y, z, ori]` 定义：

```text
x: plate 上的 stud-grid x 编号，单位是 8 mm
y: plate 上的 stud-grid y 编号，单位是 8 mm
z: LEGO 层高编号，单位是 9.6 mm
ori: 0 表示 brick 长边沿 plate +x，1 表示绕 +z 旋转 90 度、长边沿 plate +y
```

这里的 `x/y` 不是 actor 中心，而是 APEX-MR 的放置格点。brick 的中心会再加：

```text
ori=0: [studs_x * 8mm / 2, studs_y * 8mm / 2, 0]
ori=1: 先绕 +z 旋转 90 度，再按 brick 中心偏移计算
```

当前 plate grid 点示例：

```text
grid [0, 0, 0]   -> world [0.192, -0.128, 0.0032]
grid [1, 0, 0]   -> world [0.200, -0.128, 0.0032]
grid [0, 1, 0]   -> world [0.192, -0.120, 0.0032]
grid [31, 31, 0] -> world [0.440,  0.120, 0.0032]
grid [0, 0, 1]   -> world [0.192, -0.128, 0.0128]
```

## 场景内容

使用 Robot_Digital_Twin mesh：

```text
third_party/Robot_Digital_Twin/gazebo/meshes/lego/base32x32.stl
third_party/Robot_Digital_Twin/gazebo/meshes/lego/b1x2.stl
third_party/Robot_Digital_Twin/gazebo/meshes/lego/b1x4.stl
third_party/Robot_Digital_Twin/gazebo/meshes/lego/b2x4.stl
```

同时保留 URDF path 打印，方便确认来源：

```text
generated_urdf/robot_digital_twin/lego_baseplate32.urdf
generated_urdf/robot_digital_twin/lego_1x2.urdf
generated_urdf/robot_digital_twin/lego_1x4.urdf
generated_urdf/robot_digital_twin/lego_2x4.urdf
```

当前放置所有非 plate LEGO brick 类型：

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

颜色约定：

```text
black: baseplate32
white: 1x2 brick
green: 1x4 brick
red:   2x4 brick
transparent green: 1x2 target marker
```

## 运行命令

Headless 检查：

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage2_baseplate_scene.py --steps 20
```

视觉检查：

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage2_baseplate_scene.py \
  --steps 100000 --render --render-sleep 0.03 --wait-at-end
```

## 当前结果

Headless 通过。

关键输出：

```text
plate size studs: [32, 32]
plate mesh origin pos: [0.32, 0.0, 0.0016]
plate top/grid pos: [0.32, 0.0, 0.0032]

lego_1x1 grid [2, 2, 0, 0]
bottom [0.212, -0.108, 0.0032]
actor  [0.212, -0.108, 0.0128]

lego_1x2 grid [5, 3, 0, 1]
bottom [0.236, -0.096, 0.0032]
actor  [0.236, -0.096, 0.0128]

lego_1x4 grid [9, 2, 0, 0]
bottom [0.280, -0.108, 0.0032]
actor  [0.280, -0.108, 0.0128]

lego_1x6 grid [15, 3, 0, 1]
bottom [0.316, -0.080, 0.0032]
actor  [0.316, -0.080, 0.0128]

lego_1x8 grid [20, 2, 0, 0]
bottom [0.384, -0.108, 0.0032]
actor  [0.384, -0.108, 0.0128]

lego_2x2 grid [3, 12, 0, 0]
bottom [0.224, -0.024, 0.0032]
actor  [0.224, -0.024, 0.0128]

lego_2x4 grid [8, 12, 0, 1]
bottom [0.264, -0.016, 0.0032]
actor  [0.264, -0.016, 0.0128]

lego_2x6 grid [14, 13, 0, 0]
bottom [0.328, -0.016, 0.0032]
actor  [0.328, -0.016, 0.0128]

lego_2x8 grid [22, 13, 0, 1]
bottom [0.376, 0.008, 0.0032]
actor  [0.376, 0.008, 0.0128]

PASS: baseplate32 grid scene with all non-plate LEGO brick types initializes
```

## 判断

阶段 2 当前通过。我们现在有了：

- 一个固定的 `32 x 32` plate frame。
- APEX-MR 风格的 grid-to-world pose 计算。
- 可复用的 press point 计算。
- 三类 LEGO brick 在同一 plate 上的可视化检查。

后续阶段应该基于 `lego_grid.py` 继续做：

- 指定任意 LEGO 放置格点。
- 从格点算 target brick pose。
- 从 `press_side/press_offset` 算局部接触/按压点。
- 再叠 RM75 tool 的 `T_tcp_contact` 去生成机械臂目标姿态。
