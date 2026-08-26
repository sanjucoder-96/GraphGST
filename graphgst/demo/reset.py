"""Reset the demo state to the fixed hero scenario.

One command that (a) regenerates the demo dataset under `demo/artifacts/`
byte-deterministically and (b) optionally wipes and reloads Neo4j from
that dataset. Every subsequent run of the demo starts from the exact
same graph.

Usage
-----
    python -m demo.reset                 # regen + attempt Neo4j load
    python -m demo.reset --no-neo4j      # regen only; Neo4j untouched
    python -m demo.reset --status        # print current demo status
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# make top-level project importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datagen.anomalies import inject_anomalies                    # noqa: E402
from datagen.config import GenerationConfig                        # noqa: E402
from datagen.emitters import emit                                  # noqa: E402
from datagen.network import sample_edges, sample_gstins            # noqa: E402
from datagen.rings import plant_rings                              # noqa: E402
from datagen.transactions import derive_returns, sample_transactions  # noqa: E402

from .scenario import DEMO_MONTHS, DEMO_N_GSTINS, DEMO_N_RINGS, DEMO_SEED

logger = logging.getLogger(__name__)

DEMO_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
DEMO_STATUS_FILE = os.path.join(DEMO_ARTIFACT_DIR, "status.json")

DEMO_CFG = GenerationConfig(
    n_gstins=DEMO_N_GSTINS, months=DEMO_MONTHS, n_rings=DEMO_N_RINGS,
    ring_size_min=3, ring_size_max=6, seed=DEMO_SEED,
    out_dir=DEMO_ARTIFACT_DIR,
)


def _reexec_with_hashseed_if_needed() -> None:
    """Same trick as `benchmarks/run_all.py` — Python's per-process hash
    salt cascades into different set-iteration and NetworkX SCC output,
    so pin it before running any generator. Uses subprocess (rather than
    os.execvpe) because os.execvpe with `python -m …` is silently broken
    on Windows."""
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    import subprocess
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    ret = subprocess.call([sys.executable, "-m", "demo.reset", *sys.argv[1:]], env=env)
    sys.exit(ret)


def _generate() -> Dict[str, Any]:
    """Rebuild the demo dataset in DEMO_ARTIFACT_DIR."""
    if os.path.isdir(DEMO_ARTIFACT_DIR):
        shutil.rmtree(DEMO_ARTIFACT_DIR, ignore_errors=True)
    os.makedirs(DEMO_ARTIFACT_DIR, exist_ok=True)
    DEMO_CFG.validate()

    gstins = sample_gstins(DEMO_CFG)
    edges = sample_edges(DEMO_CFG, gstins)
    bundles = sample_transactions(DEMO_CFG, gstins, edges)
    ring_bundles, r_g1, r_g3, r_tp, planted_rings = plant_rings(DEMO_CFG, gstins)
    ring_ids = {b.invoice.invoice_id for b in ring_bundles}
    bundles = bundles + ring_bundles
    g1, g3, g2b, tp = derive_returns(DEMO_CFG, gstins, bundles)
    g1.extend(r_g1); g3.extend(r_g3); tp.extend(r_tp)
    bundles, g1, g3, tp, planted = inject_anomalies(
        DEMO_CFG, bundles, g1, g3, tp,
        ring_invoice_ids=ring_ids, gstin_meta_records=gstins,
    )
    emit(DEMO_CFG, gstins, bundles, g1, g3, g2b, tp, planted, planted_rings)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cfg": DEMO_CFG.to_dict(),
        "counts": {
            "gstins": len(gstins),
            "invoices": len(bundles),
            "gstr1": len(g1), "gstr3b": len(g3), "gstr2b": len(g2b),
            "taxpayments": len(tp), "planted_rings": len(planted_rings),
            "planted_anomalies": len(planted),
        },
        "planted_rings": planted_rings,
    }


def _neo4j_reload(status: Dict[str, Any]) -> Dict[str, Any]:
    """Wipe Neo4j and reload from the demo artifacts. Best-effort — if
    Neo4j is unreachable we log a warning and set neo4j_loaded=False."""
    try:
        from datagen.loader import load_directory
        from db import run_write
        # Wipe first so a stale prior demo can't leak into the new one.
        run_write("MATCH (n) DETACH DELETE n")
        summary = load_directory(DEMO_ARTIFACT_DIR)
        status["neo4j_loaded"] = True
        status["neo4j_summary"] = summary
        logger.info("Neo4j reloaded from demo artifacts")
        # Materialize intelligence so the demo graph is immediately investigable:
        # detect+persist rings, reconcile+persist events, materialize composed
        # risk onto GSTIN nodes. Best-effort — a graph without it still loads.
        try:
            from risk.materialize import refresh_intelligence
            status["intelligence"] = refresh_intelligence(persist=True)
            logger.info("intelligence materialized: %s", status["intelligence"])
        except Exception as ie:  # noqa: BLE001
            status["intelligence_error"] = repr(ie)
            logger.warning(f"intelligence refresh skipped: {ie}")
    except Exception as e:
        status["neo4j_loaded"] = False
        status["neo4j_error"] = repr(e)
        logger.warning(f"Neo4j reload skipped: {e}")
    return status


def _write_status(status: Dict[str, Any]) -> None:
    with open(DEMO_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, default=str)


def read_status() -> Optional[Dict[str, Any]]:
    if not os.path.exists(DEMO_STATUS_FILE):
        return None
    with open(DEMO_STATUS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def reset(load_neo4j: bool = True) -> Dict[str, Any]:
    """Reset the demo state and return the status dict."""
    status = _generate()
    status["artifact_dir"] = DEMO_ARTIFACT_DIR
    if load_neo4j:
        status = _neo4j_reload(status)
    else:
        status["neo4j_loaded"] = False
        status["neo4j_error"] = "skipped by caller"
    _write_status(status)
    return status


def main() -> int:
    _reexec_with_hashseed_if_needed()
    p = argparse.ArgumentParser()
    p.add_argument("--no-neo4j", action="store_true",
                    help="regenerate CSVs only; leave Neo4j untouched")
    p.add_argument("--status", action="store_true",
                    help="print the current demo status and exit")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                          format="%(asctime)s %(levelname)s %(message)s")

    if args.status:
        s = read_status()
        if s is None:
            print("No demo state — run `python -m demo.reset` first")
            return 1
        print(json.dumps({k: v for k, v in s.items() if k != "planted_rings"},
                            indent=2))
        return 0

    print(f"resetting demo state at {DEMO_ARTIFACT_DIR}")
    status = reset(load_neo4j=not args.no_neo4j)
    print(json.dumps({
        "generated_at": status["generated_at"],
        "artifact_dir": status["artifact_dir"],
        "counts": status["counts"],
        "neo4j_loaded": status.get("neo4j_loaded"),
        "neo4j_error": status.get("neo4j_error"),
    }, indent=2, default=str))
    print()
    print("Next: python -m demo.verify   # confirm every story number holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
