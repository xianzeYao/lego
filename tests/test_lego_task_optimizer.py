import unittest

from maniskill_rm75_lego.lego_task_optimizer import (
    TaskBrick,
    choose_press,
    expanded_footprint_keys_2d,
    failed_pick_bricks_from_collision_log,
    failed_pick_grids_from_collision_log,
    failed_pick_bricks_from_failure_text,
    failed_pick_grids_from_failure_text,
    forbidden_sides_from_collision_log,
    forbidden_sides_from_place_exit_collision_log,
    forbidden_sides_from_pick_collision_log,
    forbidden_sides_from_failure_text,
    footprint,
    optimize_task,
    place_order_hints_from_collision_log,
    restage_failed_pick_bricks,
)


def settings():
    return {
        "name": "optimizer_test",
        "plate": {"plate_size_xy": [48, 48]},
        "initial_bricks": [
            {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0]},
            {"id": "B002", "type": "lego_2x4", "grid": [3, 2, 0, 0]},
            {"id": "B003", "type": "lego_2x4", "grid": [8, 6, 0, 0]},
        ],
    }


class LegoTaskOptimizerTest(unittest.TestCase):
    def test_orders_lower_layers_and_same_layer_x_first(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {"name": "place_B003", "object": "B003", "pick": {"grid": [8, 6, 0, 0]}, "place": {"grid": [11, 10, 1, 0]}},
                {"name": "place_B001", "object": "B001", "pick": {"grid": [8, 2, 0, 0]}, "place": {"grid": [12, 10, 0, 0]}},
                {"name": "place_B002", "object": "B002", "pick": {"grid": [3, 2, 0, 0]}, "place": {"grid": [4, 10, 0, 0]}},
            ],
        }

        optimized = optimize_task(settings(), task)

        self.assertEqual([step["object"] for step in optimized["steps"]], ["B002", "B001", "B003"])
        self.assertEqual(
            [step["place"]["grid"] for step in optimized["steps"]],
            [[4, 10, 0, 0], [12, 10, 0, 0], [11, 10, 1, 0]],
        )

    def test_place_collision_hints_can_pull_target_before_blocker(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {"name": "place_B001", "object": "B001", "pick": {"grid": [8, 2, 0, 0]}, "place": {"grid": [12, 10, 0, 0]}},
                {"name": "place_B002", "object": "B002", "pick": {"grid": [3, 2, 0, 0]}, "place": {"grid": [4, 10, 0, 0]}},
                {"name": "place_B003", "object": "B003", "pick": {"grid": [8, 6, 0, 0]}, "place": {"grid": [30, 10, 0, 0]}},
            ],
        }
        collision_log = {
            "records": [
                {"kind": "tool_clearance", "stage": "place_B003/place_down", "a": "tool", "b": "B002"},
            ]
        }

        hints = place_order_hints_from_collision_log(task, collision_log)
        optimized = optimize_task(settings(), task, preferred_before_by_brick=hints)

        self.assertEqual(hints, {"B003": {"B002"}})
        self.assertEqual([step["object"] for step in optimized["steps"]], ["B003", "B002", "B001"])
        self.assertEqual(
            optimized["steps"][0]["planning"]["optimizer"]["preferred_before"],
            ["B002"],
        )

    def test_place_collision_hints_do_not_override_support_dependencies(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {"name": "place_B001", "object": "B001", "pick": {"grid": [8, 2, 0, 0]}, "place": {"grid": [12, 10, 0, 0]}},
                {"name": "place_B002", "object": "B002", "pick": {"grid": [3, 2, 0, 0]}, "place": {"grid": [4, 10, 0, 0]}},
                {"name": "place_B003", "object": "B003", "pick": {"grid": [8, 6, 0, 0]}, "place": {"grid": [4, 10, 1, 0]}},
            ],
        }
        collision_log = {
            "records": [
                {"kind": "tool_clearance", "stage": "place_B003/place_down", "a": "tool", "b": "B002"},
            ]
        }

        optimized = optimize_task(
            settings(),
            task,
            preferred_before_by_brick=place_order_hints_from_collision_log(task, collision_log),
        )

        self.assertLess(
            [step["object"] for step in optimized["steps"]].index("B002"),
            [step["object"] for step in optimized["steps"]].index("B003"),
        )

    def test_selects_non_x_positive_side_when_x_positive_clearance_leaves_plate(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {"name": "place_B001", "object": "B001", "pick": {"grid": [8, 2, 0, 0]}, "place": {"grid": [44, 10, 0, 0]}},
            ],
        }

        optimized = optimize_task(settings(), task)

        self.assertNotEqual(optimized["steps"][0]["pick"]["press_side"], 1)
        self.assertEqual(optimized["steps"][0]["planning"]["press_strategy"], "optimizer_candidate")

    def test_lower_layer_side_brick_blocks_tool_long_edge_but_direct_support_does_not(self):
        task_settings = {
            "name": "optimizer_test",
            "plate": {"plate_size_xy": [48, 48]},
            "initial_bricks": [
                {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0]},
                {"id": "B002", "type": "lego_2x2", "grid": [8, 6, 0, 0]},
                {"id": "B003", "type": "lego_2x2", "grid": [8, 10, 0, 0]},
            ],
        }
        task = {
            "name": "optimizer_test",
            "steps": [
                {"name": "place_B001", "object": "B001", "pick": {"grid": [8, 2, 0, 0]}, "place": {"grid": [18, 18, 0, 0]}},
                {"name": "place_B002", "object": "B002", "pick": {"grid": [8, 6, 0, 0]}, "place": {"grid": [21, 20, 0, 0]}},
                {"name": "place_B003", "object": "B003", "pick": {"grid": [8, 10, 0, 0]}, "place": {"grid": [19, 18, 1, 0]}},
            ],
        }

        optimized = optimize_task(task_settings, task)

        self.assertNotEqual(optimized["steps"][2]["pick"]["press_side"], 1)

    def test_keeps_preferred_side_with_backend_compatible_offset(self):
        task_settings = {
            "name": "optimizer_test",
            "plate": {"plate_size_xy": [48, 48]},
            "initial_bricks": [
                {"id": "B001", "type": "lego_2x4", "grid": [8, 2, 0, 0]},
                {"id": "B002", "type": "lego_1x1", "grid": [8, 6, 0, 0]},
                {"id": "B003", "type": "lego_2x8", "grid": [8, 10, 0, 1]},
            ],
        }
        task = {
            "name": "optimizer_test",
            "steps": [
                {"name": "place_B001", "object": "B001", "pick": {"grid": [8, 2, 0, 0]}, "place": {"grid": [19, 18, 0, 0]}},
                {"name": "place_B002", "object": "B002", "pick": {"grid": [8, 6, 0, 0]}, "place": {"grid": [21, 21, 0, 0]}},
                {"name": "place_B003", "object": "B003", "pick": {"grid": [8, 10, 0, 1]}, "place": {"grid": [19, 18, 1, 1]}},
            ],
        }

        optimized = optimize_task(task_settings, task)

        self.assertEqual(optimized["steps"][2]["pick"]["press_side"], 1)
        self.assertEqual(optimized["steps"][2]["pick"]["press_offset"], [0, 1])

    def test_discouraged_pick_side_does_not_override_place_down_clearance(self):
        brick = TaskBrick("B004", "lego_2x2", [10, 10, 0, 0])
        placed = [
            TaskBrick("B001", "lego_1x1", [8, 10, 0, 0]),
            TaskBrick("B002", "lego_1x1", [10, 8, 0, 0]),
            TaskBrick("B003", "lego_1x1", [10, 12, 0, 0]),
        ]

        press_side, press_offset = choose_press(
            brick,
            placed,
            (48, 48),
            forbidden_sides=None,
            discouraged_sides={1},
        )

        self.assertEqual(press_side, 1)
        self.assertEqual(press_offset, [0, 1])

    def test_pick_obstacle_keys_can_select_safer_staging_side(self):
        brick = TaskBrick("B001", "lego_2x4", [20, 20, 0, 0])

        press_side, press_offset = choose_press(
            brick,
            placed=[],
            plate_size_xy=(48, 48),
            pick_grid=[8, 2, 0, 0],
            pick_obstacle_keys={(12, 2), (12, 3), (13, 2), (13, 3)},
        )

        self.assertNotEqual(press_side, 1)

    def test_collision_log_forbids_side_used_by_matching_step(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }
        collision_log = {
            "records": [
                {
                    "kind": "tool_clearance",
                    "stage": "place_B001/place_down",
                    "a": "tool",
                    "b": "B999",
                    "overlap_m": [0.001, 0.001, 0.001],
                    "volume_m3": 1e-9,
                }
            ]
        }

        forbidden = forbidden_sides_from_collision_log(task, collision_log)
        optimized = optimize_task(settings(), task, forbidden)

        self.assertEqual(forbidden, {"B001": {1}})
        self.assertNotEqual(optimized["steps"][0]["pick"]["press_side"], 1)

    def test_optimize_task_writes_forbidden_pick_grids_to_planning(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }

        optimized = optimize_task(
            settings(),
            task,
            forbidden_pick_grids_by_brick={"B001": {(8, 2, 0, 0)}},
        )

        self.assertEqual(
            optimized["steps"][0]["planning"]["optimizer"]["forbidden_pick_grids"],
            [[8, 2, 0, 0]],
        )

    def test_collision_log_only_forbids_side_for_press_down_phases(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }
        collision_log = {
            "records": [
                {"kind": "tool_clearance", "stage": "place_B001/pre_pick", "a": "tool", "b": "B999"},
                {"kind": "tool_clearance", "stage": "place_B001/place_twist", "a": "tool", "b": "B999"},
            ]
        }

        forbidden = forbidden_sides_from_collision_log(task, collision_log)

        self.assertEqual(forbidden, {})

    def test_place_exit_collision_log_forbids_side_for_release_phases(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }
        collision_log = {
            "records": [
                {"kind": "tool_clearance", "stage": "place_B001/pre_pick", "a": "tool", "b": "B999"},
                {"kind": "tool_clearance", "stage": "place_B001/place_twist", "a": "tool", "b": "B999"},
                {"kind": "tool_clearance", "stage": "place_B001/place_up", "a": "tool", "b": "B999"},
            ]
        }

        forbidden = forbidden_sides_from_place_exit_collision_log(task, collision_log)
        optimized = optimize_task(settings(), task, forbidden)

        self.assertEqual(forbidden, {"B001": {1}})
        self.assertNotEqual(optimized["steps"][0]["pick"]["press_side"], 1)

    def test_pick_collision_log_forbids_side_for_pick_phases(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 2, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }
        collision_log = {
            "records": [
                {"kind": "tool_clearance", "stage": "place_B001/pre_pick", "a": "tool", "b": "B999"},
                {"kind": "tool_clearance", "stage": "place_B001/place_twist", "a": "tool", "b": "B999"},
            ]
        }

        forbidden = forbidden_sides_from_pick_collision_log(task, collision_log)

        self.assertEqual(forbidden, {"B001": {2}})

    def test_pick_tool_collision_restages_setting_and_task_pick_grid(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }
        collision_log = {
            "records": [
                {"kind": "tool_clearance", "stage": "place_B001/pre_pick", "a": "tool", "b": "B999"},
            ]
        }

        failed = failed_pick_bricks_from_collision_log(task, collision_log)
        next_settings, next_task = restage_failed_pick_bricks(settings(), task, failed)

        self.assertEqual(failed, {"B001"})
        self.assertNotEqual(next_settings["initial_bricks"][0]["grid"], [8, 2, 0, 0])
        self.assertEqual(next_settings["initial_bricks"][0]["grid"], next_task["steps"][0]["pick"]["grid"])

    def test_pick_tool_collision_records_failed_pick_grid_and_restage_avoids_it(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }
        collision_log = {
            "records": [
                {"kind": "tool_clearance", "stage": "place_B001/pre_pick", "a": "tool", "b": "B999"},
            ]
        }

        failed_grids = failed_pick_grids_from_collision_log(task, collision_log)
        next_settings, next_task = restage_failed_pick_bricks(
            settings(),
            task,
            {"B001"},
            {"B001": {(8, 2, 0, 0), (7, 2, 0, 0)}},
        )

        self.assertEqual(failed_grids, {"B001": {(8, 2, 0, 0)}})
        self.assertNotIn(tuple(next_settings["initial_bricks"][0]["grid"]), {(8, 2, 0, 0), (7, 2, 0, 0)})
        self.assertEqual(next_settings["initial_bricks"][0]["grid"], next_task["steps"][0]["pick"]["grid"])

    def test_pick_restage_avoids_prior_final_structure_safety_band(self):
        task_settings = {
            "name": "optimizer_test",
            "plate": {"plate_size_xy": [48, 48]},
            "initial_bricks": [
                {"id": "B001", "type": "lego_1x1", "grid": [2, 20, 0, 0]},
                {"id": "B002", "type": "lego_2x4", "grid": [8, 2, 0, 0]},
            ],
        }
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [2, 20, 0, 0], "press_side": 1, "press_offset": 0},
                    "place": {"grid": [11, 2, 0, 0]},
                },
                {
                    "name": "place_B002",
                    "object": "B002",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [20, 20, 0, 0]},
                },
            ],
        }

        next_settings, next_task = restage_failed_pick_bricks(task_settings, task, {"B002"})

        new_grid = next_settings["initial_bricks"][1]["grid"]
        safety_keys = expanded_footprint_keys_2d("lego_1x1", [11, 2, 0, 0], (48, 48), 8)
        self.assertFalse({(x, y) for x, y, _ in footprint("lego_2x4", new_grid)} & safety_keys)
        self.assertEqual(next_task["steps"][1]["pick"]["grid"], new_grid)

    def test_failure_text_forbids_side_used_by_matching_step(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }

        forbidden = forbidden_sides_from_failure_text(
            task,
            "RuntimeError: IK failed for place_B001/place_down segment 1/3: err=[1, 2, 3]",
        )
        optimized = optimize_task(settings(), task, forbidden)

        self.assertEqual(forbidden, {"B001": {1}})
        self.assertNotEqual(optimized["steps"][0]["pick"]["press_side"], 1)
        self.assertEqual(
            optimized["steps"][0]["planning"]["optimizer"]["forbidden_sides"],
            [1],
        )

    def test_pick_failure_restages_setting_and_task_pick_grid(self):
        task = {
            "name": "optimizer_test",
            "steps": [
                {
                    "name": "place_B001",
                    "object": "B001",
                    "pick": {"grid": [8, 2, 0, 0], "press_side": 1, "press_offset": [0, 1]},
                    "place": {"grid": [12, 10, 0, 0]},
                }
            ],
        }
        text = "RuntimeError: IK failed for place_B001/pick_down: err=[1, 2, 3]"

        failed = failed_pick_bricks_from_failure_text(task, text)
        failed_grids = failed_pick_grids_from_failure_text(task, text)
        next_settings, next_task = restage_failed_pick_bricks(settings(), task, failed)

        self.assertEqual(failed, {"B001"})
        self.assertEqual(failed_grids, {"B001": {(8, 2, 0, 0)}})
        self.assertNotEqual(next_settings["initial_bricks"][0]["grid"], [8, 2, 0, 0])
        self.assertEqual(
            next_settings["initial_bricks"][0]["grid"],
            next_task["steps"][0]["pick"]["grid"],
        )


if __name__ == "__main__":
    unittest.main()
