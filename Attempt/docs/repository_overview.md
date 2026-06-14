# Repository Overview

This repository is an experiment workspace for single-arm LEGO manipulation and future Isaac Sim / BrickSim reproduction. External upstream projects are vendored as normal folders, not submodules, so local edits can be committed directly to this `lego` repository.

## Vendored Libraries

### `APEX-MR/`

Source: `https://github.com/intelligent-control-lab/APEX-MR`  
Vendored commit: `46a9448d9eaac5bd5973e0cd064623c5e7f5254e`

What it is:

- Multi-robot asynchronous planning and execution framework for LEGO assembly.
- Provides LEGO task JSON format, task assignment, motion planning, TPG/ADG execution graph, and LEGO manipulation policies.
- Contains the most useful manipulation logic for us: `pick_down`, `pick_twist`, `drop_down`, `drop_twist`, `place_up`, `press_down`, support, and handover.

What we keep:

- Task formats under `config/lego_tasks/`.
- Tool-frame DH variants under `config/lego_tasks/robot_properties/`.
- LEGO policy/action logic in `src/lego_policy.cpp` and `include/task.h`.
- Stability/task-assignment code as reference.

What we do not need first:

- Dual-arm ILP assignment.
- TPG/ADG asynchronous execution.
- Handover.
- Full ROS/MFI hardware interface.

Reason:

- We are starting from a single-arm reproduction. APEX-MR is mainly a reference for action design, tool frames, task representation, and the original ROS baseline.

### `Robot_Digital_Twin/`

Source: `https://github.com/intelligent-control-lab/Robot_Digital_Twin.git`  
Vendored commit: `017120d2b3fb2941fbeeb581d94f41b56d00df1d`

What it is:

- ROS/Gazebo/MoveIt digital twin used by APEX-MR.
- Provides GP4 URDF/xacro, MoveIt config, LEGO STL meshes, baseplates, environment meshes, and the original LEGO EOAT mesh.

What we keep:

- `gazebo/urdf/` for URDF/xacro reference.
- `gazebo/meshes/eoat/` for the original LEGO tool head reference.
- `gazebo/meshes/lego/` for LEGO STL and baseplate reference.
- `moveit_config/` for original planning groups and end-effector links.

What we do not need first:

- Gazebo runtime if we choose Isaac Sim.
- GP50/Fanuc models unless needed as reference.
- Camera assets unless we add perception.

Reason:

- This is where the physical tool and robot scene assets live. It lets us compare our RM75 tool setup against the original GP4 LEGO tool assumptions.

### `BrickSim/`

Source: `https://github.com/intelligent-control-lab/BrickSim.git`  
Vendored commit: `cbd5de3238e6ac12f44ef699e1507a9f16bdafc3`

What it is:

- Isaac Sim based physics simulator for interlocking brick assemblies.
- Provides snap-fit/contact-rich LEGO simulation, assembly/disassembly demos, breakage/collapse behavior, and Python/C++ extension code.

What we keep:

- `demos/demo_assembly.py` as the first smoke test.
- `python/` API and package code.
- `native/` extension code.
- `resources/` assets and robot/brick resources.
- `scripts/download_prebuilt_native.sh` and build scripts.

What we do not need first:

- Teleoperation demo unless we add a leader device.
- In-hand manipulation demo unless our tool path needs it.
- Native source modification unless the prebuilt extension is insufficient.

Reason:

- BrickSim should be the physics validation layer after our RM75 tool can execute a one-brick pick/place/press sequence.

## Local Attempt Assets

### `Attempt/`

What it contains:

- RM75 arm files.
- AG2F90-C / modified gripper assets.
- Custom LEGO/tool STL: `Attempt/lego_test_open_fixed.stl`.
- Project docs/checklists.

What we keep:

- The RM75 URDF variants and meshes.
- The modified tool and LEGO STL.
- Documentation under `Attempt/docs/`.

What to clean later:

- Duplicate or wrong URDF variants once we know which one imports correctly.
- Unused mesh formats after Isaac Sim import is stable.
- Experimental scripts that are replaced by the final Isaac/BrickSim pipeline.

## Why Vendor Instead Of Submodules

We expect to edit source code in APEX-MR, Robot_Digital_Twin, and BrickSim while experimenting. If these were submodules, edits would belong to those nested repositories and would need fork/remotes/submodule pointer management. Vendoring makes every file a normal part of this `lego` repository.

Tradeoff:

- Easier local modification and single-repo commits.
- Larger repository.
- Harder upstream syncing.

This is acceptable for the current experimental phase. If the project becomes long-lived, we can later split modifications into forks or submodules.

## First Reproduction Goal

Do not start with full automatic assembly. The first useful milestone is:

```text
RM75 arm + modified LEGO tool + one LEGO brick
approach -> pick/attach -> lift -> place -> press -> release -> retreat
```

After this is repeatable:

1. Replace fake attach/release with BrickSim contact or snap-fit logic.
2. Add `pick_twist` and `drop_twist` based on APEX-MR policy.
3. Execute two stacked bricks.
4. Add simple instruction JSON.
5. Only then consider automatic planning or APEX-MR task format conversion.

