# Linux 复现步骤

这份文档只描述第一阶段要做的事：在一台 Linux/NVIDIA 电脑上，基于本仓库复现单臂 LEGO 拼装流程。目标不是一开始就复现完整 APEX-MR 多机器人系统，而是按下面这条路线一步一步跑通：

```text
搭 Linux / Isaac Sim / BrickSim 环境
        |
        v
复现 BrickSim 官方单臂/装配 demo
        |
        v
换成我们自己的 RM75 机械臂和改装 tool
        |
        v
拿一个给定 LEGO 装配说明书/简化 JSON
        |
        v
用 APEX-MR 思路生成单臂顺序执行的 action sequence
        |
        v
计算每一步的 RM75 joint 值或控制目标
        |
        v
送进 Isaac Sim / BrickSim 里的 RM75 执行
```

第一阶段不处理 text-to-LEGO，也不处理自动生成 LEGO 结构。可以先假设我们已经拿到一个按层搭建的 LEGO 说明书。

## 0. 推荐硬件和系统

推荐：

- Ubuntu 22.04 或 24.04。
- NVIDIA GPU 和正常驱动。
- 32 GB RAM 更稳；16 GB 可以先跑小场景，但环境会比较紧。
- 1 TB SSD 足够。

先检查 GPU：

```bash
nvidia-smi
```

如果 `nvidia-smi` 不正常，先不要装 BrickSim，也不要调 RM75。

## 1. 拉取仓库

推荐直接带 submodule：

```bash
git clone --recurse-submodules git@github.com:xianzeYao/lego.git
cd lego
```

如果已经 clone 过：

```bash
git submodule update --init --recursive
```

确认 third party 都在：

```bash
git submodule status
```

应该看到：

```text
third_party/APEX-MR
third_party/BrickSim
third_party/Robot_Digital_Twin
```

三个 third party 的具体作用见：

```text
docs/repository_overview.md
```

## 2. 安装 Isaac Sim 和 BrickSim 环境

先按 BrickSim 支持的版本安装 Isaac Sim。版本必须跟 BrickSim 要求对齐，不要随意升级。

进入 BrickSim：

```bash
cd third_party/BrickSim
```

安装/同步 BrickSim 环境：

```bash
./scripts/download_prebuilt_native.sh
uv sync --locked
```

如果这里失败，优先检查：

- Isaac Sim 版本。
- NVIDIA driver。
- Python / `uv` 环境。
- BrickSim native extension 是否下载成功。

## 3. 先跑 BrickSim 官方 Demo

官方 demo 是第一道 smoke test：

```bash
uv run bricksim demos/demo_assembly.py
```

验收：

- Isaac Sim 能启动。
- demo 场景能加载。
- brick 能出现。
- 仿真能 step。
- 没有 native extension load error。

如果官方 demo 跑不通，不要继续导入 RM75。先把 BrickSim 自己跑通。

## 4. 确认我们的 RM75 和 Tool 资产

本仓库主资产在：

```text
assets/rm75_gripper/
```

第一阶段建议使用：

```text
assets/rm75_gripper/RM75-B/urdf/RM75-B.urdf
assets/rm75_gripper/RM75-B/urdf/RM75-B_lego_tool.urdf
assets/rm75_gripper/RM75-B/urdf/RM75-B.planning.tiny.urdf
assets/rm75_gripper/RM75-B/urdf/RM75-B.permissive.srdf
assets/rm75_gripper/RM75-B/meshes/lego_test_open_fixed.stl
```

文件分工：

- `RM75-B.urdf`：原夹爪版主视觉/仿真模型，包含 RM75、夹爪、8mm spacer 和 `gripper_tcp`。
- `RM75-B_lego_tool.urdf`：LEGO 小件 tool overlay 版模型，保留 RM75、8mm spacer 和原夹爪扣具，再叠加 `lego_test_open_fixed.stl`，末端 frame 为 `lego_tool_tcp`。
- `RM75-B.planning.tiny.urdf`：规划用简化 collision 版本。
- `RM75-B.permissive.srdf`：规划器用的 group 和 collision disable 配置。
- `lego_test_open_fixed.stl`：我们的自定义 LEGO/tool 相关 STL，放在 RM75-B 的 `meshes/` 下，方便 URDF 使用相对路径引用。

