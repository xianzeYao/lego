# Repository Overview

This repository is an experiment workspace for single-arm LEGO manipulation and future Isaac Sim / BrickSim reproduction. External upstream projects are vendored as normal folders, not submodules, so local edits can be committed directly to this `lego` repository.

The short version:

- `Attempt/` is our working area: RM75 arm, modified LEGO tool, custom STL, and project notes.
- `APEX-MR/` is the original high-level LEGO assembly planning/execution reference.
- `Robot_Digital_Twin/` is the original ROS/Gazebo/MoveIt asset and robot scene reference used by APEX-MR.
- `BrickSim/` is the Isaac Sim physics layer for interlocking brick contact, snapping, disassembly, and collapse.
- `Robotic_Lego_Manipulation/` is the earlier LEGO manipulation skill layer: task JSON, grasp/place/support pose computation, tool-frame variants, IK, and ROS goal publication.

For the first reproduction, we should not try to reproduce the full multi-robot paper stack. The practical target is one RM75 arm, one modified tool, and one brick in simulation:

```text
approach -> pick/attach -> lift -> place -> press -> release -> retreat
```

After this loop works, we can replace the fake attach/release with BrickSim connection/contact behavior and then add more APEX-MR-style actions.

## Vendored Libraries

### `APEX-MR/`

Source: `https://github.com/intelligent-control-lab/APEX-MR`  
Vendored commit: `46a9448d9eaac5bd5973e0cd064623c5e7f5254e`

What it is:

- Multi-robot asynchronous planning and execution framework for LEGO assembly.
- It takes a structured LEGO task, assigns work to robots, plans motions, builds temporal execution graphs, and runs LEGO manipulation policies.
- It is written for the original ROS/MoveIt/digital-twin setup, not directly for our RM75 + Isaac Sim setup.
- The useful parts for us are the task format, tool-frame ideas, action primitives, and the way the paper decomposes LEGO assembly into repeatable manipulation actions.

What we keep:

- Task formats under `config/lego_tasks/`.
- Tool-frame DH variants under `config/lego_tasks/robot_properties/`.
- LEGO policy/action logic in `src/lego_policy.cpp` and `include/task.h`.
- Stability/task-assignment code as reference.
- Existing explanatory docs under `APEX-MR/docs/`, especially configuration, task assignment, and motion planning notes.

What we do not need first:

- Dual-arm ILP assignment.
- TPG/ADG asynchronous execution.
- Handover.
- Full ROS/MFI hardware interface.

Reason:

- We are starting from a single-arm reproduction. APEX-MR is mainly a reference for action design, tool frames, task representation, and the original ROS baseline.

When we will encounter it:

- First pass: read only. Use it to understand what actions a LEGO assembly policy needs.
- After one-brick motion works: copy the action vocabulary into our own Isaac/BrickSim script.
- Later: adapt its JSON task format if we want to feed layer-by-layer instructions into our simulator.
- Much later: revisit task assignment, TPG/ADG, and stability if we move back to multi-arm or long-horizon assembly.

Expected friction:

- APEX-MR assumes GP4-style robots and MoveIt planning groups.
- Its tool frames are not a single URDF end-effector; several task-specific TCP/tool transforms are configured separately.
- Some dependencies are research-stack heavy, such as ROS, MoveIt, Gurobi, and the external digital twin.
- Running it unchanged is useful as a baseline, but directly porting the whole system into Isaac Sim would be too much work for the first milestone.

### `Robot_Digital_Twin/`

Source: `https://github.com/intelligent-control-lab/Robot_Digital_Twin.git`  
Vendored commit: `017120d2b3fb2941fbeeb581d94f41b56d00df1d`

What it is:

- ROS/Gazebo/MoveIt digital twin used by APEX-MR.
- Provides GP4/Fanuc/Yaskawa-style robot descriptions, MoveIt config, LEGO STL meshes, baseplates, environment meshes, and the original LEGO EOAT mesh.
- This is the asset source and original coordinate-frame reference for the APEX-MR work.

