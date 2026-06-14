# Linux 复现说明

本仓库把 APEX-MR、Robot_Digital_Twin 和 BrickSim 作为 submodule 接入，并指向 `xianzeYao` 名下的 fork。顶层 `lego` 仓库只记录这些外部项目的精确 commit；如果要改外部项目源码，应该先在对应 submodule 里提交并推送到 fork，再回到顶层仓库提交新的 submodule 指针。

## 外部 Submodule

- `APEX-MR/`
  - 上游：`https://github.com/intelligent-control-lab/APEX-MR`
  - Fork：`https://github.com/xianzeYao/APEX-MR.git`
  - 固定版本：`46a9448d9eaac5bd5973e0cd064623c5e7f5254e`
- `Robot_Digital_Twin/`
  - 上游：`https://github.com/intelligent-control-lab/Robot_Digital_Twin.git`
  - Fork：`https://github.com/xianzeYao/Robot_Digital_Twin.git`
  - 固定版本：`017120d2b3fb2941fbeeb581d94f41b56d00df1d`
- `BrickSim/`
  - 上游：`https://github.com/intelligent-control-lab/BrickSim.git`
  - Fork：`https://github.com/xianzeYao/BrickSim.git`
  - 固定版本：`cbd5de3238e6ac12f44ef699e1507a9f16bdafc3`

## 推荐机器

- Ubuntu 22.04 或 24.04。
- 如果要跑 Isaac Sim / BrickSim，需要 NVIDIA GPU 和可用驱动。
- 内存建议 32 GB；16 GB 可以先试小场景，但环境和仿真会更紧。
- 1 TB SSD 足够放本仓库、Isaac Sim、BrickSim 和生成资产。

## 先 Clone 仓库

推荐直接带 submodule clone：

```bash
git clone --recurse-submodules git@github.com:xianzeYao/lego.git
```

如果已经 clone 过但没拉 submodule：

```bash
cd lego
git submodule update --init --recursive
```

检查 submodule 是否到位：

```bash
git submodule status
```

正常应该看到三个路径：

```text
APEX-MR
Robot_Digital_Twin
BrickSim
```

## 路线 A：复现 APEX-MR / ROS Baseline

如果目标是先跑原始 APEX-MR 栈，再迁移到 Isaac Sim，用这条路线。

适合场景：

- 想验证原论文的 ROS/MoveIt 逻辑。
- 想看 APEX-MR 原始任务格式、动作状态机和规划流程。
- 暂时不改成 RM75，只先跑原始 GP4/数字孪生环境。

建议环境：

- Ubuntu 20.04 + ROS Noetic。
- 或使用 APEX-MR 提供的 Docker 流程。

基本步骤：

1. 安装 ROS Noetic、MoveIt、catkin tools、rviz visual tools、moveit visual tools。
2. 建立 catkin workspace：

   ```bash
   mkdir -p ~/catkin_ws/src
   cd ~/catkin_ws/src
   git clone --recurse-submodules git@github.com:xianzeYao/lego.git
   ```

3. 如果 clone 时没有带 submodule：

   ```bash
   cd ~/catkin_ws/src/lego
   git submodule update --init --recursive
   ```

4. 把 submodule 里的 ROS package 暴露给 workspace。一个实用做法是建软链接：

   ```bash
   ln -s ~/catkin_ws/src/lego/APEX-MR ~/catkin_ws/src/apex_mr
   ln -s ~/catkin_ws/src/lego/Robot_Digital_Twin/gazebo ~/catkin_ws/src/robot_digital_twin
   ln -s ~/catkin_ws/src/lego/Robot_Digital_Twin/moveit_config ~/catkin_ws/src/dual_gp4_moveit_config
   ```

5. 编译：

   ```bash
   cd ~/catkin_ws
   catkin build
   source devel/setup.bash
   ```

6. 运行一个小任务：

   ```bash
   roslaunch apex_mr lego_assign.launch task:=cliff
   roslaunch apex_mr lego.launch task:=cliff
   ```

注意：

- 这条路线主要是复现原始工作，不是我们的最终 RM75 + Isaac Sim 路线。
- 如果 ROS package 名、launch 文件或依赖缺失，需要回到 APEX-MR README 和 `Robot_Digital_Twin` 的 package 结构逐项对齐。

## 路线 B：Isaac Sim / BrickSim 方向

如果目标是做单臂 LEGO manipulation 复现，优先用这条路线。

适合场景：

- 使用自己的 RM75 URDF。
- 使用自己的改装 LEGO tool。
- 想在 Isaac Sim / BrickSim 里做 LEGO 接触和连接仿真。
- 第一阶段只做单臂顺序执行，不做多机器人任务分配。

基本步骤：

1. 安装 NVIDIA driver，并确认 GPU 可用：

   ```bash
   nvidia-smi
   ```

2. 按 BrickSim 支持的版本安装 Isaac Sim。

3. 进入 BrickSim submodule，先跑官方 demo：

   ```bash
   cd ~/catkin_ws/src/lego/BrickSim
   ./scripts/download_prebuilt_native.sh
   uv sync --locked
   uv run bricksim demos/demo_assembly.py
   ```

4. 如果官方 demo 不能跑，不要先调 RM75。先解决：

   - Isaac Sim 版本。
   - Python / `uv` 环境。
   - native extension 加载。
   - NVIDIA driver 和 Vulkan/渲染问题。

5. 官方 demo 成功后，再导入我们自己的资产：

   ```text
   Attempt/RM75_gripper/
   Attempt/lego_test_open_fixed.stl
   ```

6. 按顺序验证：

   - RM75 URDF 能导入。
   - 所有关节能动，方向和限位正确。
   - 改装 tool 正确挂到 flange。
   - tool TCP / assemble TCP / disassemble TCP 等 frame 可视化正确。
   - 单个 LEGO brick 能在已知 pose 生成。
   - 一次 pick -> lift -> place -> press -> release 闭环能执行。

7. 更详细的逐项检查见：

   ```text
   Attempt/docs/isaac_bricksim_lego_migration_checklist.md
   ```

8. 三个外部库的角色和取舍见：

   ```text
   Attempt/docs/repository_overview.md
   ```

## 第一目标

第一阶段不要追求完整自动 LEGO 装配。目标应该收敛到：

```text
single RM75 arm + modified LEGO tool + one LEGO brick
pick -> lift -> place -> press -> release
```

验收标准：

- Isaac Sim / BrickSim 官方 demo 能跑。
- RM75 能导入并控制。
- 改装 tool 和 TCP frame 正确。
- 单块积木能被拿起、移动、放下、按压、释放。
- 日志里能记录目标 pose、实际 pose、接触/连接状态和最终误差。

只有这个循环稳定后，再扩展到：

1. BrickSim 真实连接逻辑。
2. 两块积木堆叠。
3. 简单 instruction JSON。
4. APEX-MR 风格 action sequence。
5. 更自动的 planning。

## 修改 Submodule 的建议流程

如果之后要改 APEX-MR、Robot_Digital_Twin 或 BrickSim 源码，不要直接在 detached HEAD 上长期写。

推荐流程：

```bash
cd APEX-MR
git switch -c lego-rm75-adapter
# 修改、提交、推送到 xianzeYao/APEX-MR
git add .
git commit -m "Add RM75 LEGO adapter notes"
git push -u origin lego-rm75-adapter
```

然后回到顶层仓库提交 submodule 指针：

```bash
cd ..
git add APEX-MR
git commit -m "Update APEX-MR submodule pointer"
git push
```

同理适用于 `Robot_Digital_Twin/` 和 `BrickSim/`。
