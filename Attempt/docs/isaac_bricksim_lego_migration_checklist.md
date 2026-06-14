# Isaac Sim / BrickSim LEGO Manipulation Checklist

This checklist is for migrating or reproducing the APEX-MR LEGO manipulation setup in Isaac Sim / BrickSim with a single robot arm and a custom LEGO tool.

## 0. Repository Context

- [x] Downloaded `Robot_Digital_Twin` at `apexmr-release`.
- [x] Downloaded `BrickSim` at `cbd5de3238e6ac12f44ef699e1507a9f16bdafc3`.
- [x] Confirmed APEX-MR uses external `Robot_Digital_Twin` for GP4 URDF/xacro and MoveIt config.
- [x] Confirmed local APEX-MR stores tool-frame variants as DH files, not URDF links.
- [x] Confirmed `Robot_Digital_Twin` contains EOAT meshes, LEGO meshes, GP4 xacro, Gazebo launch files, and MoveIt SRDF.
- [x] Confirmed `BrickSim` contains Isaac Sim demos, Python API, native extension code, and brick simulation resources.

## 1. Robot Model

- [ ] Identify the exact robot arm to use in Isaac Sim.
- [ ] Confirm URDF imports without missing mesh paths.
- [ ] Confirm all joint axes match the real robot.
- [ ] Confirm joint limits match the real controller.
- [ ] Confirm base frame and world frame conventions.
- [ ] Confirm visual mesh scale.
- [ ] Confirm collision mesh scale.
- [ ] Use simplified collision meshes where possible.
- [ ] Verify forward kinematics against known calibration poses.
- [ ] Verify the imported articulation can be commanded in Isaac Sim.

## 2. LEGO Tool / EOAT Model

APEX-MR's digital twin has a real URDF tool link:

- `link_tool` / `${arm_id}_link_tool`
- attached through `fts_tool` / `${arm_id}_fts_tool`
- mesh: `gazebo/meshes/eoat/tool.stl`

Check these before using it in Isaac Sim:

- [ ] Confirm whether your custom STL is the same as `tool.stl` or a newer version.
- [ ] Confirm STL units: meters vs millimeters.
- [ ] Confirm tool origin matches the robot flange convention.
- [ ] Confirm tool mesh orientation after URDF/USD import.
- [ ] Confirm collision mesh does not over-approximate the LEGO contact area too much.
- [ ] Add explicit frame markers for:
  - [ ] flange frame
  - [ ] F/T sensor frame
  - [ ] tool body frame
  - [ ] assemble TCP
  - [ ] disassemble TCP
  - [ ] alt/place-up TCP
  - [ ] press TCP

## 3. APEX-MR Tool-Frame Variants To Preserve

APEX-MR does not treat the tool as a single TCP. It uses several tool-frame variants:

- `gp4_tool_DH.txt`: nominal tool frame.
- `gp4_tool_assemble_DH.txt`: place/assembly contact frame.
- `gp4_tool_disassemble_DH.txt`: pick/disassembly contact frame.
- `gp4_tool_alt_DH.txt`: alternate side/up manipulation frame.
- `gp4_tool_alt_assemble_DH.txt`: alternate assembly frame.
- `gp4_tool_handover_assemble_DH.txt`: handover assembly frame.

For Isaac Sim:

- [ ] Convert each DH variant into an explicit transform relative to the imported tool frame.
- [ ] Create debug axes or small marker frames for each variant.
- [ ] Check that `assemble` and `disassemble` TCPs differ by the expected offset.
- [ ] Check that `alt` frame matches the side/place-up maneuver.
- [ ] Check that press direction is correct for each TCP.
- [ ] Run a visual overlay: APEX-MR TCP pose vs Isaac Sim TCP pose for the same joint angles.

## 4. LEGO Assets

Robot_Digital_Twin includes LEGO STL meshes:

- `b1x1`, `b1x2`, `b1x4`, `b1x6`, `b1x8`
- `b2x2`, `b2x4`, `b2x6`, `b2x8`
- `base32x32`, `base48x48`

Check:

- [ ] Confirm LEGO mesh units are correct after import.
- [ ] Confirm stud pitch is 8 mm.
- [ ] Confirm brick height is 9.6 mm.
- [ ] Confirm baseplate coordinate origin.
- [ ] Confirm brick top-left / center conversion.
- [ ] Confirm orientation convention: `ori=0/1` or degrees.
- [ ] Decide whether first version uses simple rigid STL or BrickSim interlocking bricks.
- [ ] If using BrickSim interlocking:
  - [ ] Define stud/cavity/topology metadata.
  - [ ] Confirm snap-fit creates expected constraints.
  - [ ] Confirm detach/disassembly thresholds.

