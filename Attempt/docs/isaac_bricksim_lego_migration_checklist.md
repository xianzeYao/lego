# Isaac Sim / BrickSim LEGO Manipulation 检查清单

这份清单用于把 APEX-MR 的 LEGO manipulation 思路迁移或复现到 Isaac Sim / BrickSim 中。当前目标是单臂、RM75、改装 LEGO tool，而不是一开始就复现完整多机器人系统。

## 0. 仓库和依赖状态

- [x] 已接入 `APEX-MR` submodule。
- [x] 已接入 `Robot_Digital_Twin` submodule，版本固定在 `apexmr-release` 对应 commit。
- [x] 已接入 `BrickSim` submodule，版本固定在 `cbd5de3238e6ac12f44ef699e1507a9f16bdafc3`。
- [x] 已确认 APEX-MR 依赖外部 `Robot_Digital_Twin` 提供 GP4 URDF/xacro 和 MoveIt config。
- [x] 已确认 APEX-MR 的 tool-frame variants 主要以 DH 文件形式存在，不只是 URDF link。
- [x] 已确认 `Robot_Digital_Twin` 包含 EOAT mesh、LEGO mesh、GP4 xacro、Gazebo launch 和 MoveIt SRDF。
- [x] 已确认 `BrickSim` 包含 Isaac Sim demo、Python API、native extension 和 brick simulation resources。

## 1. 机器人模型

- [ ] 明确 Isaac Sim 中第一版使用的机械臂就是 RM75。
- [ ] 确认 RM75 URDF 导入后没有 mesh 路径缺失。
- [ ] 确认所有 joint axis 与真实机械臂一致。
- [ ] 确认 joint limit 与真实控制器一致。
- [ ] 确认 base frame 和 world frame 约定。
- [ ] 确认 visual mesh 尺寸正确。
- [ ] 确认 collision mesh 尺寸正确。
- [ ] 尽量使用简化 collision mesh，避免复杂 STL 直接做碰撞。
- [ ] 用已知标定姿态检查 forward kinematics。
- [ ] 确认导入后的 articulation 可以被 Isaac Sim controller 命令。

## 2. LEGO Tool / EOAT 模型

APEX-MR 的 digital twin 中有真实 URDF tool link：

- `link_tool` / `${arm_id}_link_tool`
- 通过 `fts_tool` / `${arm_id}_fts_tool` 挂载
- mesh：`gazebo/meshes/eoat/tool.stl`

在 Isaac Sim 中使用前需要检查：

- [ ] 确认我们的自定义 STL 是不是和原始 `tool.stl` 一致，还是更新后的版本。
- [ ] 确认 STL 单位：米还是毫米。
- [ ] 确认 tool 原点是否符合 RM75 flange 坐标系。
- [ ] 确认 URDF/USD 导入后 tool mesh 朝向正确。
- [ ] 确认 collision mesh 不会过度包住 LEGO 接触区域。
- [ ] 为以下 frame 加可视化 marker：
  - [ ] flange frame
  - [ ] F/T sensor frame
  - [ ] tool body frame
  - [ ] assemble TCP
  - [ ] disassemble TCP
  - [ ] alt/place-up TCP
  - [ ] press TCP

## 3. APEX-MR 中需要保留的 Tool-Frame 变体

APEX-MR 不是把 tool 当作单个 TCP 使用，而是定义了多个任务相关 frame：

- `gp4_tool_DH.txt`：nominal tool frame，默认/基准 tool frame。
- `gp4_tool_assemble_DH.txt`：assemble frame，用于放置、压合、装配接触。
- `gp4_tool_disassemble_DH.txt`：disassemble frame，用于抓取、拆卸、脱离接触。
- `gp4_tool_alt_DH.txt`：alternate frame，用于侧向或 place-up 操作。
- `gp4_tool_alt_assemble_DH.txt`：alternate assembly frame，用于另一种装配姿态。
- `gp4_tool_handover_assemble_DH.txt`：handover assembly frame，主要给双臂交接场景用。

在 Isaac Sim 中需要做：

- [ ] 把每个 DH 变体转换成相对 imported tool frame 的显式 transform。
- [ ] 为每个 transform 创建 debug axis 或小 marker。
- [ ] 检查 `assemble` 和 `disassemble` TCP 是否有预期 offset。
- [ ] 检查 `alt` frame 是否对应侧向/place-up 动作。
- [ ] 检查每个 TCP 下 press 方向是否正确。
- [ ] 在相同 joint angles 下，对比 APEX-MR TCP pose 和 Isaac Sim TCP pose。

## 4. LEGO 资产

`Robot_Digital_Twin` 中包含 LEGO STL：

- `b1x1`、`b1x2`、`b1x4`、`b1x6`、`b1x8`
- `b2x2`、`b2x4`、`b2x6`、`b2x8`
- `base32x32`、`base48x48`

需要检查：

- [ ] LEGO mesh 导入后单位正确。
- [ ] stud pitch 为 8 mm。
- [ ] brick 高度为 9.6 mm。
- [ ] baseplate 坐标原点明确。
- [ ] 明确 brick top-left / center 的转换规则。
- [ ] 明确 orientation 约定：`ori=0/1`、角度，还是四元数。
- [ ] 第一版决定使用简单 rigid STL 还是 BrickSim interlocking brick。
- [ ] 如果使用 BrickSim interlocking：
  - [ ] 定义 stud / cavity / topology metadata。
  - [ ] 确认 snap-fit 能生成预期约束。
  - [ ] 确认 detach / disassembly 阈值。

