# RealMan LEGO Stepwise Pick-Place

This runner reuses the current ManiSkill LEGO stage-6 waypoint generation and sends the solved RM75 joint targets to the real robot one stage at a time.

Shadow/render dry run only, no hardware commands. By default this uses the current LEGO scene: plate top center at `(x=0.300, y=0.000, z=0.0032)`, pick `lego_1x4` from grid `(2, 2, 0, 0)`, and place it on top of the `lego_2x4` at grid `(25, 28, 1, 0)`.

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --press-depth 0.0 --place-press-depth 0.0 --twist-ik-steps 3 --render
```

Real robot, stepwise execution:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --execute-real --robot-ip <RM75_IP> --press-depth 0.0 --place-press-depth 0.0 --twist-ik-steps 3
```

Real robot with synchronized shadow rendering:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --execute-real --robot-ip <RM75_IP> --press-depth 0.0 --place-press-depth 0.0 --twist-ik-steps 3 --render
```

At each waypoint:

- Press `Enter` to execute that stage.
- Type `s` then `Enter` to skip the stage.
- Type `q` then `Enter` to abort before moving.

For real execution, the generated waypoint list includes `home_start` before the LEGO motion and `home_end` after it by default. These are still stepwise prompts, so the robot will not move until `Enter` is pressed for each one. Use `--no-include-home` or `--no-return-home` only for a controlled debug run where the robot is already at the intended start or end pose.

`--render` controls the local ManiSkill shadow window. `--execute-real` controls whether hardware commands are sent. `--dry-run-no-prompts` only skips the keyboard prompts; it still will not send hardware commands unless `--execute-real` is also set.
