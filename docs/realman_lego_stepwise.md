# RealMan LEGO Stepwise Pick-Place

This runner reuses the current ManiSkill LEGO stage-6 waypoint generation and sends the solved RM75 joint targets to the real robot one stage at a time.

Dry run only, no hardware commands:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --target-grid 14 13 1 0 --press-depth 0.0 --place-press-depth 0.0 --twist-ik-steps 3
```

Real robot, stepwise execution:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --execute-real --robot-ip <RM75_IP> --target-grid 14 13 1 0 --press-depth 0.0 --place-press-depth 0.0 --twist-ik-steps 3
```

At each waypoint:

- Press `Enter` to execute that stage.
- Type `s` then `Enter` to skip the stage.
- Type `q` then `Enter` to abort before moving.

The script does not send the home pose by default. Add `--include-home` only when the real robot is already in a known safe configuration for that first move.
