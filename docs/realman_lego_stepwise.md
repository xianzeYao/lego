# RealMan LEGO Stepwise Pick-Place

This runner reuses the current ManiSkill LEGO stage-6 waypoint generation and sends the solved RM75 joint targets to the real robot one stage at a time.

Shadow/render dry run only, no hardware commands. By default this uses the current LEGO scene: plate top center at `(x=0.300, y=0.000, z=0.0032)`, pick `lego_1x4` from grid `(8, 6, 0, 0)`, and place it on top of the centered `lego_2x4` at grid `(14, 15, 1, 0)`.

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --plate-z-offset 0.008 --press-depth 0.012 --place-press-depth 0.012 --render
```

Real robot, stepwise execution:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --execute-real --robot-ip <RM75_IP> --plate-z-offset 0.008 --press-depth 0.012 --place-press-depth 0.012 --eef-log-hz 30
```

Real robot with synchronized shadow rendering:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_realman_lego_pick_place_stepwise.py --execute-real --robot-ip 192.168.101.20 --plate-z-offset 0.008 --press-depth 0.012 --place-press-depth 0.012 --render
```

Task-ladder config run, simulation/shadow rendering only. The plate height correction is passed explicitly with `--plate-z-offset`:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_task_ladder_robot_preview.py --task-config config/ladder --plate-z-offset 0.008 --pick-press-depth 0.012 --place-press-depth 0.012 --render
```

Task-ladder config run on the real robot, with synchronized shadow rendering:

```bash
/home/yxz/data/conda/envs/maniskill4lego/bin/python maniskill_rm75_lego/scripts/run_task_ladder_robot_preview.py --task-config config/ladder --execute-real --robot-ip 192.168.101.20 --plate-z-offset 0.008 --pick-press-depth 0.012 --place-press-depth 0.012 --render --step
```

For the task-ladder runner, stages run continuously by default. Add `--step` to pause before each stage:

- Press `Enter` to execute that stage.
- Type `s` then `Enter` to skip the stage.
- Type `q` then `Enter` to abort before moving.

For task-ladder real execution, the generated motion includes `home` before the LEGO motion and `home_end` after it. By default it runs continuously. Add `--step` when you want an Enter prompt before each stage.

`--plate-z-offset` is the unified real-world height correction between the robot base frame and the LEGO plate top. It is passed from the command line for both the single-stage and ladder scripts. The ladder command sets `--pick-press-depth` and `--place-press-depth` to `0.012` m from the command line. The older `--press-depth` spelling is still accepted by the ladder script as an alias for `--pick-press-depth`.

The pick twist IK subdivision is fixed at `1` for the real-tested LEGO motion and is no longer exposed as a command-line parameter.

Short Cartesian primitives are densified before execution. For stages such as `pick_down`, `pick_attach`, `pick_upright`, `drop_up`, `place_down`, `place_press`, and `place_up`, the script samples intermediate TCP/contact poses at up to `--cartesian-step-size` spacing, solves IK for each sample, and executes the resulting joint subpath under one stage prompt. Set `--cartesian-step-size <= 0` to disable this densification.

For the task-ladder runner, real execution streams the generated dense joint path directly through `realman_step_runner.py`. It bypasses the third-party `move_linear()` interpolation and only applies adjacent-joint max-delta densification before calling the RealMan `send_action` stream.

For the legacy single-stage runner, `--eef-log-hz 30` records controller-reported EEF pose and joints to `outputs/realman_eef_logs/`. The task-ladder runner does not expose EEF logging yet.

`--render` controls the local ManiSkill shadow window. `--execute-real` controls whether hardware commands are sent. For the legacy stage-6 runner, `--dry-run-no-prompts` skips keyboard prompts; for the task-ladder runner, use `--step` only when you want keyboard prompts.
