# Linux Reproduction Notes

This repository vendors the upstream APEX-MR and Robot_Digital_Twin source trees so local changes can be committed directly to this `lego` repository.

## Vendored Sources

- `APEX-MR/`
  - Source: `https://github.com/intelligent-control-lab/APEX-MR`
  - Vendored commit: `46a9448d9eaac5bd5973e0cd064623c5e7f5254e`
- `Robot_Digital_Twin/`
  - Source: `https://github.com/intelligent-control-lab/Robot_Digital_Twin.git`
  - Vendored commit: `017120d2b3fb2941fbeeb581d94f41b56d00df1d`

## Recommended Machine

- Ubuntu 22.04 or 24.04.
- NVIDIA GPU and driver if running Isaac Sim / BrickSim.
- At least 32 GB RAM preferred.
- 1 TB SSD is enough for this repo, Isaac Sim, BrickSim, and generated assets.

## Option A: Reproduce APEX-MR / ROS Baseline

Use this if the goal is to run the original APEX-MR stack before migrating to Isaac Sim.

1. Install ROS Noetic on Ubuntu 20.04, or use the APEX-MR Docker workflow.
2. Install MoveIt, catkin tools, rviz visual tools, and moveit visual tools.
3. Place this repository in a catkin workspace, for example:

   ```bash
   mkdir -p ~/catkin_ws/src
   cd ~/catkin_ws/src
   git clone git@github.com:xianzeYao/lego.git
   ```

4. Expose the vendored ROS packages to the workspace. The practical options are:

   ```bash
   ln -s ~/catkin_ws/src/lego/APEX-MR ~/catkin_ws/src/apex_mr
   ln -s ~/catkin_ws/src/lego/Robot_Digital_Twin/gazebo ~/catkin_ws/src/robot_digital_twin
   ln -s ~/catkin_ws/src/lego/Robot_Digital_Twin/moveit_config ~/catkin_ws/src/dual_gp4_moveit_config
   ```

5. Build:

   ```bash
   cd ~/catkin_ws
   catkin build
   source devel/setup.bash
   ```

6. Run a small APEX-MR task:

   ```bash
   roslaunch apex_mr lego_assign.launch task:=cliff
   roslaunch apex_mr lego.launch task:=cliff
   ```

## Option B: Isaac Sim / BrickSim Direction

Use this if the goal is to reproduce the single-arm LEGO manipulation path.

1. Install NVIDIA driver and verify:

   ```bash
   nvidia-smi
   ```

2. Install Isaac Sim according to the BrickSim-supported version.
3. Install BrickSim and run its official demo first.
4. Import the RM75 arm and modified tool from:

   ```text
   Attempt/RM75_gripper/
   Attempt/lego_test_open_fixed.stl
   ```

5. Verify these in order:

   - Robot URDF imports and all joints move.
   - Modified tool is attached to the flange.
   - Tool TCP frames are visible and correct.
   - One LEGO brick can be spawned at a known pose.
   - One pick-place-press cycle works with attach/detach or BrickSim constraints.

6. Follow the detailed checklist:

   ```text
   Attempt/docs/isaac_bricksim_lego_migration_checklist.md
   ```

## First Target

The first useful target is not full automatic LEGO assembly. It is:

```text
single RM75 arm + modified LEGO tool + one LEGO brick
pick -> lift -> place -> press -> release
```

Only scale to multiple bricks after the one-brick result is repeatable.