What we keep:

- `gazebo/urdf/` for URDF/xacro reference.
- `gazebo/meshes/eoat/` for the original LEGO tool head reference.
- `gazebo/meshes/lego/` for LEGO STL and baseplate reference.
- `moveit_config/` for original planning groups and end-effector links.
- The original generated URDF/SRDF files as examples of how the tool was attached to the robot wrist.

What we do not need first:

- Gazebo runtime if we choose Isaac Sim.
- GP50/Fanuc models unless needed as reference.
- Camera assets unless we add perception.

Reason:

- This is where the physical tool and robot scene assets live. It lets us compare our RM75 tool setup against the original GP4 LEGO tool assumptions.

When we will encounter it:

- During asset import: compare our RM75/tool URDF against the original `link_tool`, EOAT mesh, collision geometry, and end-effector attachment chain.
- During frame debugging: compare TCP/tool transforms and brick placement conventions.
- During ROS baseline reproduction: use its MoveIt/Gazebo config if we decide to run APEX-MR in its original environment.

Expected friction:

- The URDF/xacro paths are ROS package oriented and may contain absolute or package-relative assumptions.
- Isaac Sim import may need mesh path fixes, unit checks, inertial cleanup, collision simplification, and joint-axis verification.
- The original tool is designed around their robot and their brick manipulation strategy; our modified tool must be treated as the primary source of truth.

### `BrickSim/`

Source: `https://github.com/intelligent-control-lab/BrickSim.git`  
Vendored commit: `cbd5de3238e6ac12f44ef699e1507a9f16bdafc3`

What it is:

- Isaac Sim based physics simulator for interlocking brick assemblies.
- Provides snap-fit/contact-rich LEGO simulation, assembly/disassembly demos, breakage/collapse behavior, connection events, and Python/C++ extension code.
- It is not a full planner by itself. It gives us a better physics model for bricks once we already know what motions to command.

What we keep:

- `demos/demo_assembly.py` as the first smoke test.
- `demos/demo_inhand.py` as a later reference for more complex manipulation.
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

When we will encounter it:

- Linux setup: run the official demo unchanged before importing our own robot.
- First custom simulation: load RM75, load one brick, and validate that Isaac Sim can step, render, and control the arm.
- Contact validation: replace fake attach/release with BrickSim connection events or constraints.
- Multi-brick validation: check whether a placed brick is truly connected and whether the structure survives pressing/release.

Expected friction:

- Isaac Sim is Linux/NVIDIA focused. Mac is not a realistic target for this part.
- GPU memory and system memory matter. Your 5060 Ti 8 GB can likely run small scenes, but 16 GB RAM is tight; 32 GB RAM would reduce environment pain.
- BrickSim has native extension/prebuilt binary requirements. Downloaded binaries and generated build products should be treated as reproducible artifacts, not precious source.
- Custom LEGO STL is not automatically a BrickSim-aware interlocking part. We may first use simple rigid-body collision, then map to BrickSim brick parameters or connection metadata.

### `Robotic_Lego_Manipulation/`

Source: `https://github.com/intelligent-control-lab/Robotic_Lego_Manipulation`  
Vendored commit: `9bc91654e708e4d8428ecfa76840103cacb2a19a`

What it is:

- Earlier LEGO manipulation package from the same lab.
- It is closer to the concrete skill/action layer than APEX-MR.
- It reads LEGO task JSON, computes brick grab/place/support poses, runs IK, and publishes joint goals to `Stream_Motion_Controller`.
- It supports Fanuc/Yaskawa-style setups and uses `Robot_Digital_Twin` for the ROS/Gazebo side.

What we keep:

- `include/Lego.hpp` and `src/Lego.cpp` for LEGO geometry, brick pose, support pose, connection bookkeeping, and IK reference.
- `src/ros_nodes/lego_task_planning_node.cpp` for the pick/place/twist/support state machine.
- `config/assembly_tasks/` for example task manuals.
- `config/robot_properties/` for tool-frame variants such as nominal, assemble, disassemble, alt, and alt assemble.
- `config/lego_library.json` for brick dimensions and naming.

