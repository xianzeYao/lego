# 仓库总览

这个仓库是单臂 LEGO 拼装复现与后续 Isaac Sim / BrickSim 实验的工作区。外部项目现在以 submodule 形式接入，并且指向 `xianzeYao` 名下的 fork。这样我们既可以固定复现版本，也可以在需要时修改外部源码并提交到自己的 fork。

当前仓库的核心分工：

- `Attempt/`：我们的主工作区，放 RM75 机械臂、改装 LEGO tool、自定义 STL、复现文档和后续实验脚本。
- `APEX-MR/`：原论文的高层 LEGO 装配规划与执行参考。
- `Robot_Digital_Twin/`：APEX-MR 原始 ROS/Gazebo/MoveIt 场景、机器人和 LEGO 资产参考。
- `BrickSim/`：基于 Isaac Sim 的积木物理仿真层，用来处理 LEGO 接触、连接、拆卸和结构坍塌。

第一阶段不建议直接复现完整多机器人系统。更实际的目标是：

```text
单臂 RM75 + 改装 LEGO tool + 一个 LEGO brick
approach -> pick/attach -> lift -> place -> press -> release -> retreat
```

这个闭环跑通后，再把简单的 attach/release 替换成 BrickSim 的连接/接触逻辑，然后逐步加入 APEX-MR 风格的动作。

## 外部 Submodule

### `APEX-MR/`

上游来源：`https://github.com/intelligent-control-lab/APEX-MR`  
本仓库使用的 fork：`https://github.com/xianzeYao/APEX-MR.git`  
固定版本：`46a9448d9eaac5bd5973e0cd064623c5e7f5254e`

它是什么：

- 一个面向 LEGO 装配的多机器人异步规划与执行框架。
- 输入结构化 LEGO 任务，进行任务分配、运动规划、时序图构建和 LEGO 操作策略执行。
- 原始实现依赖 ROS / MoveIt / Robot_Digital_Twin，不是直接为 RM75 + Isaac Sim 写的。
- 对我们最有价值的是任务格式、动作拆解、tool frame 设计和 LEGO 操作 primitive。

我们需要保留关注：

- `config/lego_tasks/`：LEGO 任务和装配描述格式。
- `config/lego_tasks/robot_properties/`：不同 tool frame 的 DH 配置。
- `src/lego_policy.cpp`、`include/task.h`：LEGO 动作策略和 action 定义。
- 稳定性分析、任务分配代码：后期参考。
- `APEX-MR/docs/`：配置、任务分配、运动规划说明。

第一阶段可以先不管：

- 双臂/多臂 ILP 任务分配。
- TPG/ADG 异步执行图。
- handover。
- 完整 ROS/MFI 硬件接口。

我们什么时候会用到它：

- 一开始只读，用来理解 LEGO 拼装到底需要哪些动作。
- 单块积木动作跑通后，把它的动作词汇迁移到我们自己的 Isaac/BrickSim 脚本里。
- 后续如果要读取按层 LEGO 说明书，可以考虑复用或转换它的 JSON 任务格式。
- 很后面如果回到多臂或长序列装配，再考虑 ILP、TPG/ADG 和稳定性逻辑。

主要阻力：

- 它假设的是 GP4 等原始机器人和 MoveIt planning group。
- 它不是只有一个 TCP，而是用多个任务相关 tool frame。
- 依赖较重，包括 ROS、MoveIt、Gurobi 和 Robot_Digital_Twin。
- 直接整体迁移到 Isaac Sim 工作量偏大，不适合第一阶段。

### `Robot_Digital_Twin/`

上游来源：`https://github.com/intelligent-control-lab/Robot_Digital_Twin.git`  
本仓库使用的 fork：`https://github.com/xianzeYao/Robot_Digital_Twin.git`  
固定版本：`017120d2b3fb2941fbeeb581d94f41b56d00df1d`

它是什么：

