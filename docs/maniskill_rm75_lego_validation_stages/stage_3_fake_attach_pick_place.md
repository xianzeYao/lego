# 阶段 3：Fake Attach Pick And Place

日期：2026-06-14

对应主路线：

```text
docs/maniskill_rm75_lego_validation.md
```

## 目标

验证第一版 fake attach/release 机制：

- attach 时记录 `contact_T_brick`。
- attached 阶段每个 step 手动设置：

```text
world_T_brick = world_T_contact * contact_T_brick
```

- release 时把 brick 放到目标 pose。
- brick 在 attach 后不相对 contact frame 漂移。
- release 后 brick world pose 与 target pose 一致。

本阶段不验证真实抓取、不验证 LEGO 物理卡合、不验证 IK/mplib 可达性。

## 新增代码

```text
maniskill_rm75_lego/scripts/run_stage3_fake_attach_pick_place.py
```

复用阶段 2 场景：

```text
RM75LegoPickPlace-v1
```

## 动作流程

当前使用手写 joint-space waypoint：

```text
home = [90, 0, 0, -90, 0, -90, 60] deg
move pre_pick/contact
fake_attach
move lift
move transfer
move place/contact
fake_release at target pose
hold
retreat/home
```

contact frame 暂用：

```text
world_T_contact = world_T_lego_tool_tcp * Trans(0, 0, -0.015)
```

## 运行命令

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage3_fake_attach_pick_place.py \
  --steps-per-waypoint 20 --hold-steps 10
```

视觉检查建议用：

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage3_fake_attach_pick_place.py \
  --steps-per-waypoint 80 --hold-steps 30 \
  --render --render-sleep 0.03 --wait-at-end
```

## 结果

通过。

关键输出：

```text
initial brick p: [0.32, 0.0, 0.0096]
target brick p: [0.32, 0.08, 0.0096]
initial tcp p: [0.0, -0.21, 0.2695]
[attach] contact p: [-0.181767, -0.106162, 0.882894]
[attach] brick p: [0.32, -0.0, 0.0096]
[release] brick p: [0.32, 0.08, 0.0096]
final brick p: [0.32, 0.08, 0.0096]
final target position error: 0.0
max attached position error: 0.0
PASS: fake attach/release pick-place logic keeps brick attached and releases at target
```

## 判断

阶段 3 的 headless fake attach/release 逻辑验证通过。

这说明：

- `contact_T_brick` 记录和复用链路正确。
- attached 状态下 brick 能随 contact frame 更新。
- release 后可以把 Robot_Digital_Twin LEGO actor 放到目标 URDF pose。
- 后续可以在同一机制上替换更真实的 contact frame、IK 或 mplib waypoint。

## 注意事项

- 当前 waypoint 是手写 joint-space 目标，不保证 TCP 真的到达 LEGO 上方。
- attach 当前是逻辑绑定，不是物理抓取；attach 时如果 contact frame 和 brick 实际相距很远，也会记录一个很大的相对变换。
- 本阶段只证明对象状态机和 pose 更新方式正确；下一步需要验证 press 几何或先补可达性/IK。
