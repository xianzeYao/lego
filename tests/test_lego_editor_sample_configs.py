import json
import unittest
from pathlib import Path

from maniskill_rm75_lego.lego_task_optimizer import (
    BRICK_SPECS,
    TaskBrick,
    optimize_order,
    plate_coverage,
    footprint,
)
from maniskill_rm75_lego.lego_task_parser import load_task_config_dir


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = REPO_ROOT / "config" / "lego_editor_samples"
DIFFICULTIES = ("easy", "middle", "hard")


class LegoEditorSampleConfigTest(unittest.TestCase):
    def test_sample_configs_are_parser_compatible_and_complete(self):
        for difficulty in DIFFICULTIES:
            with self.subTest(difficulty=difficulty):
                task = load_task_config_dir(SAMPLE_ROOT / difficulty)

                self.assertEqual(len(task.bricks), len(task.operations))
                self.assertGreater(len(task.bricks), 0)
                self.assertTrue(all(op.pick.grid is not None for op in task.operations))
                self.assertTrue(all(op.pick.press_side is not None for op in task.operations))
                self.assertTrue(all(op.pick.press_offset is not None for op in task.operations))
                self.assertTrue(all(op.place.grid is not None for op in task.operations))

    def test_sample_press_offsets_are_backend_compatible(self):
        for difficulty in DIFFICULTIES:
            with self.subTest(difficulty=difficulty):
                config_dir = SAMPLE_ROOT / difficulty
                with (config_dir / "settings.json").open("r") as f:
                    settings = json.load(f)
                with (config_dir / "task.json").open("r") as f:
                    task = json.load(f)
                type_by_id = {
                    str(entry["id"]): str(entry["type"])
                    for entry in settings["initial_bricks"]
                }

                for step in task["steps"]:
                    brick_type = type_by_id[str(step["object"])]
                    studs_x, studs_y = BRICK_SPECS[brick_type]
                    press_side = int(step["pick"]["press_side"])
                    stud_count = studs_y if press_side in (1, 4) else studs_x
                    press_offset = step["pick"]["press_offset"]
                    offsets = press_offset if isinstance(press_offset, list) else [press_offset]

                    self.assertIn(len(offsets), (1, 2))
                    if stud_count > 1:
                        self.assertEqual(len(offsets), 2)
                    self.assertTrue(all(0 <= int(offset) < stud_count for offset in offsets))
                    if len(offsets) == 2:
                        self.assertEqual(abs(int(offsets[0]) - int(offsets[1])), 1)

    def test_sample_task_pick_grids_match_settings_and_place_grids_match_steps(self):
        for difficulty in DIFFICULTIES:
            with self.subTest(difficulty=difficulty):
                config_dir = SAMPLE_ROOT / difficulty
                with (config_dir / "settings.json").open("r") as f:
                    settings = json.load(f)
                with (config_dir / "task.json").open("r") as f:
                    task = json.load(f)

                settings_by_id = {
                    str(entry["id"]): entry
                    for entry in settings["initial_bricks"]
                }
                step_ids = [str(step["object"]) for step in task["steps"]]

                self.assertEqual(set(step_ids), set(settings_by_id))
                for step in task["steps"]:
                    brick_id = str(step["object"])
                    self.assertEqual(step["pick"]["grid"], settings_by_id[brick_id]["grid"])
                    self.assertEqual(len(step["place"]["grid"]), 4)

    def test_sample_settings_follow_staging_rules(self):
        for difficulty in DIFFICULTIES:
            with self.subTest(difficulty=difficulty):
                config_dir = SAMPLE_ROOT / difficulty
                with (config_dir / "settings.json").open("r") as f:
                    settings = json.load(f)
                plate_size = tuple(settings["plate"]["plate_size_xy"])
                occupied: set[tuple[int, int, int]] = set()
                seen_types: set[str] = set()
                closed_types: set[str] = set()

                for entry in settings["initial_bricks"]:
                    brick_type = str(entry["type"])
                    grid = list(entry["grid"])

                    self.assertIn(brick_type, BRICK_SPECS)
                    self.assertLessEqual(grid[2], 4)
                    self.assertGreaterEqual(plate_coverage(brick_type, grid, plate_size), 0.8)
                    self.assertNotIn(brick_type, closed_types)
                    for seen_type in seen_types:
                        if seen_type != brick_type:
                            closed_types.add(seen_type)
                    seen_types.add(brick_type)

                    for key in footprint(brick_type, grid):
                        x, y, _ = key
                        if 0 <= x < plate_size[0] and 0 <= y < plate_size[1]:
                            self.assertNotIn(key, occupied)
                            occupied.add(key)

    def test_sample_task_order_matches_backend_build_order(self):
        for difficulty in DIFFICULTIES:
            with self.subTest(difficulty=difficulty):
                config_dir = SAMPLE_ROOT / difficulty
                with (config_dir / "settings.json").open("r") as f:
                    settings = json.load(f)
                with (config_dir / "task.json").open("r") as f:
                    task = json.load(f)
                type_by_id = {
                    str(entry["id"]): str(entry["type"])
                    for entry in settings["initial_bricks"]
                }
                original_order = [str(step["object"]) for step in task["steps"]]
                bricks = [
                    TaskBrick(
                        id=str(step["object"]),
                        type=type_by_id[str(step["object"])],
                        grid=list(step["place"]["grid"]),
                    )
                    for step in task["steps"]
                ]

                self.assertEqual(optimize_order(bricks, original_order), original_order)


if __name__ == "__main__":
    unittest.main()