- APEX-MR 使用的 ROS/Gazebo/MoveIt digital twin。
- 包含 GP4/Fanuc/Yaskawa 风格机器人描述、MoveIt 配置、LEGO STL、底板、环境 mesh 和原始 LEGO EOAT/tool mesh。
- 它是原始工作中机器人、场景、坐标系和资产的参考库。

我们需要保留关注：

- `gazebo/urdf/`：URDF/xacro 参考。
- `gazebo/meshes/eoat/`：原始 LEGO tool head 参考。
- `gazebo/meshes/lego/`：LEGO STL 和底板参考。
- `moveit_config/`：原始 planning group 和 end-effector link 配置。
- 生成过的 URDF/SRDF：参考 tool 如何挂到机器人腕部。

第一阶段可以先不管：

- 如果选择 Isaac Sim，Gazebo 运行时不是必须。
- GP50/Fanuc 模型只作为参考，不作为主目标。
- 相机资产等到做感知时再看。

我们什么时候会用到它：

- 导入资产时，对比我们的 RM75/tool URDF 和原始 `link_tool`、EOAT mesh、collision geometry、end-effector 链。
- 调试坐标系时，对比 TCP/tool transform 和 LEGO 放置约定。
- 如果要跑 APEX-MR 原始 ROS baseline，再使用它的 MoveIt/Gazebo 配置。

主要阻力：

- URDF/xacro 路径是 ROS package 风格，可能有 package-relative 假设。
- Isaac Sim 导入时可能要修 mesh 路径、单位、惯量、collision、joint axis。
- 原始 tool 是为他们的机器人和策略设计的；我们的改装 tool 才是后续实验的主基准。

### `BrickSim/`

上游来源：`https://github.com/intelligent-control-lab/BrickSim.git`  
本仓库使用的 fork：`https://github.com/xianzeYao/BrickSim.git`  
固定版本：`cbd5de3238e6ac12f44ef699e1507a9f16bdafc3`

它是什么：

- 基于 Isaac Sim 的 interlocking brick 物理仿真器。
- 提供 LEGO 接触、snap-fit、装配/拆卸 demo、结构破坏/坍塌、连接事件和 Python/C++ 扩展。
- 它不是完整 planner；它更像是在我们已经知道要怎么动之后，验证 LEGO 物理交互是否合理的仿真层。

我们需要保留关注：

- `demos/demo_assembly.py`：第一优先级 smoke test。
- `demos/demo_inhand.py`：后续复杂 manipulation 参考。
- `python/`：Python API 和包代码。
- `native/`：本地扩展源码。
- `resources/`：brick、robot 和场景资源。
- `scripts/download_prebuilt_native.sh`：预编译 native 扩展下载脚本。

第一阶段可以先不管：

- teleoperation demo。
- in-hand manipulation demo。
- native 源码修改，除非预编译扩展不够用。

我们什么时候会用到它：

- Linux 机器上先跑官方 demo，确认 Isaac Sim / BrickSim 环境可用。
- 然后加载 RM75、加载一个 brick，验证 Isaac Sim 能运行、渲染和控制机械臂。
- 最后把 fake attach/release 换成 BrickSim 的 connection event 或 constraint。
- 多块积木阶段，用它检查连接是否成立、结构是否稳定。

主要阻力：

- Isaac Sim 基本是 Linux + NVIDIA 路线，Mac 不适合跑这部分。
- 8 GB 显存可以先跑小场景，但 16 GB 系统内存偏紧；32 GB 会舒服很多。
- BrickSim 有 native extension / prebuilt binary 要求。
- 自定义 LEGO STL 不会天然变成 BrickSim 可识别的 interlocking part，可能需要补 metadata 或先用简单刚体近似。

## 本地 Attempt 资产

### `Attempt/`

它包含：

- RM75 机械臂相关文件。
- AG2F90-C / 改装夹爪资产。
- 自定义 LEGO/tool STL：`Attempt/lego_test_open_fixed.stl`。
- 项目文档和检查清单。

我们需要保留：