What we do not need first:

- Fanuc-specific `Stream_Motion_Controller` runtime.
- Yaskawa service path unless we test against that hardware style.
- ROS/Gazebo launch flow if we are running Isaac Sim first.

Reason:

- This is the most direct source for "given a LEGO task, what concrete poses and joint goals should the robot execute?"
- It is useful before full APEX-MR because it exposes the low-level manipulation assumptions more plainly.

When we will encounter it:

- After BrickSim official demo and RM75 import work.
- When converting one LEGO manual step into grasp pose, place pose, twist motion, and press/release sequence.
- When defining our RM75-specific tool frames.

Expected friction:

- It assumes six-axis Fanuc/Yaskawa-style robots and DH files, not our RM75 URDF directly.
- Its IK and joint limits are tied to the original robot models.
- Its output path is ROS topics for `Stream_Motion_Controller`; in Isaac Sim we will replace that lower layer with an Isaac articulation/RMPflow/controller bridge.
- It may overlap with APEX-MR's LEGO policy code, so we should choose one source of truth per phase instead of stacking two incompatible planners.

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

When we will encounter it:

- Immediately. This is where our actual robot and tool definition should live.
- Every transform, TCP, collision mesh, and joint limit should be verified here before we blame APEX-MR or BrickSim.

Expected friction:

- URDF may load visually but still have wrong collision shapes, inertial values, scale, axes, or tool TCP.
- STL origin and unit conventions can be wrong even when the mesh looks correct.
- The modified LEGO pickup head probably needs more than one named frame: nominal tool, assemble tool, disassemble tool, alternate orientations, and possibly a handover frame if dual-arm returns later.

## Why Vendor Instead Of Submodules

We expect to edit source code in APEX-MR, Robot_Digital_Twin, and BrickSim while experimenting. If these were submodules, edits would belong to those nested repositories and would need fork/remotes/submodule pointer management. Vendoring makes every file a normal part of this `lego` repository.

Tradeoff:

- Easier local modification and single-repo commits.
- Larger repository.
- Harder upstream syncing.

This is acceptable for the current experimental phase. If the project becomes long-lived, we can later split modifications into forks or submodules.

## How The Libraries Relate

The relationship is easiest to treat as layers:

```text
Layer-by-layer LEGO instruction
        |
        v
Task representation
APEX-MR JSON is the reference, but we can start simpler
        |
        v
Action sequence
pick_down / pick_twist / drop_down / drop_twist / press_down
        |
        v
Robot-specific motion
RM75 URDF + our modified tool + Isaac Sim controller/planner
        |
        v
Brick physics validation
BrickSim contact / connection / disassembly / collapse behavior
```

`Robot_Digital_Twin` sits beside this stack as a reference asset library for the original APEX-MR environment. It is not the runtime we must use if we choose Isaac Sim, but it tells us what the original authors assumed about robot links, LEGO meshes, EOAT geometry, and MoveIt groups.

The practical rule:

- Use `Attempt/` as the source of truth for our robot and tool.
- Use `APEX-MR/` as the source of truth for assembly action ideas and task decomposition.
- Use `Robot_Digital_Twin/` as the source of truth for original assets and frame conventions.
- Use `BrickSim/` as the source of truth for brick physics once the arm motion is already controllable.
- Use `Robotic_Lego_Manipulation/` as the source of truth for concrete LEGO manipulation skill details when implementing the first single-arm action sequence.

## Proposed Reproduction Pipeline

The target pipeline should be staged. The first version should avoid solving text-to-LEGO and avoid the full multi-robot planner:

```text
Linux/NVIDIA environment
        |
        v
BrickSim official single-arm demo
        |
        v
BrickSim/Isaac scene with our RM75 URDF and modified tool
        |
        v
One LEGO instruction/manual step
        |
        v
APEX-MR task representation or simplified equivalent
        |
        v
Single-arm schedule
        |
        v
Robotic_Lego_Manipulation-style skill layer
grasp pose -> place pose -> twist/press/release sequence -> IK/joint targets
        |
        v
Isaac Sim controller for RM75
        |
        v
BrickSim validates contact/connection/collapse
```

Important caveat:

- APEX-MR is not just a pure scheduler; it also contains LEGO policy and motion-planning logic.
- Robotic_Lego_Manipulation also contains task execution and IK logic.
- Therefore the clean integration is not "APEX-MR calculates everything, then Robotic_Lego_Manipulation calculates everything again."
- The cleaner split is:
  - APEX-MR or a simplified APEX-MR-like adapter decides task order and single-arm action sequence.
  - Robotic_Lego_Manipulation provides the concrete pose/action templates.
  - Our RM75/Isaac layer computes or executes the final joint targets.

For the first successful reproduction, the best source of truth should be:

- Environment and physics: `BrickSim/`.
- Robot/tool assets: `Attempt/`.
- Concrete LEGO skills: `Robotic_Lego_Manipulation/`.
- Task/manual format and later planning: `APEX-MR/`.

## Reproduction Phases

### Phase 0: Linux machine and smoke tests

Goal:

- Confirm the Linux/NVIDIA machine can run Isaac Sim and BrickSim.

What we touch:

- `BrickSim/`
- `Attempt/docs/linux_reproduction.md`

What may fail:

- Isaac Sim version mismatch.
- NVIDIA driver/CUDA/runtime mismatch.
- BrickSim prebuilt native extension download or load failure.
- Python environment mismatch around `uv`, Isaac Sim Python, or Isaac Lab.

Do not debug our RM75 robot yet if the official BrickSim demo does not run.

### Phase 1: Import RM75 and tool

Goal:

- Load the RM75 URDF and modified LEGO tool in Isaac Sim.
- Verify joint axes, joint limits, mesh scale, collision geometry, and TCP frames.

What we touch:

- `Attempt/`
- `Robot_Digital_Twin/gazebo/urdf/` only as a comparison reference.
- `Robot_Digital_Twin/gazebo/meshes/eoat/` only as original tool reference.

What may fail:

- Meshes render but collide incorrectly.
- STL unit/origin mismatch.
- Tool frame points in the wrong direction.
- URDF importer drops or approximates collision/inertial data.
- The gripper/tool needs additional fixed links for task-specific TCPs.

### Phase 2: One-brick fake attach/release

Goal:

- Execute one complete pick/place/press loop using a simple attach/detach constraint or scripted parent relationship.

What we touch:

- `Attempt/`
- Possibly a small new Isaac Sim script under `Attempt/` or a new local package.
- `APEX-MR/src/lego_policy.cpp` as a reference only.

What may fail:

- IK cannot reach the pose because TCP or base frame is wrong.
- Collision checking blocks reasonable approach paths.
- Press direction is wrong relative to brick studs.
- Fake attach hides physical errors, so this phase should be treated as motion validation, not real LEGO validation.

### Phase 3: Robotic_Lego_Manipulation action vocabulary

Goal:

- Implement the useful LEGO manipulation actions for our single arm:
  `pick_down`, `pick_twist`, `drop_down`, `drop_twist`, `place_up`, `press_down`.

What we touch:

- `Robotic_Lego_Manipulation/include/Lego.hpp`
- `Robotic_Lego_Manipulation/src/Lego.cpp`
- `Robotic_Lego_Manipulation/src/ros_nodes/lego_task_planning_node.cpp`
- `Robotic_Lego_Manipulation/config/robot_properties/`
- `APEX-MR/include/task.h`
- `APEX-MR/src/lego_policy.cpp`
- `APEX-MR/config/lego_tasks/robot_properties/`
- Our own Isaac/BrickSim control script under `Attempt/`.

What may fail:

