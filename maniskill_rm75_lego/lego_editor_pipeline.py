from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from maniskill_rm75_lego.task_optimization_loop import run_optimization_loop


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_ROOT = REPO_ROOT / "config" / "lego_editor_samples"
DEFAULT_OUTPUT_ROOT = Path("/tmp/lego_editor_sample_optimized")


def config_dirs(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "settings.json").exists() and (path / "task.json").exists()
    )


def export_samples(sample_root: Path) -> None:
    subprocess.run(
        ["npm", "run", "export:samples", "--", str(sample_root)],
        cwd=REPO_ROOT / "lego_editor",
        check=True,
    )


def read_summary(output_dir: Path) -> dict:
    summary_path = output_dir / "optimization_summary.json"
    if not summary_path.exists():
        return {}
    with summary_path.open("r") as f:
        return json.load(f)


def run_pipeline(
    sample_root: Path,
    output_root: Path,
    iterations: int,
    runner_args: list[str],
    should_export_samples: bool,
    keep_going_without_log: bool,
) -> dict:
    sample_root = sample_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if should_export_samples:
        export_samples(sample_root)

    results = []
    for config_dir in config_dirs(sample_root):
        target_dir = output_root / config_dir.name
        final_dir = run_optimization_loop(
            config_dir=config_dir,
            output_dir=target_dir,
            iterations=iterations,
            runner_args=runner_args,
            stop_on_runner_failure_without_log=not keep_going_without_log,
        )
        summary = read_summary(target_dir)
        results.append(
            {
                "name": config_dir.name,
                "input_dir": str(config_dir),
                "output_dir": str(target_dir),
                "final_dir": str(final_dir),
                "converged": bool(summary.get("converged")),
                "best_score": summary.get("best_score"),
                "iterations": len(summary.get("iterations", [])),
            }
        )

    pipeline_summary = {
        "sample_root": str(sample_root),
        "output_root": str(output_root),
        "iterations_requested": int(iterations),
        "runner_args": runner_args,
        "results": results,
        "all_converged": all(item["converged"] for item in results),
    }
    with (output_root / "pipeline_summary.json").open("w") as f:
        json.dump(pipeline_summary, f, indent=2)
        f.write("\n")
    return pipeline_summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export LEGO editor samples and optimize each settings/task directory."
    )
    parser.add_argument("--sample-root", type=Path, default=DEFAULT_SAMPLE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--iterations", type=int, default=6)
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Use existing sample configs instead of regenerating them from lego_editor.",
    )
    parser.add_argument(
        "--strict-log",
        action="store_true",
        help="Fail if the runner exits before writing a collision log.",
    )
    parser.add_argument(
        "runner_args",
        nargs=argparse.REMAINDER,
        help="Extra run_task_lego_robot.py args after '--'. Defaults to a fast dry-run smoke.",
    )
    args = parser.parse_args()
    runner_args = args.runner_args
    if runner_args[:1] == ["--"]:
        runner_args = runner_args[1:]
    if not runner_args:
        runner_args = ["--steps-per-segment", "8", "--hold-steps", "1"]

    summary = run_pipeline(
        sample_root=args.sample_root,
        output_root=args.output_root,
        iterations=args.iterations,
        runner_args=runner_args,
        should_export_samples=not args.skip_export,
        keep_going_without_log=not args.strict_log,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_converged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
