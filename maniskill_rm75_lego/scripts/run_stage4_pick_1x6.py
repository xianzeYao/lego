#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from maniskill_rm75_lego.scripts.run_stage4_pick_2x4 import main


if __name__ == "__main__":
    raise SystemExit(main(
        default_brick_key="lego_1x6",
        default_press_side=2,
        default_press_offset=2,
    ))