- RM75 URDF 变体和 mesh。
- 改装 tool 和 LEGO STL。
- `Attempt/docs/` 下的复现文档。

后续可以清理：

- 确定哪个 URDF 正确后，删除重复或错误版本。
- Isaac Sim 导入稳定后，删除不用的 mesh 格式。
- 被正式 pipeline 替代的临时脚本。

主要阻力：

- URDF 可能“看起来能加载”，但 collision、惯量、单位、joint axis、tool TCP 仍然是错的。
- STL 原点和单位很容易出问题。
- 改装 LEGO pickup head 很可能需要多个命名 frame：nominal、assemble、disassemble、alt、press 等，而不是只靠一个 TCP。

## 为什么用 Fork Submodule

我们后续大概率会读、改、调试 APEX-MR、Robot_Digital_Twin 和 BrickSim。现在它们是指向我们自己 fork 的 submodule，而不是直接指向上游。

好处：

- 可以从原作者 upstream 拉更新。
- 可以把我们对外部项目的修改提交到自己的 fork。
- 顶层 `lego` 仓库更小，只记录精确 submodule 版本。

代价：

- 新机器 clone 后必须初始化 submodule。
- 修改 submodule 需要两次提交：先在 submodule 内提交，再在顶层仓库提交新的 submodule 指针。
- 如果 submodule 处于 detached HEAD，长期修改前应该先建分支。

常用命令：

```bash
git clone --recurse-submodules git@github.com:xianzeYao/lego.git
git submodule update --init --recursive
git submodule status
```

## 三个库之间的关系

可以把它们理解成分层：

```text
按层 LEGO 说明书
        |
        v
任务表示
APEX-MR JSON 是参考，但第一版可以更简单
        |
        v
动作序列
pick_down / pick_twist / drop_down / drop_twist / press_down
        |
        v
机器人具体运动
RM75 URDF + 改装 tool + Isaac Sim controller/planner
        |
        v
LEGO 物理验证
BrickSim contact / connection / disassembly / collapse
```

`Robot_Digital_Twin` 更像旁边的原始资产和坐标系参考库。我们如果选择 Isaac Sim，不一定要跑它的 Gazebo runtime，但它能告诉我们原作者对 robot link、LEGO mesh、EOAT geometry 和 MoveIt group 的假设。

实际使用原则：

- `Attempt/` 是我们的机器人和 tool 真值来源。
- `APEX-MR/` 是装配动作设计、任务拆解和后期规划的参考。
- `Robot_Digital_Twin/` 是原始资产和坐标系约定的参考。
- `BrickSim/` 是机械臂运动可控之后的 LEGO 物理验证层。

## 推荐复现路线

第一版避免 text-to-LEGO，也避免完整多机器人 planner：

```text
Linux/NVIDIA 环境
        |
        v
跑通 BrickSim 官方单臂/装配 demo
        |
        v
在 Isaac/BrickSim 场景中导入 RM75 URDF 和改装 tool
        |
        v
选一个 LEGO 说明书中的单步或简化 JSON
        |
        v
使用 APEX-MR 任务表示或更简单的本地格式
        |
        v
单臂顺序执行
        |
        v
APEX-MR 风格 LEGO policy
grasp pose -> place pose -> twist/press/release
        |
        v
RM75-specific IK / Isaac Sim controller
        |
        v
BrickSim 验证接触、连接、拆卸和坍塌
```

重要判断：

- APEX-MR 不只是 scheduler，它里面也有 LEGO policy 和 motion-planning 逻辑。
- `Robotic_Lego_Manipulation` 已经评估过并从主仓库移除，因为它和 APEX-MR 在 LEGO action、tool frame、pose/IK 逻辑上有重叠。
- 更清晰的切分是：
  - APEX-MR 或一个简化 APEX-MR adapter 决定任务顺序和动作序列。
  - APEX-MR 的 LEGO policy 代码提供动作词汇。
  - 我们自己的 RM75/Isaac 层负责算出并执行 RM75 关节目标。