## 5. Single-Brick Manipulation Primitive

Minimum primitive:

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

Check:

- [ ] Approach pose is collision-free.
- [ ] Pick TCP aligns with LEGO grip/contact feature.
- [ ] Attach transform keeps LEGO fixed relative to tool.
- [ ] Lift motion does not hit studs or neighbors.
- [ ] Place pose aligns to target studs.
- [ ] Press distance is small and controlled.
- [ ] Release does not create a sudden impulse.
- [ ] Retraction direction clears the LEGO.

## 6. APEX-MR Action Ideas To Reproduce

APEX-MR's useful manipulation ideas:

- [ ] `pick_down`: lower until contact, then twist using disassembly TCP.
- [ ] `pick_twist`: rotate around a tool-local axis to loosen/engage.
- [ ] `drop_down`: lower until contact, then twist using assembly TCP.
- [ ] `drop_twist`: opposite twist direction from picking.
- [ ] `place_up`: alternate upward/side insertion mode.
- [ ] `press_down`: press with force/contact feedback.
- [ ] `support`: use another contact to stabilize a structure. For single-arm work, this can become passive fixture/support.
- [ ] `handover`: not needed for the first single-arm version.

For single-arm Isaac Sim, start with:

- [ ] `pick_down`
- [ ] `pick_twist`
- [ ] `drop_down`
- [ ] `drop_twist`
- [ ] `press_down`

Defer:

- [ ] dual-arm support
- [ ] handover
- [ ] asynchronous TPG/ADG

## 7. Force / Contact Feedback

APEX-MR uses F/T feedback thresholds:

- z-force threshold for pick/drop.
- x-force threshold for place-up.
- lower velocity for contact-rich moves.
- stop command once force threshold is reached.

In Isaac Sim / BrickSim:

- [ ] Decide whether to use simulated force sensor, contact sensor, or BrickSim connection event.
- [ ] Add a sensor or contact monitor at the tool/LEGO interface.
- [ ] Record baseline force before contact move.
- [ ] Stop descending when force/contact threshold is reached.
- [ ] Use very low speed for contact moves.
- [ ] Log force/contact traces for debugging.
- [ ] Verify press does not tunnel through the LEGO.

## 8. Motion Generation

Start simple:

- [ ] Hand-written joint waypoints.
- [ ] Hand-written Cartesian waypoints.
- [ ] No global planning for the first 1-brick test.

Then improve:

- [ ] Add IK solver for target TCP poses.
- [ ] Add collision checking.
- [ ] Add RMPflow/Lula only after basic frames are correct.
- [ ] Add MoveIt2 or external planner only if local waypoints are insufficient.

## 9. BrickSim-Specific Validation

- [ ] Run official BrickSim `demo_assembly.py` unchanged.
- [ ] Confirm Isaac Sim version and Python version match BrickSim requirements.
- [ ] Confirm your GPU can run the scene at low resolution.
- [ ] Confirm BrickSim can load custom brick or existing brick assets.
- [ ] Confirm connection is detected after press.
- [ ] Confirm breakage/collapse detection works on a small stacked example.
- [ ] Confirm reset/replay works.

## 10. Minimum Milestones

### M1: Environment

- [ ] Isaac Sim starts.
- [ ] BrickSim official demo runs.
- [ ] Empty scene can load your robot.

### M2: Robot + Tool

- [ ] Robot moves in Isaac Sim.
- [ ] Tool is attached to the flange.
- [ ] TCP marker positions are visually correct.

### M3: One Brick

- [ ] One LEGO brick is spawned at a known pose.
- [ ] Robot picks it using attach or constraint.
- [ ] Robot places it at a target pose.
- [ ] Robot presses and releases without instability.

### M4: Two Bricks

- [ ] First brick is placed.
- [ ] Second brick aligns on top.
- [ ] BrickSim or contact logic reports connection.

### M5: Instruction JSON

- [ ] Define a small instruction JSON.
- [ ] Execute steps sequentially.
- [ ] Save final scene state.
- [ ] Compare final brick poses against target poses.

## 11. Stop Criteria Before Scaling

Do not scale to many bricks until these are true:

- [ ] Tool TCP is verified against real or known APEX-MR poses.
- [ ] Contact move stops reliably.
- [ ] One-brick placement repeatability is acceptable.
- [ ] Two-brick stacking is stable.
- [ ] Reset is deterministic.
- [ ] Logs include target pose, actual pose, contact status, and final error.