- The upstream actions assume their own tool geometry, so distances and rotations are not copy-paste constants.
- Tool variants such as `nominal tool`, `assemble tool`, `disassemble tool`, `alt tool`, `alt assemble tool`, and `handover assemble tool` are usually different task frames/TCP transforms, not necessarily different physical tools.
- We need to calibrate these transforms for the modified tool.

### Phase 4: Replace fake attach with brick physics

Goal:

- Use BrickSim contact/connection behavior to decide whether the brick is held, placed, connected, or disconnected.

What we touch:

- `BrickSim/python/bricksim/mdp/connection_events.py`
- `BrickSim/python/bricksim/mdp/connection_state.py`
- `BrickSim/python/bricksim/mdp/brick_part.py`
- Our local simulation script.

What may fail:

- Custom STL does not contain the metadata BrickSim expects for studs/holes.
- Contact thresholds require tuning for our tool and brick sizes.
- Stable connection needs slower press/release trajectories than pure kinematic placement.
- Physics time step or solver settings may make snapping unstable.

### Phase 5: Multi-brick layer instruction

Goal:

- Feed a small layer-by-layer instruction into the simulation and assemble two or more bricks.

What we touch:

- `APEX-MR/config/lego_tasks/` if we reuse or convert their JSON style.
- Local instruction parser/generator under `Attempt/`.
- BrickSim structure/connection utilities.

What may fail:

- Brick order matters for reachability and stability.
- Collision with already placed bricks appears.
- A press action that works for one brick may disturb the previous brick.
- We may need simple stability checks before running a full sequence.

### Phase 6: Optional planner and long-horizon logic

Goal:

- Only after the single-arm sequence is reliable, consider more automatic planning.

What we touch:

- APEX-MR task assignment/planning logic if we want multi-arm or full paper reproduction.
- StableLego-style analysis if structure stability becomes a bottleneck.
- VAMP-MR-style motion planning if planning speed becomes a bottleneck.

What may fail:

- Full APEX-MR is designed for multi-robot asynchronous execution. For one arm, much of it adds complexity without immediate benefit.
- ILP/TPG/ADG are useful later, but not needed to prove the RM75 tool can assemble bricks.

## Related Upstream Projects

These are related to the same research line but are not currently vendored here.

### `StableLego`

Source: `https://github.com/intelligent-control-lab/StableLego`

Likely role:

- Static stability checking for LEGO assemblies.
- APEX-MR references it for stability-aware task assignment, and BrickSim also has adapted StableLego-related code.

Current recommendation:

- Do not make it part of the first reproduction.
- Revisit it when we assemble more than a few bricks or need to choose a stable build order.

### `VAMP-MR`

Source: linked from the APEX-MR README.

Likely role:

- Accelerated multi-robot motion planning.

Current recommendation:

- Not needed for the single-arm first milestone.
- Revisit only if motion planning becomes the main bottleneck or if we return to multi-arm planning.

### `Robotic_Lego_Controller`

Status:

- Public source was not confirmed from the repository name alone.

Current recommendation:

- Ignore it unless we have the exact URL or local source.
- If it becomes available, evaluate it as a low-level controller reference, not as a replacement for BrickSim or APEX-MR.

## What To Keep, Remove, Or Regenerate

Keep in git:

- Source code in `APEX-MR/`, `Robot_Digital_Twin/`, and `BrickSim/`.
- Meshes and robot assets needed to reproduce the environment.
- `Attempt/` robot/tool assets and docs.
- Small scripts that define our reproduction pipeline.

Remove or ignore:

- Nested `.git/` directories inside vendored repos.
- `__pycache__/`, build directories, logs, temporary downloads, and local simulator caches.
- Large downloaded binaries if they can be reproduced by documented commands.
- OS metadata files such as `*:Zone.Identifier`.

Reason:

- We want the repo to preserve source and important assets, not machine-specific build products.
- If a downloaded file is required and not easy to regenerate, document the exact command/version before deciding whether to commit it.

## First Reproduction Goal

Do not start with full automatic assembly. The first useful milestone remains:

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
