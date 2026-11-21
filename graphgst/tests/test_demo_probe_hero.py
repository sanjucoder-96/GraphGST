"""Regression test: `demo.probe_hero` must report NO DRIFT.

If datagen changes and the hero ring's shape shifts, this test fails
and the developer must either revert the datagen change or update
`demo/scenario.py` to match the new hero + rerun `demo.verify` to
lock in the fresh baseline."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.slow
def test_probe_hero_reports_no_drift():
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    result = subprocess.run(
        [sys.executable, "-m", "demo.probe_hero"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        pytest.fail(
            "demo.probe_hero reported drift — datagen produced hero-ring "
            "values that differ from demo/scenario.py. Either revert the "
            "datagen change or update HERO_RING and re-run "
            "`python -m demo.verify` to lock in the new baseline.\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )
