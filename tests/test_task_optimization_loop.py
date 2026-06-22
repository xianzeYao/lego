import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import io

from maniskill_rm75_lego.task_optimization_loop import (
    build_runner_command,
    count_pick_tool_clearance_records,
    count_place_exit_tool_clearance_records,
    count_press_down_tool_clearance_records,
    exhausted_pick_side_bricks,
    has_press_down_tool_clearance_records,
    increment_failed_pick_grid_counts,
    optimizer_history_from_task,
    pick_grids_from_task_planning,
    repeated_failed_pick_grid_bricks,
    run_optimization_loop,
)


class TaskOptimizationLoopTest(unittest.TestCase):
    def test_build_runner_command_enables_tool_collision_audit(self):
        command = build_runner_command(Path("cfg"), Path("collision.json"), ["--seed", "3"])

        self.assertEqual(command[command.index("--task-config") + 1], "cfg")
        self.assertIn("--audit-tool-collisions", command)
        self.assertIn("--collision-log", command)
        self.assertEqual(command[-2:], ["--seed", "3"])

    def test_detects_press_down_tool_clearance_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "collision.json"
            log_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {"kind": "brick_overlap", "stage": "initial"},
                            {"kind": "tool_clearance", "stage": "place_B001/place_down"},
                            {"kind": "tool_clearance", "stage": "place_B001/place_twist"},
                        ]
                    }
                )
            )

            self.assertTrue(has_press_down_tool_clearance_records(log_path))
            self.assertEqual(count_press_down_tool_clearance_records(log_path), 1)
            self.assertEqual(count_place_exit_tool_clearance_records(log_path), 1)
            self.assertEqual(count_pick_tool_clearance_records(log_path), 0)

    def test_detects_exhausted_pick_sides_after_press_forbidden_sides(self):
        exhausted = exhausted_pick_side_bricks(
            press_forbidden_history={"B001": {1}},
            pick_forbidden_history={"B001": {2, 3, 4}, "B002": {1, 2}},
            failed_pick_grids={
                "B001": {(8, 2, 0, 0)},
                "B002": {(8, 6, 0, 0)},
            },
        )

        self.assertEqual(exhausted, {"B001"})

    def test_detects_repeated_failed_pick_grid(self):
        counts = increment_failed_pick_grid_counts({}, {"B001": {(8, 2, 0, 0)}})
        counts = increment_failed_pick_grid_counts(counts, {"B001": {(8, 2, 0, 0)}, "B002": {(8, 6, 0, 0)}})

        self.assertEqual(repeated_failed_pick_grid_bricks(counts), {"B001"})

    def test_restores_optimizer_side_history_from_task_planning(self):
        press_history, pick_history = optimizer_history_from_task(
            {
                "steps": [
                    {
                        "object": "B001",
                        "planning": {
                            "optimizer": {
                                "forbidden_sides": [1, 2, 3],
                                "forbidden_press_sides": [1],
                                "discouraged_pick_sides": [2, 3],
                            }
                        },
                    }
                ]
            }
        )

        self.assertEqual(press_history, {"B001": {1}})
        self.assertEqual(pick_history, {"B001": {2, 3}})

    def test_restores_forbidden_pick_grids_from_task_planning(self):
        grids = pick_grids_from_task_planning(
            {
                "steps": [
                    {
                        "object": "B001",
                        "planning": {
                            "optimizer": {
                                "forbidden_pick_grids": [[8, 2, 0, 0], [7, 2, 0, 0]]
                            }
                        },
                    }
                ]
            }
        )

        self.assertEqual(grids, {"B001": {(8, 2, 0, 0), (7, 2, 0, 0)}})

    def test_place_exit_tool_clearance_writes_next_candidate_instead_of_converging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                collision_log = Path(command[command.index("--collision-log") + 1])
                collision_log.write_text(
                    json.dumps(
                        {
                            "records": [
                                {
                                    "kind": "tool_clearance",
                                    "stage": "place_B001/place_twist",
                                    "a": "tool",
                                    "b": "B999",
                                }
                            ]
                        }
                    )
                )

                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=2,
                )

            self.assertEqual(final_dir, output_dir / "final")
            self.assertTrue((output_dir / "candidate_01").exists())
            task = json.loads((final_dir / "task.json").read_text())
            self.assertNotEqual(task["steps"][0]["pick"]["press_side"], 1)
            summary = json.loads((output_dir / "optimization_summary.json").read_text())
            self.assertFalse(summary["converged"])
            self.assertEqual(summary["final_dir"], str(final_dir))
            self.assertEqual(summary["iterations"][0]["press_down_tool_clearance_records"], 0)
            self.assertEqual(summary["iterations"][0]["pick_tool_clearance_records"], 0)
            self.assertEqual(summary["iterations"][0]["place_exit_tool_clearance_records"], 1)

    def test_pick_tool_clearance_writes_next_candidate_instead_of_converging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                collision_log = Path(command[command.index("--collision-log") + 1])
                collision_log.write_text(
                    json.dumps(
                        {
                            "records": [
                                {
                                    "kind": "tool_clearance",
                                    "stage": "place_B001/pre_pick",
                                    "a": "tool",
                                    "b": "B999",
                                }
                            ]
                        }
                    )
                )

                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=1,
                )

            self.assertEqual(final_dir, output_dir / "final")
            self.assertTrue((output_dir / "candidate_01").exists())
            task = json.loads((final_dir / "task.json").read_text())
            settings = json.loads((final_dir / "settings.json").read_text())
            self.assertEqual(settings["initial_bricks"][0]["grid"], [8, 2, 0, 0])
            self.assertEqual(task["steps"][0]["pick"]["grid"], [8, 2, 0, 0])
            self.assertNotEqual(task["steps"][0]["pick"]["press_side"], 1)
            self.assertEqual(task["steps"][0]["planning"]["optimizer"]["forbidden_sides"], [1])
            summary = json.loads((output_dir / "optimization_summary.json").read_text())
            self.assertFalse(summary["converged"])
            self.assertEqual(summary["iterations"][0]["pick_tool_clearance_records"], 1)

    def test_loop_restages_repeated_pick_grid_before_all_sides_are_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                collision_log = Path(command[command.index("--collision-log") + 1])
                collision_log.write_text(
                    json.dumps(
                        {
                            "records": [
                                {
                                    "kind": "tool_clearance",
                                    "stage": "place_B001/pre_pick",
                                    "a": "tool",
                                    "b": "B999",
                                }
                            ]
                        }
                    )
                )

                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=2,
                )

            task = json.loads((final_dir / "task.json").read_text())
            summary = json.loads((output_dir / "optimization_summary.json").read_text())
            self.assertNotEqual(task["steps"][0]["pick"]["grid"], [8, 2, 0, 0])
            self.assertEqual(
                task["steps"][0]["planning"]["optimizer"]["forbidden_sides"],
                [1, 2],
            )
            self.assertIn([8, 2, 0, 0], summary["iterations"][1]["forbidden_pick_grids"]["B001"])
            self.assertIn("B001", summary["iterations"][1]["exhausted_restage_brick_ids"])

    def test_loop_restages_pick_grid_after_pick_sides_are_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                collision_log = Path(command[command.index("--collision-log") + 1])
                collision_log.write_text(
                    json.dumps(
                        {
                            "records": [
                                {
                                    "kind": "tool_clearance",
                                    "stage": "place_B001/pre_pick",
                                    "a": "tool",
                                    "b": "B999",
                                }
                            ]
                        }
                    )
                )

                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=5,
                )

            task = json.loads((final_dir / "task.json").read_text())
            settings = json.loads((final_dir / "settings.json").read_text())
            summary = json.loads((output_dir / "optimization_summary.json").read_text())
            self.assertNotEqual(task["steps"][0]["pick"]["grid"], [8, 2, 0, 0])
            self.assertEqual(settings["initial_bricks"][0]["grid"], task["steps"][0]["pick"]["grid"])
            self.assertIn([8, 2, 0, 0], summary["iterations"][4]["forbidden_pick_grids"]["B001"])

    def test_loop_uses_collision_log_to_write_next_candidate_after_runner_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                collision_log = Path(command[command.index("--collision-log") + 1])
                collision_log.write_text(
                    json.dumps(
                        {
                            "records": [
                                {
                                    "kind": "tool_clearance",
                                    "stage": "place_B001/place_down",
                                    "a": "tool",
                                    "b": "B999",
                                }
                            ]
                        }
                    )
                )

                class Result:
                    returncode = 1
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run), patch("sys.stderr", new=io.StringIO()):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=1,
                )

            task = json.loads((final_dir / "task.json").read_text())
            self.assertNotEqual(task["steps"][0]["pick"]["press_side"], 1)
            summary = json.loads((output_dir / "optimization_summary.json").read_text())
            self.assertFalse(summary["converged"])
            self.assertEqual(summary["final_dir"], str(final_dir))
            self.assertEqual(summary["iterations"][0]["press_down_tool_clearance_records"], 1)

    def test_loop_defers_pick_restage_until_press_down_is_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                collision_log = Path(command[command.index("--collision-log") + 1])
                collision_log.write_text(
                    json.dumps(
                        {
                            "records": [
                                {"kind": "tool_clearance", "stage": "place_B001/place_down", "a": "tool", "b": "B999"},
                                {"kind": "tool_clearance", "stage": "place_B001/pre_pick", "a": "tool", "b": "B999"},
                            ]
                        }
                    )
                )

                class Result:
                    returncode = 1
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=1,
                )

            task = json.loads((final_dir / "task.json").read_text())
            settings = json.loads((final_dir / "settings.json").read_text())
            summary = json.loads((output_dir / "optimization_summary.json").read_text())
            self.assertEqual(settings["initial_bricks"][0]["grid"], [8, 2, 0, 0])
            self.assertEqual(task["steps"][0]["pick"]["grid"], [8, 2, 0, 0])
            self.assertNotEqual(task["steps"][0]["pick"]["press_side"], 1)
            self.assertEqual(summary["iterations"][0]["forbidden_pick_grids"], {})

    def test_loop_uses_ik_failure_log_without_collision_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                class Result:
                    returncode = 1
                    stdout = ""
                    stderr = "RuntimeError: IK failed for place_B001/pick_down: err=[0.1, 0.2]"

                return Result()

            with patch("subprocess.run", side_effect=fake_run), patch("sys.stderr", new=io.StringIO()):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=1,
                )

            task = json.loads((final_dir / "task.json").read_text())
            settings = json.loads((final_dir / "settings.json").read_text())
            self.assertEqual(settings["initial_bricks"][0]["grid"], [8, 2, 0, 0])
            self.assertEqual(settings["initial_bricks"][0]["grid"], task["steps"][0]["pick"]["grid"])
            self.assertNotEqual(task["steps"][0]["pick"]["press_side"], 1)

    def test_loop_accumulates_forbidden_sides_across_iterations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                config = Path(command[command.index("--task-config") + 1])
                side = json.loads((config / "task.json").read_text())["steps"][0]["pick"]["press_side"]
                collision_log = Path(command[command.index("--collision-log") + 1])
                collision_log.write_text(
                    json.dumps(
                        {
                            "records": [
                                {
                                    "kind": "tool_clearance",
                                    "stage": "place_B001/place_down",
                                    "a": "tool",
                                    "b": f"side_{side}",
                                }
                            ]
                        }
                    )
                )

                class Result:
                    returncode = 1
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=2,
                )

            task = json.loads((final_dir / "task.json").read_text())
            self.assertNotIn(task["steps"][0]["pick"]["press_side"], {1, 2})
            self.assertEqual(
                task["steps"][0]["planning"]["optimizer"]["forbidden_sides"],
                [1, 2],
            )

    def test_loop_keeps_best_audited_candidate_with_press_down_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]}
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            }
                        ],
                    }
                )
            )

            calls = 0

            def fake_run(command, cwd, capture_output, text):
                nonlocal calls
                collision_log = Path(command[command.index("--collision-log") + 1])
                records = [
                    {"kind": "tool_clearance", "stage": "place_B001/pre_pick", "a": "tool", "b": "B999"}
                ]
                if calls == 1:
                    records = [
                        {"kind": "tool_clearance", "stage": "place_B001/place_down", "a": "tool", "b": "B999"}
                    ]
                collision_log.write_text(json.dumps({"records": records}))
                calls += 1

                class Result:
                    returncode = 1
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=2,
                )

            summary = json.loads((output_dir / "optimization_summary.json").read_text())
            self.assertEqual(final_dir, output_dir / "final")
            self.assertEqual(summary["best_dir"], str(output_dir / "best"))
            self.assertEqual(summary["best_iteration"], 0)
            self.assertEqual(summary["best_score"][:2], [0, 1])
            best_task = json.loads((output_dir / "best" / "task.json").read_text())
            final_task = json.loads((output_dir / "final" / "task.json").read_text())
            self.assertNotEqual(best_task["steps"][0]["pick"]["press_side"], final_task["steps"][0]["pick"]["press_side"])

    def test_loop_restages_exhausted_pick_side_even_while_other_brick_learns_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "input"
            output_dir = root / "out"
            config_dir.mkdir()
            (config_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "plate": {"plate_size_xy": [48, 48]},
                        "initial_bricks": [
                            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0], "color": [0.8, 0.1, 0.1, 1]},
                            {"id": "B002", "type": "lego_2x4", "grid": [8, 6, 0, 0], "color": [0.1, 0.1, 0.8, 1]},
                        ],
                    }
                )
            )
            (config_dir / "task.json").write_text(
                json.dumps(
                    {
                        "name": "loop_test",
                        "steps": [
                            {
                                "name": "place_B001",
                                "object": "B001",
                                "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [12, 10, 0, 0]},
                            },
                            {
                                "name": "place_B002",
                                "object": "B002",
                                "pick": {"grid": [8, 6, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                                "place": {"grid": [20, 10, 0, 0]},
                            },
                        ],
                    }
                )
            )

            def fake_run(command, cwd, capture_output, text):
                config = Path(command[command.index("--task-config") + 1])
                task = json.loads((config / "task.json").read_text())
                side_by_id = {step["object"]: step["pick"]["press_side"] for step in task["steps"]}
                collision_log = Path(command[command.index("--collision-log") + 1])
                records = [
                    {
                        "kind": "tool_clearance",
                        "stage": "place_B001/pre_pick",
                        "a": "tool",
                        "b": f"side_{side_by_id['B001']}",
                    },
                    {
                        "kind": "tool_clearance",
                        "stage": "place_B002/pre_pick",
                        "a": "tool",
                        "b": f"side_{side_by_id['B002']}",
                    },
                ]
                collision_log.write_text(json.dumps({"records": records}))

                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return Result()

            with patch("subprocess.run", side_effect=fake_run):
                final_dir = run_optimization_loop(
                    config_dir=config_dir,
                    output_dir=output_dir,
                    iterations=4,
                )

            task = json.loads((final_dir / "task.json").read_text())
            settings = json.loads((final_dir / "settings.json").read_text())
            summary = json.loads((output_dir / "optimization_summary.json").read_text())
            b001_pick = next(step for step in task["steps"] if step["object"] == "B001")["pick"]["grid"]
            b001_setting = next(entry for entry in settings["initial_bricks"] if entry["id"] == "B001")["grid"]

            self.assertNotEqual(b001_pick, [8, 2, 0, 0])
            self.assertEqual(b001_pick, b001_setting)
            self.assertIn("B001", summary["iterations"][3]["exhausted_restage_brick_ids"])


if __name__ == "__main__":
    unittest.main()