## 5. 单块积木操作 Primitive

最小动作序列：

1. move home
2. approach brick
3. descend to pick
4. attach/grasp
5. lift
6. move above target
7. descend to place
8. press
9. twist if needed
10. release
11. retreat

需要检查：

- [ ] approach pose 无碰撞。
- [ ] pick TCP 对准 LEGO 抓取/接触特征。
- [ ] attach transform 能让 LEGO 相对 tool 固定。
- [ ] lift 不撞 stud、底板或邻近 brick。
- [ ] place pose 对准目标 stud。
- [ ] press 距离小且可控。
- [ ] release 不产生明显冲击。
- [ ] retreat 方向能避开 LEGO。

## 6. APEX-MR 中值得复现的动作思想

APEX-MR 中对我们有用的 manipulation ideas：

- [ ] `pick_down`：下降到接触，然后用 disassembly TCP 做抓取/脱离动作。
- [ ] `pick_twist`：绕 tool-local axis 旋转，帮助松开或卡住积木。
- [ ] `drop_down`：下降到放置接触，然后用 assembly TCP。
- [ ] `drop_twist`：和 pick 相反方向的 twist。
- [ ] `place_up`：侧向或向上插入模式。
- [ ] `press_down`：使用力/接触反馈向下压合。
- [ ] `support`：用另一个接触支撑结构；单臂阶段可先变成被动 fixture/support。
- [ ] `handover`：第一阶段单臂不需要。

单臂 Isaac Sim 第一版优先实现：

- [ ] `pick_down`
- [ ] `pick_twist`
- [ ] `drop_down`
- [ ] `drop_twist`
- [ ] `press_down`

推迟：

- [ ] 双臂 support。
- [ ] handover。
- [ ] 异步 TPG/ADG。

## 7. 力 / 接触反馈

APEX-MR 使用 F/T feedback threshold：

- pick/drop 时使用 z-force threshold。
- place-up 时使用 x-force threshold。
- 接触丰富动作使用低速度。
- 达到力阈值后停止当前运动。

在 Isaac Sim / BrickSim 中需要决定：

- [ ] 使用 simulated force sensor、contact sensor，还是 BrickSim connection event。
- [ ] 在 tool/LEGO 接触位置添加 sensor 或 contact monitor。
- [ ] 接触动作前记录 baseline force。
- [ ] 下降动作达到 force/contact threshold 时停止。
- [ ] 接触动作使用低速。
- [ ] 记录 force/contact trace 用于调试。
- [ ] 确认 press 不会穿透 LEGO。

## 8. 运动生成

第一版从简单方案开始：

- [ ] 手写 joint waypoints。
- [ ] 手写 Cartesian waypoints。
- [ ] 第一块积木测试不做全局规划。

然后再增强：

- [ ] 为目标 TCP pose 增加 IK solver。
- [ ] 增加 collision checking。
- [ ] 在 frame 都正确后再加 RMPflow/Lula。
- [ ] 只有本地 waypoint 不够用时，再考虑 MoveIt2 或外部 planner。

## 9. BrickSim 专项验证

- [ ] 原样运行 BrickSim 官方 `demo_assembly.py`。
- [ ] 确认 Isaac Sim 版本和 Python 版本符合 BrickSim 要求。
- [ ] 确认 GPU 能在低分辨率下运行场景。
- [ ] 确认 BrickSim 能加载现有 brick asset 或自定义 brick。
- [ ] press 后能检测到 connection。
- [ ] 小型堆叠例子中 breakage/collapse detection 正常。
- [ ] reset/replay 行为稳定。

## 10. 最小里程碑

### M1：环境

- [ ] Isaac Sim 能启动。
- [ ] BrickSim 官方 demo 能跑。
- [ ] 空场景能加载 RM75。

### M2：机器人 + Tool

- [ ] RM75 能在 Isaac Sim 中运动。
- [ ] tool 正确挂到 flange。
- [ ] TCP marker 的位置和方向可视化正确。

### M3：一块积木

- [ ] 一个 LEGO brick 能在已知 pose 生成。
- [ ] 机械臂能用 attach 或 constraint 拿起它。
- [ ] 机械臂能把它放到目标 pose。
- [ ] press 和 release 不导致明显不稳定。

### M4：两块积木

- [ ] 第一块能稳定放置。
- [ ] 第二块能在其上方对齐。
- [ ] BrickSim 或 contact logic 能报告 connection。

### M5：Instruction JSON

- [ ] 定义一个小 instruction JSON。
- [ ] 顺序执行每一步。
- [ ] 保存最终 scene state。
- [ ] 对比最终 brick pose 和目标 pose。

## 11. 扩展前停止条件

不要在以下条件满足前扩展到很多积木：

- [ ] Tool TCP 已经用真实或 APEX-MR 已知姿态验证。
- [ ] 接触动作能可靠停止。
- [ ] 单块积木放置重复性可接受。
- [ ] 两块堆叠稳定。
- [ ] reset 是确定性的。
- [ ] 日志包含 target pose、actual pose、contact status 和 final error。