第一阶段的主基准：

- 环境和物理：`BrickSim/`。
- 机器人和 tool 资产：`Attempt/`。
- 任务格式、动作策略和后期规划：`APEX-MR/`。

## 分阶段计划

### Phase 0：Linux 机器和 smoke test

目标：

- 确认 Linux/NVIDIA 机器能跑 Isaac Sim 和 BrickSim。

涉及：

- `BrickSim/`
- `Attempt/docs/linux_reproduction.md`

可能失败：

- Isaac Sim 版本不匹配。
- NVIDIA driver / CUDA / runtime 不匹配。
- BrickSim prebuilt native extension 下载或加载失败。
- `uv`、Isaac Sim Python、Isaac Lab 周边环境不匹配。

原则：官方 BrickSim demo 没跑通前，不要急着调 RM75。

### Phase 1：导入 RM75 和 tool

目标：

- 在 Isaac Sim 中加载 RM75 URDF 和改装 LEGO tool。
- 检查 joint axis、joint limit、mesh scale、collision geometry 和 TCP frame。

涉及：

- `Attempt/`
- `Robot_Digital_Twin/gazebo/urdf/` 只作对比。
- `Robot_Digital_Twin/gazebo/meshes/eoat/` 只作原始 tool 参考。

可能失败：

- mesh 看起来正常，但 collision 不对。
- STL 单位或原点错。
- tool frame 方向错。
- URDF importer 丢掉或近似了 collision/inertial。
- 改装 tool 需要额外 fixed links 表示不同 TCP。

### Phase 2：单块积木 fake attach/release

目标：

- 用简单 attach/detach constraint 或 scripted parent relationship 跑通完整 pick/place/press。

涉及：

- `Attempt/`
- 后续可以在 `Attempt/` 下新增 Isaac Sim 脚本或本地 package。
- `APEX-MR/src/lego_policy.cpp` 只作参考。

可能失败：

- IK 到不了，原因可能是 TCP 或 base frame 错。
- collision checking 阻塞合理路径。
- press 方向相对 stud 错。
- fake attach 会隐藏真实接触问题，所以这一阶段只验证运动，不代表 LEGO 物理成功。

### Phase 3：迁移 APEX-MR 动作词汇

目标：

- 为单臂实现有用的 LEGO 操作动作：
  `pick_down`、`pick_twist`、`drop_down`、`drop_twist`、`place_up`、`press_down`。

涉及：

- `APEX-MR/include/task.h`
- `APEX-MR/src/lego_policy.cpp`
- `APEX-MR/src/lego/Lego.cpp`
- `APEX-MR/config/lego_tasks/robot_properties/`
- 我们自己的 Isaac/BrickSim 控制脚本。

可能失败：

- 上游动作默认他们自己的 tool geometry，距离和角度不能直接照抄。
- `nominal tool`、`assemble tool`、`disassemble tool`、`alt tool`、`alt assemble tool`、`handover assemble tool` 通常是不同任务 TCP/transform，不一定是不同实体工具。
- 需要为我们的改装 tool 重新标定这些 transform。

### Phase 4：把 fake attach 换成 BrickSim 物理

目标：

- 用 BrickSim 的接触/连接行为判断 brick 是否被抓住、放下、连接或拆开。

涉及：

- `BrickSim/python/bricksim/mdp/connection_events.py`
- `BrickSim/python/bricksim/mdp/connection_state.py`
- `BrickSim/python/bricksim/mdp/brick_part.py`
- 本地仿真脚本。

可能失败：

- 自定义 STL 没有 BrickSim 需要的 stud/hole metadata。
- 接触阈值需要根据 tool 和 brick 调。
- 稳定连接需要更慢的 press/release 轨迹。
- physics timestep 或 solver 设置导致 snap 不稳定。

### Phase 5：多块积木和按层说明书

目标：

- 输入一个小的 layer-by-layer instruction，拼两块或更多积木。

涉及：

