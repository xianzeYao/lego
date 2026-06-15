# 阶段 6：Fake-Attached Place Motion

日期：2026-06-15

对应主路线：

```text
docs/maniskill_rm75_lego_validation.md
```

## 目标

先默认 LEGO 已经“卡在”工具头上，用 fake attach 模拟稳定抓持，然后检查
home-held -> transfer -> place 动作趋势和 waypoint IK。

本阶段不验证真实卡合/释放，只验证：

- 默认从 home contact frame 开始 fake attach。
- attached 阶段 brick 相对 contact frame 保持固定。
- place target 由目标 `grid [x,y,z,ori]` 构造工具工作 frame。
- `place_offset -> drop_up -> place_down -> place_press -> place_twist -> release -> place_up`
  的动作趋势和 IK 是否合理。

## 新增代码

```text
maniskill_rm75_lego/scripts/run_stage6_fake_attached_place_1x6.py
```

## 当前默认任务

```text
brick: lego_1x6
initial grid: [15, 3, 0, 1]
target grid:  [23, 22, 0, 0]
press_side: 2
press_offset: 2
T_tcp_contact = Trans(0, 0, -0.015)
held_brick_offset_contact: [0, 0, 0.018]
place offset: APEX [-5mm, +5mm, -5mm]
place_twist_deg: +14 deg
```

## 几何语义

默认流程不再先从桌面 pick，而是在 home 位姿直接让 brick 跟随 contact frame：

```text
home
fake_attach
transfer
place_offset
drop_up
place_down
place_press
place_twist
release
place_up
```

目标位置由目标 grid pose 给出：

```text
world_T_brick_target
```

place contact 是独立工具工作 frame，不等同于 brick frame：

```text
+X: 目标 brick 长边方向
+Z: world down / press direction
origin: target brick actor origin 上方约 18 mm
```

然后反推 home 手里 brick 的相对位姿：

```text
contact_T_brick = inverse(world_T_contact_place) * world_T_brick_target
world_T_brick_home = world_T_contact_home * contact_T_brick
```

默认拿 `lego_1x6` 看趋势；如果要换成其它 stage2 里的 brick，例如 2x4：

```bash
--brick-key lego_2x4
```

因此 `place_down` 时 brick 正好对齐目标 grid；`place_twist` 用来观察工具释放动作趋势。
当前 release 会把 brick snap 到目标 pose，避免 fake-attached twist 后的姿态偏差污染
最终误差检查。

如果要回到 pick 后再 place 的趋势检查，可以加：

```bash
--include-pick
```

这个模式会在 `pick_twist` 处记录 fake attach，相当于假设 twist 后已经卡住；不能在
lift 后记录，否则会把抬起高度错误地记录成 brick 和 tool 之间的距离。

## 运行命令

Headless：

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage6_fake_attached_place_1x6.py \
  --steps-per-segment 20 --hold-steps 5
```

视觉检查：

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage6_fake_attached_place_1x6.py \
  --render --render-sleep 0.03 --steps-per-segment 80 --hold-steps 30 --wait-at-end
```

常用调参：

```bash
--target-grid 23 22 0 0
--place-twist-deg 14
--place-press-depth 0.003
--place-attack-dir 1
--held-brick-offset 0 0 0.018
--held-brick-yaw-deg 0
--transfer-up-height 0.08
```

## 当前结果

Headless 通过。

关键输出：

```text
mode: home_held_place
initial brick p: [0.000001, -0.21, 0.2665]
target brick p: [0.08, -0.248, 0.0128]
pre_place/place_offset contact p: [0.075, -0.253, 0.0408]
drop_up contact p: [0.08, -0.248, 0.0358]
place_down contact p: [0.08, -0.248, 0.0308]
place_twist contact p: [0.08, -0.248, 0.0278]
place_up contact p: [0.08, -0.248, 0.0628]
final target position error: 0.0
PASS: stage6 fake-attached place motion trend
```

所有 waypoint IK 成功。

## 下一步

- 打开 viewer 看 `home-held -> transfer -> place_offset -> drop_up -> place_down -> place_twist`
  的动作趋势是否像工具头卡住 LEGO 后在放置。
- 如果趋势对，再把 Stage 5 的真实抓持结果接进这个 place motion。
- 如果趋势不对，优先调 `place_twist_deg`、`place_press_depth` 和目标 grid，而不是先碰动力学。
