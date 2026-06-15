# RealMan LEGO Stepwise Pick-Place

This runner reuses the current ManiSkill LEGO stage-6 waypoint generation and sends the solved RM75 joint targets to the real robot one stage at a time.

Shadow/render dry run only, no hardware commands. By default this uses the current LEGO scene: plate top center at `(x=0.300, y=0.000, z=0.0032)`, pick `lego_1x4` from grid `(8, 6, 0, 0)`, and place it on top of the centered `lego_2x4` at grid `(14, 15, 1, 0)`.

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --plate-z-offset 0.0075 --press-depth 0.0 --place-press-depth 0.0 --twist-ik-steps 3 --render
```

Real robot, stepwise execution:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --execute-real --robot-ip <RM75_IP> --plate-z-offset 0.0075 --press-depth 0.0 --place-press-depth 0.0 --twist-ik-steps 3 --eef-log-hz 30
```

Real robot with synchronized shadow rendering:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --execute-real --robot-ip <RM75_IP> --plate-z-offset 0.0075 --press-depth 0.0 --place-press-depth 0.0 --twist-ik-steps 3 --eef-log-hz 30 --render
```

At each waypoint:

- Press `Enter` to execute that stage.
- Type `s` then `Enter` to skip the stage.
- Type `q` then `Enter` to abort before moving.

For real execution, the generated waypoint list includes `home_start` before the LEGO motion and `home_end` after it by default. These are still stepwise prompts, so the robot will not move until `Enter` is pressed for each one. Use `--no-include-home` or `--no-return-home` only for a controlled debug run where the robot is already at the intended start or end pose.

`--plate-z-offset` is the unified real-world height correction between the robot base frame and the LEGO plate top. The current command uses `0.0075` m and keeps `--press-depth` and `--place-press-depth` at `0.0`, so pick/place do not add separate extra pressing depth.

During real execution, `--eef-log-hz 30` records controller-reported EEF pose and joints to `outputs/realman_eef_logs/`. The CSV rows are tagged by waypoint stage, and the JSON summary reports per-stage `x/y/z` span plus XY deviation.

`--render` controls the local ManiSkill shadow window. `--execute-real` controls whether hardware commands are sent. `--dry-run-no-prompts` only skips the keyboard prompts; it still will not send hardware commands unless `--execute-real` is also set.
