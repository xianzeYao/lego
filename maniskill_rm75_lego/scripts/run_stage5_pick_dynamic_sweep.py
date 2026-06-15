#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)
STAGE5_SCRIPT = REPO_ROOT / "maniskill_rm75_lego" / "scripts" / "run_stage5_pick_dynamic_1x6.py"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/stage5_pick_dynamic_1x6_sweep")
    parser.add_argument("--candidate-output-dir", default="outputs/stage5_pick_dynamic_1x6")
    parser.add_argument("--sleep-between-runs", type=float, default=0.0)
    parser.add_argument("--report-every-seconds", type=float, default=1800.0)
    parser.add_argument("--max-runs", type=int, default=0, help="0 means run the built-in candidate list once")
    parser.add_argument("--tool-proxy", action="store_true")
    parser.add_argument("--render", action="store_true")
    return parser.parse_args()


def candidate_grid():
    contact_zs = [-0.012, -0.015, -0.018, -0.021]
    press_depths = [0.003, 0.005, 0.007, 0.009]
    twist_degs = [-14.0, -18.0, -22.0]
    for contact_z in contact_zs:
        for press_depth in press_depths:
            for twist_deg in twist_degs:
                yield {
                    "contact_offset": [0.0, 0.0, contact_z],
                    "press_depth": press_depth,
                    "pick_twist_deg": twist_deg,
                }


def newest_summary(output_dir: Path, before: set[Path]) -> Path | None:
    summaries = set(output_dir.glob("run_*/summary.json")) - before
    if not summaries:
        return None
    return max(summaries, key=lambda p: p.stat().st_mtime)


def main() -> int:
    args = parse_args()
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

    sweep_dir = Path(args.output_dir) / datetime.now().strftime("sweep_%Y%m%d_%H%M%S")
    sweep_dir.mkdir(parents=True, exist_ok=True)
    candidate_output_dir = Path(args.candidate_output_dir)
    candidate_output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    start_time = time.time()
    last_report = start_time
    candidates = list(candidate_grid())
    if args.max_runs > 0:
        candidates = candidates[: args.max_runs]

    for idx, candidate in enumerate(candidates, start=1):
        before = set(candidate_output_dir.glob("run_*/summary.json"))
        cmd = [
            str(PYTHON),
            str(STAGE5_SCRIPT),
            "--output-dir",
            str(candidate_output_dir),
            "--steps-per-segment",
            "24",
            "--hold-steps",
            "10",
            "--settle-steps",
            "40",
            "--contact-offset",
            *(str(v) for v in candidate["contact_offset"]),
            "--press-depth",
            str(candidate["press_depth"]),
            "--pick-twist-deg",
            str(candidate["pick_twist_deg"]),
        ]
        if args.tool_proxy:
            cmd.append("--tool-proxy")
        if args.render:
            cmd.append("--render")

        print(f"[sweep] candidate {idx}/{len(candidates)} {candidate}")
        completed = subprocess.run(cmd, cwd=REPO_ROOT, env=os.environ.copy(), check=False)
        summary_path = newest_summary(candidate_output_dir, before)
        if summary_path is None:
            row = {
                "idx": idx,
                "success": False,
                "summary_path": "",
                "returncode": completed.returncode,
                **candidate,
            }
        else:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            impulses = summary.get("max_contact_impulse", {})
            row = {
                "idx": idx,
                "success": summary.get("success", False),
                "summary_path": str(summary_path),
                "returncode": completed.returncode,
                "contact_offset": summary.get("contact_offset_tcp"),
                "press_depth": summary.get("press_depth"),
                "pick_twist_deg": summary.get("pick_twist_deg"),
                "max_lift_m": summary.get("max_lift_m"),
                "final_lift_m": summary.get("final_lift_m"),
                "max_verify_rel_drift_m": summary.get("max_verify_rel_drift_m"),
                "brick_tool_impulse": impulses.get("brick_tool"),
                "brick_tool_proxy_impulse": impulses.get("brick_tool_proxy"),
                "brick_baseplate_impulse": impulses.get("brick_baseplate"),
            }
        rows.append(row)

        summary_csv = sweep_dir / "sweep_summary.csv"
        with summary_csv.open("w", newline="", encoding="utf-8") as f:
            fieldnames = sorted({key for r in rows for key in r.keys()})
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        if row.get("success"):
            print("[sweep] PASS", row)
            print("[sweep] wrote", summary_csv)
            return 0

        now = time.time()
        if now - last_report >= args.report_every_seconds:
            best = max(rows, key=lambda r: r.get("max_lift_m") or -999)
            print("[sweep] periodic report best_by_lift:", best)
            print("[sweep] wrote", summary_csv)
            last_report = now
        if args.sleep_between_runs > 0:
            time.sleep(args.sleep_between_runs)

    print("[sweep] no successful candidate")
    print("[sweep] wrote", sweep_dir / "sweep_summary.csv")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