- `APEX-MR/config/lego_tasks/`，如果复用或转换它的 JSON。
- `Attempt/` 下的本地 instruction parser/generator。
- BrickSim 的结构和连接工具。

可能失败：

- 拼装顺序影响可达性和稳定性。
- 已放置积木会造成 collision。
- 单块成功的 press 动作可能扰动前一块。
- 可能需要简单稳定性检查再执行完整序列。

### Phase 6：可选 planner 和长序列逻辑

目标：

- 单臂流程稳定后，再考虑更自动的规划。

涉及：

- 如果回到多臂或完整论文复现，再看 APEX-MR 的 task assignment / planning。
- 如果结构稳定性成为瓶颈，再看 StableLego。
- 如果运动规划速度成为瓶颈，再看 VAMP-MR。

可能失败：

- 完整 APEX-MR 面向多机器人异步执行。对单臂而言，很多部分第一阶段只会增加复杂度。
- ILP、TPG、ADG 有用，但不是证明 RM75 能拼 LEGO 的前置条件。

## 相关上游项目

这些项目和同一研究线相关，但当前不作为本仓库 submodule。

### `Robotic_Lego_Manipulation`

来源：`https://github.com/intelligent-control-lab/Robotic_Lego_Manipulation`

状态：

- 已评估并从本仓库移除。
- 它和 APEX-MR 在 task JSON、LEGO action state、tool-frame variants、LEGO pose/IK 逻辑上有重叠。

当前建议：

- 不作为 submodule 依赖保留。
- 只有当我们明确需要 Fanuc 示例、`Stream_Motion_Controller` 接口、单独 F/T sensor driver、RealSense node 或更简单的单文件 action-state-machine 参考时，再重新看。

### `StableLego`

来源：`https://github.com/intelligent-control-lab/StableLego`

可能作用：

- LEGO 装配结构的静态稳定性检查。
- APEX-MR 会引用它做 stability-aware task assignment，BrickSim 中也有相关改造代码。

当前建议：

- 不进入第一阶段。
- 等到拼超过少量积木，或者需要自动选择稳定装配顺序时再看。

### `VAMP-MR`

来源：APEX-MR README 中链接。

可能作用：

- 加速多机器人运动规划。

当前建议：

- 单臂第一阶段不需要。
- 只有当运动规划成为主要瓶颈，或者重新做多臂规划时再看。

### `Robotic_Lego_Controller`

状态：

- 仅凭名字尚未确认公开源码和准确仓库地址。

当前建议：

- 没有准确 URL 或本地源码前先忽略。
- 如果后续拿到源码，把它当作低层控制器参考，不替代 BrickSim 或 APEX-MR。

## 什么保留，什么删除，什么重生成

保留在 git：

- `APEX-MR/`、`Robot_Digital_Twin/`、`BrickSim/` 的 submodule 指针。
- 复现环境需要的 mesh 和 robot assets。
- `Attempt/` 下我们的 robot/tool 资产和文档。
- 描述复现 pipeline 的小脚本。

删除或 ignore：

- `__pycache__/`、build 目录、日志、临时下载、仿真缓存。
- 能通过命令重建的大型下载二进制。
- OS 元数据，例如 `*:Zone.Identifier`。

原因：

- 仓库应该保存源码、文档、资产和外部 submodule 的精确版本，而不是机器相关的构建产物。
- 如果某个下载文件确实必须保留，先记录准确命令和版本，再决定是否提交。

## 第一复现目标

不要从完整自动装配开始。第一阶段仍然是：

```text
RM75 arm + modified LEGO tool + one LEGO brick
approach -> pick/attach -> lift -> place -> press -> release -> retreat
```

跑通后再做：

1. 用 BrickSim contact 或 snap-fit 替换 fake attach/release。
2. 加入 `pick_twist` 和 `drop_twist`。
3. 执行两块上下堆叠。
4. 加入简单 instruction JSON。
5. 最后再考虑自动 planning 或 APEX-MR task format 转换。