不要优先使用：

- `wrong_RM75-B.urdf`：名字已经标明错误。
- `panda_stick.urdf`：Franka Panda 示例，不是 RM75。
- `robot_ag2f90c.urdf`：Dobot CR5 + AG2F90-C 的旧模型，不是当前 RM75 路线。
- `RM75-B_vhacd.urdf`：可以后续参考碰撞分解，但第一版先别当主模型。

## 5. 在 Isaac Sim 中导入 RM75

先只导入机器人，不要放 LEGO。

检查顺序：

- [ ] `RM75-B_lego_tool.urdf` 能导入。
- [ ] mesh 路径都能解析。
- [ ] robot scale 正确。
- [ ] `joint_1` 到 `joint_7` 都能动。
- [ ] joint axis 方向正确。
- [ ] joint limit 与真实 RM75 控制器一致。
- [ ] base frame / world frame 约定明确。
- [ ] `lego_tool_tcp` 能看到或能通过 debug marker 表示。

如果 robot 看起来能加载但运动不对，优先检查：

- URDF joint origin。
- joint axis。
- STL/DAE 单位。
- base link 朝向。
- Isaac Sim URDF importer 是否改写了 articulation 设置。

## 6. 挂载和校准改装 Tool

当前 LEGO tool 版 RM75 URDF 已经包含 `lego_tool_link` 和 `lego_tool_tcp`，但 LEGO 拼装通常不只需要一个 TCP。APEX-MR 的经验是同一个物理 tool 会有多个任务 frame：

- nominal tool frame。
- assemble TCP。
- disassemble TCP。
- alt/place-up TCP。
- press TCP。

第一版要做：

- [ ] 明确 flange frame。
- [ ] 明确 gripper/tool body frame。
- [ ] 可视化 `lego_tool_tcp`。
- [ ] 增加或记录 assemble TCP。
- [ ] 增加或记录 disassemble TCP。
- [ ] 增加或记录 press TCP。
- [ ] 确认 press 方向相对 LEGO stud 是正确的。

这些 frame 可以先用 Isaac Sim debug marker 表示，不一定一开始就写回 URDF。

## 7. 生成一块 LEGO 和目标位姿

先不要做完整说明书，只放一块 LEGO。

检查：

- [ ] LEGO mesh 单位正确。
- [ ] stud pitch 按 8 mm 理解。
- [ ] brick 高度按 9.6 mm 理解。
- [ ] brick 原点明确，是中心、角点，还是自定义位置。
- [ ] 目标 pose 明确。
- [ ] brick orientation 约定明确。

第一版可以使用简单 rigid body 或 fake object attach，不要求马上进入 BrickSim interlocking metadata。

## 8. 跑通单块 LEGO Fake Attach 流程

第一阶段最小动作：

```text
move home
approach brick
descend to pick
attach/grasp
lift
move above target
descend to place
press
release
retreat
```

验收：

- [ ] approach pose 无碰撞。
- [ ] pick TCP 对准 LEGO 抓取位置。
- [ ] attach 后 LEGO 相对 tool 固定。
- [ ] lift 不撞底板或邻近物。
- [ ] place pose 对准目标位置。
- [ ] press 距离小且可控。
- [ ] release 不产生明显冲击。
- [ ] retreat 方向能安全离开。

这一阶段的目标只是验证 RM75 运动和 frame，不代表 LEGO 物理已经正确。

## 9. 接入 APEX-MR 的动作思路

APEX-MR 在这里主要当动作设计参考，不要先搬完整多机器人系统。

重点参考：

```text
third_party/APEX-MR/src/lego_policy.cpp
third_party/APEX-MR/include/task.h
third_party/APEX-MR/src/lego/Lego.cpp
third_party/APEX-MR/config/lego_tasks/
third_party/APEX-MR/config/lego_tasks/robot_properties/
```

第一版单臂动作：

- `pick_down`
- `pick_twist`
- `drop_down`
- `drop_twist`
- `press_down`

先不做：

