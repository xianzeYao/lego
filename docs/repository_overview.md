# Third Party 说明

本仓库的外部依赖统一放在 `third_party/` 下，并且都以 submodule 形式指向 `xianzeYao` 名下的 fork。这样做的目的很明确：既能固定复现版本，又能在需要时修改外部源码并提交到自己的 fork。

当前 third party 目录：

```text
third_party/
  APEX-MR/
  BrickSim/
  Robot_Digital_Twin/
```

## `third_party/APEX-MR`

上游：`https://github.com/intelligent-control-lab/APEX-MR`  
Fork：`https://github.com/xianzeYao/APEX-MR.git`  
固定版本：`46a9448d9eaac5bd5973e0cd064623c5e7f5254e`

作用：

- 作为 LEGO 装配任务规划和动作策略参考。
- 关注它的任务 JSON、LEGO action、tool-frame variants、`lego_policy.cpp` 和 task/action 数据结构。
- 第一阶段不直接复现完整多机器人 ILP、TPG/ADG、handover 和硬件接口。

我们怎么用：

- 先把它当参考资料读。
- 单块 LEGO 动作跑通后，迁移其中的 `pick_down`、`pick_twist`、`drop_down`、`drop_twist`、`press_down` 等动作思想。
- 后续如果要读取按层 LEGO 说明书，可以复用或转换它的任务格式。

## `third_party/BrickSim`

上游：`https://github.com/intelligent-control-lab/BrickSim.git`  
Fork：`https://github.com/xianzeYao/BrickSim.git`  
固定版本：`cbd5de3238e6ac12f44ef699e1507a9f16bdafc3`

作用：

- 作为 Isaac Sim 中的 LEGO interlocking brick 物理仿真层。
- 负责 LEGO 接触、连接、拆卸、结构破坏和 collapse 等行为。
- 它不是 planner；它是在机械臂动作已经能执行之后，用来验证 LEGO 物理交互是否成立。

我们怎么用：

- Linux/NVIDIA 机器上先跑官方 demo。
- 然后导入 RM75 和改装 tool。
- 第一版可以先用 fake attach/release 跑通动作，再逐步替换成 BrickSim connection/contact 逻辑。

## `third_party/Robot_Digital_Twin`

上游：`https://github.com/intelligent-control-lab/Robot_Digital_Twin.git`  
Fork：`https://github.com/xianzeYao/Robot_Digital_Twin.git`  
固定版本：`017120d2b3fb2941fbeeb581d94f41b56d00df1d`

作用：

- 作为 APEX-MR 原始 ROS/Gazebo/MoveIt 数字孪生和资产参考。
- 里面有原始机器人 URDF/xacro、MoveIt 配置、LEGO STL、底板、EOAT/tool mesh。
- 如果我们走 Isaac Sim 路线，它不是主要 runtime，但对比坐标系、tool 挂载方式和 LEGO asset 很有用。

我们怎么用：

- 对比原作者的 tool link、end-effector link、LEGO mesh 和 baseplate 约定。
- 必要时用它复现 APEX-MR 原始 ROS baseline。
- 不把它作为第一阶段 RM75 + Isaac Sim 的主工程。

## 修改 Submodule 的规则

如果要改 third party 源码，推荐流程是：

```bash
cd third_party/APEX-MR
git switch -c lego-rm75-adapter
# 修改并提交
git add .
git commit -m "Add RM75 adapter notes"
git push -u origin lego-rm75-adapter
```

然后回到顶层仓库提交 submodule 指针：

```bash
cd ../..
git add third_party/APEX-MR
git commit -m "Update APEX-MR submodule pointer"
git push
```

`BrickSim` 和 `Robot_Digital_Twin` 同理。

## Clone 时的注意事项

新机器推荐直接：

```bash
git clone --recurse-submodules git@github.com:xianzeYao/lego.git
```

如果已经 clone 了主仓库：

```bash
git submodule update --init --recursive
```
