# 阶段 4：2x4 Pick + Twist Motion

日期：2026-06-15

对应主路线：

```text
docs/maniskill_rm75_lego_validation.md
```

## 目标

开始解决真实 pick 动作的第一步，也就是只确认 pick + twist 的几何目标和
IK motion 是否正确：

```text
到 LEGO 上方 -> 下降 -> 翘起旋转 -> 抬起
```

本阶段先不验证碰撞、真实接触、真实吸附/卡住，也不做完整规划。目标是：

- 根据 LEGO `brick type + grid [x,y,z,ori] + press_side + press_offset` 算 pick 几何目标点。
- 可视化两个被选中的 stud、stud pair center、邻边 pick target。
- 把 `T_tcp_contact = Trans(0,0,-0.015)` 用到 TCP 目标计算里。
- 用 Pinocchio IK 解 RM75 的 `pre_pick -> pick_down -> pick_twist -> pick_twist_up`。

当前 pick 动作语义：

```text
home
pre_pick        # contact 点在 pick target 正上方
pick_down       # 沿 press direction 下压到目标附近
pick_twist      # 绕 contact frame 局部 Y 轴 twist，当前 RM75 默认 -14 deg
pick_twist_up   # 保持 twist 后姿态，沿 world +Z 抬起
```

本阶段通过只说明 motion 合理，不说明 LEGO 已经能被真实动力学撬起。

## 新增代码

```text
maniskill_rm75_lego/lego_grid.py
maniskill_rm75_lego/scripts/run_stage4_pick_2x4.py
```

`lego_grid.py` 新增：

```text
brick_stud_centers_world(...)
pick_target_from_press_side(...)
```

## 当前默认任务

取当前 Stage 2 场景里的 `LEGO_2X4`：

```text
brick: lego_2x4
grid: [8, 12, 0, 1]
press_side: 1
press_offset: 0
contact_offset_tcp: [0, 0, -0.015]
```

`press_side/press_offset` 语义来自 APEX-MR：

```text
press_side  决定从 LEGO 哪条邻边进入
press_offset 决定沿该边选哪一组相邻 stud
```

当前几何输出：

```text
selected stud centers:
  [-0.052, -0.304, 0.0144]
  [-0.060, -0.304, 0.0144]

stud pair center:
  [-0.056, -0.304, 0.0144]

pick contact target:
  [-0.056, -0.300, 0.0144]

outward normal:
  [0.0, 1.0, 0.0]

tangent:
  [-1.0, 0.0, 0.0]
```

解释：

- 两个蓝色 stud sphere 是当前被选中的两个凸起中心。
- 黄色 sphere 是两个 stud 的中心点。
- 红色 sphere 是从 stud pair center 向邻边作垂线得到的 pick contact target。
- contact frame 现在使用 RM75/APEX 对齐后的约定：`+X` 是工具有墙/工作侧方向，和邻边外侧方向一致；`+Z` 是 press direction，和当前 `lego_tool_tcp` 的 `+Z` 同向，也就是 world down。

当前 viewer 默认显示的是 contact 点轨迹，而不是 TCP 轨迹：

```text
pre_pick_contact  : 接触点在 pick target 正上方
pick_down_contact : 接触点下压到 pick target 附近
pick_twist_contact: 与 pick_down 同接触原点，姿态 twist；viewer 中会稍微偏移成 ghost，避免完全重合
pick_twist_up_contact: 保持 twist 后姿态，沿 world +Z 抬起 15mm
```

TCP frame 受 `T_tcp_contact` 和 IK fallback 姿态影响，容易干扰人工判断，所以默认隐藏。
如果需要同时看 TCP 目标帧，可以加：

```bash
--show-tcp-frames
```

## 姿态说明

第一版默认会先尝试：

```text
--tcp-orientation apex
```

也就是用 APEX-MR 风格的工具工作姿态。这个姿态下：

```text
tool wall side direction = +APEX contact frame X
```

它应该和 `outward normal` 同向。脚本会打印：

```text
wall/outward alignment dot: 1.0
```

脚本会同时打印轴向审计值：

```text
contact_z/home_tcp_z dot: 1.0
wall/outward alignment dot: 1.0
```

如果后续某次改 URDF 或 frame 后这两个值明显偏离 `1.0`，说明轴向定义又不一致了。

保留 fallback 机制：

```text
tcp_orientation: apex
executed_tcp_orientation: home
```

正常情况下现在应该是：

```text
tcp_orientation: apex
executed_tcp_orientation: apex
```

如果 IK 失败才会退回 home TCP 姿态跑通。
如果要强制检查严格 APEX 姿态，可以加：

```bash
--no-ik-fallback
```

## 运行命令

Headless：

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage4_pick_2x4.py \
  --steps-per-segment 20 --hold-steps 10
```

视觉检查：

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/yxz/data/conda/envs/maniskill4lego/bin/python \
  maniskill_rm75_lego/scripts/run_stage4_pick_2x4.py \
  --render --render-sleep 0.04 --steps-per-segment 120 --hold-steps 60 --wait-at-end
```

常用调参：

```bash
--press-side 1
--press-offset 0
--pre-height 0.06
--press-depth 0.005
--twist-up-height 0.015
--pick-twist-deg -14.000007
--tcp-orientation apex
--marker-scale 1.35
```

## 当前结果

Headless 通过。

关键输出：

```text
pre_pick ik success: True
pick_down ik success: True
pick_twist ik success: True
pick_twist_up ik success: True
wall/outward alignment dot: 1.0
pre_pick contact p:  [-0.056, -0.300, 0.0744]
pick_down contact p: [-0.056, -0.300, 0.0094]
pick_twist_up contact p: [-0.056, -0.300, 0.0244]
PASS: stage4 pick geometry and IK motion for lego_2x4
```

当前 IK waypoint：

```text
pre_pick tcp target p:      [-0.056, -0.300,  0.0594]
pick_down tcp target p:     [-0.056, -0.300, -0.0056]
pick_twist tcp target p:    [-0.056, -0.3036, -0.0052]
pick_twist_up tcp target p: [-0.056, -0.3036,  0.0098]
```

注意：当前输出里如果出现 `executed_tcp_orientation: home`，说明严格 APEX 姿态没被 IK 接受，
脚本自动切到可执行姿态。真正物理一致的姿态约束需要下一轮继续处理。

## 阶段结论

阶段 4 现在定义为 **Pick + Twist Motion**：

```text
brick/grid/press_side/press_offset -> pick contact target -> contact frame
-> TCP target frame -> IK waypoint -> viewer 中动作方向确认
```

已确认：

- selected studs、stud pair center、pick contact target 的几何关系合理。
- contact frame 的 `+X` 是工具有墙/工作侧方向，并和 outward normal 同向。
- contact frame 的 `+Z` 是 press direction，和当前 `lego_tool_tcp +Z` 同向。
- `pre_pick -> pick_down -> pick_twist -> pick_twist_up` 的动作语义已经对齐。

## 下一步

- 阶段 5：Pick Dynamic 验证，去掉 fake attach 作为成功条件，验证真实接触/翘起/跟随。
- 阶段 6：Place + Twist Motion，按目标 grid pose 做 place 的几何和 IK motion。
- 阶段 7：Place Dynamic 验证，验证真实下压、释放、抬起后 brick 留在目标位置。