- 双臂 support。
- handover。
- ILP 多机器人任务分配。
- TPG/ADG 异步执行。

实现方式可以很简单：

```text
instruction step
  -> brick id + source pose + target pose
  -> action sequence
  -> TCP waypoints
  -> IK / joint targets
  -> Isaac Sim execution
```

## 10. 计算 RM75 Joint 值或控制目标

第一版不要急着上复杂 planner。

推荐顺序：

1. 手写少量 joint waypoint。
2. 手写 Cartesian waypoint。
3. 对目标 TCP pose 做 IK。
4. 增加简单 collision checking。
5. frame 都对之后再考虑 RMPflow/Lula。
6. 如果本地 waypoint 不够，再考虑 MoveIt2 或外部 planner。

规划模型可先使用：

```text
assets/rm75_gripper/RM75-B/urdf/RM75-B.planning.tiny.urdf
assets/rm75_gripper/RM75-B/urdf/RM75-B.permissive.srdf
```

注意：

- `RM75-B.planning.tiny.urdf` 是规划简化模型，不是最终视觉模型。
- 如果规划器老是报自碰撞，先看 SRDF collision disable 和 tool collision。
- 如果 IK 结果看起来怪，先怀疑 TCP frame，而不是 planner。

## 11. 把 Fake Attach 换成 BrickSim 物理

单块动作能稳定执行后，再开始替换物理交互。

要验证：

- [ ] tool 和 LEGO 接触能被检测到。
- [ ] press 后 BrickSim 能报告 connection。
- [ ] release 后 brick 不乱飞。
- [ ] detach/disassembly threshold 合理。
- [ ] reset/replay 稳定。

可能需要看的 BrickSim 代码：

```text
third_party/BrickSim/python/bricksim/mdp/connection_events.py
third_party/BrickSim/python/bricksim/mdp/connection_state.py
third_party/BrickSim/python/bricksim/mdp/brick_part.py
```

如果自定义 STL 没有 BrickSim 需要的 stud/hole/topology metadata，先不要硬接。可以先用已有 BrickSim brick asset 验证流程。

## 12. 输入一个简单 LEGO 说明书

等单块动作和 BrickSim 连接都能跑，再输入一个最小 instruction JSON。

第一版 JSON 可以只包含：

```text
brick_id
brick_type
source_pose
target_pose
orientation
layer
```

执行方式：

```text
for each instruction step:
    生成 action sequence
    生成 TCP waypoints
    求 IK / joint targets
    Isaac Sim 执行
    BrickSim 检查 contact/connection
    记录日志
```

不要一开始做 text-to-LEGO。那是前端任务生成问题，不是第一阶段仿真复现问题。

## 13. 两块积木验收

单块成功后，做两块上下堆叠。

验收：

- [ ] 第一块能稳定放置。
- [ ] 第二块能对齐第一块 stud。
- [ ] press 后 BrickSim 报告 connection。
- [ ] release 后结构稳定。
- [ ] retreat 不碰已经放好的 brick。
- [ ] reset 后重复执行结果接近。

两块成功前，不要扩展到很多块。

## 14. 日志和停止条件

每次执行至少记录：

- target pose。
- actual pose。
- joint target。
- joint actual。
- TCP pose。
- contact status。
- connection status。
- final pose error。

扩展到多块前，必须满足：

- [ ] RM75 joint axis 和 limit 已验证。
- [ ] tool TCP / assemble TCP / press TCP 已验证。
- [ ] 单块 fake attach 流程稳定。
- [ ] BrickSim 官方 demo 稳定。
- [ ] BrickSim 单块 connection 稳定。
- [ ] 两块堆叠稳定。
- [ ] reset/replay 基本确定。

## 15. 暂时不做的事

第一阶段明确不做：

- text-to-LEGO。
- 自动设计 LEGO 模型。
- 完整 APEX-MR 多机器人 ILP。
- TPG/ADG 异步执行。
- 双臂 handover。
- 从零写完整运动规划器。

这些都可以后面补，但不是证明 RM75 + 改装 tool 能在 BrickSim/Isaac Sim 里拼 LEGO 的前置条件。
