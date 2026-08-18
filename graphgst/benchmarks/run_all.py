"""Unified benchmark runner.

Generates ONE synthetic dataset (deterministic, seeded), then runs all
four bench modules against it and merges their reports into a single
`latest.json` file. Prints a compact summary table and returns
exit-code 0 iff all metrics stay within tolerance of the baseline.

Usage
-----
    python -m benchmarks.run_all                     # default cfg
    python -m benchmarks.run_all --write-baseline    # overwrite baseline.json
    python -m benchmarks.run_all --n-gstins 1000 --seed 7

Exit codes
----------
    0  all headline metrics within tolerance
    1  at least one regression beyond tolerance
    2  bench crashed
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datagen.anomalies import inject_anomalies                    # noqa: E402
from datagen.config import GenerationConfig                        # noqa: E402
from datagen.emitters import emit                                  # noqa: E402
from datagen.network import sample_edges, sample_gstins            # noqa: E402
from datagen.rings import plant_rings                              # noqa: E402
from datagen.transactions import derive_returns, sample_transactions  # noqa: E402

METRICS_SCHEMA_VERSION = 1


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT.parent), stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _prepare_dataset(cfg: GenerationConfig) -> None:
    """Emit the shared synthetic dataset to cfg.out_dir once."""
    gstins = sample_gstins(cfg)
    edges = sample_edges(cfg, gstins)
    bundles = sample_transactions(cfg, gstins, edges)
    ring_bundles, ring_g1, ring_g3, ring_tp, planted_rings = plant_rings(cfg, gstins)
    ring_ids = {b.invoice.invoice_id for b in ring_bundles}
    bundles = bundles + ring_bundles
    g1, g3, g2b, tp = derive_returns(cfg, gstins, bundles)
    g1.extend(ring_g1); g3.extend(ring_g3); tp.extend(ring_tp)
    bundles, g1, g3, tp, planted = inject_anomalies(
        cfg, bundles, g1, g3, tp,
        ring_invoice_ids=ring_ids, gstin_meta_records=gstins,
    )
    emit(cfg, gstins, bundles, g1, g3, g2b, tp, planted, planted_rings)


def _run_one(name: str, fn) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        report = fn()
        elapsed = round(time.perf_counter() - t0, 3)
        return {"status": "ok", "elapsed_sec": elapsed, "report": report}
    except Exception as e:
        elapsed = round(time.perf_counter() - t0, 3)
        return {"status": "error", "elapsed_sec": elapsed, "error": repr(e)}


def run_all(
    cfg: Optional[GenerationConfig] = None,
    embed_k: int = 10,
    embed_walks: int = 15,
    embed_walk_len: int = 25,
) -> Dict[str, Any]:
    """Run every bench against one shared dataset. Returns the merged report."""
    cfg = cfg or GenerationConfig(
        n_gstins=500, months=3, n_rings=8,
        ring_size_min=3, ring_size_max=6, seed=42,
        out_dir=os.path.join(tempfile.gettempdir(), "graphgst_bench_all"),
    )
    cfg.validate()
    # Clean start
    if os.path.isdir(cfg.out_dir):
        shutil.rmtree(cfg.out_dir, ignore_errors=True)
    os.makedirs(cfg.out_dir, exist_ok=True)

    t0 = time.perf_counter()
    _prepare_dataset(cfg)
    prep_sec = round(time.perf_counter() - t0, 3)

    from benchmarks import bench_embed_lookalike, bench_reconcile_prf   # noqa: E402
    from benchmarks import bench_ring_recall, bench_risk_discrimination  # noqa: E402

    benches = {
        "ring_recall":      lambda: bench_ring_recall.bench_prepared(cfg, cfg.out_dir),
        "reconcile_prf":    lambda: bench_reconcile_prf.bench_prepared(cfg, cfg.out_dir),
        "risk_discrimination": lambda: bench_risk_discrimination.bench_prepared(cfg, cfg.out_dir),
        "embed_lookalike":  lambda: bench_embed_lookalike.bench_prepared(
            cfg, cfg.out_dir, embed_k, embed_walks, embed_walk_len),
    }

    per_bench: Dict[str, Any] = {}
    for name, fn in benches.items():
        per_bench[name] = _run_one(name, fn)

    # Extract the headline metrics for the compact score card
    headlines = _extract_headlines(per_bench)

    merged = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "config": cfg.to_dict(),
        "dataset_prep_sec": prep_sec,
        "headlines": headlines,
        "benches": per_bench,
    }

    # Cleanup dataset dir (don't leave temp files behind)
    shutil.rmtree(cfg.out_dir, ignore_errors=True)
    return merged


def _extract_headlines(per_bench: Dict[str, Any]) -> Dict[str, float]:
    """Pull the numbers that headline claims are made from."""
    out: Dict[str, float] = {}

    def _rep(name: str) -> Optional[Dict[str, Any]]:
        entry = per_bench.get(name)
        if not entry or entry.get("status") != "ok":
            return None
        return entry.get("report")

    r = _rep("ring_recall")
    if r:
        out["ring.recall"] = float(r.get("recall") or 0.0)
        out["ring.detected"] = float((r.get("counts") or {}).get("detected_rings", 0))

    r = _rep("reconcile_prf")
    if r:
        micro = r.get("micro") or {}
        out["reconcile.micro_f1"] = float(micro.get("f1") or 0.0)
        out["reconcile.micro_precision"] = float(micro.get("precision") or 0.0)
        out["reconcile.micro_recall"] = float(micro.get("recall") or 0.0)

    r = _rep("risk_discrimination")
    if r:
        out["risk.roc_auc"] = float(r.get("roc_auc") or 0.0)
        pk = r.get("precision_at_k") or {}
        out["risk.precision_at_50"] = float(pk.get("50") or 0.0)
        out["risk.precision_at_100"] = float(pk.get("100") or 0.0)

    r = _rep("embed_lookalike")
    if r:
        for row in r.get("per_k") or []:
            if int(row.get("k") or 0) == 10:
                out["embed.hit_at_10"] = float(row.get("hit_at_k") or 0.0)
                out["embed.cohesion_recall_at_10"] = float(
                    row.get("cohesion_recall_mean") or 0.0
                )

    return out


def _write(report: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def _reexec_with_hashseed_if_needed() -> None:
    """Python's per-process hash randomisation changes set-iteration order
    across runs, which cascades into NetworkX SCC / random walks and makes
    numeric benchmarks non-byte-deterministic. If PYTHONHASHSEED isn't
    already fixed, re-exec self with PYTHONHASHSEED=0."""
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    os.execvpe(sys.executable, [sys.executable, "-m", "benchmarks.run_all", *sys.argv[1:]], env)


def main() -> int:
    _reexec_with_hashseed_if_needed()
    p = argparse.ArgumentParser()
    p.add_argument("--n-gstins", type=int, default=500)
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--n-rings", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(Path(__file__).with_name("latest.json")))
    p.add_argument("--baseline",
                    default=str(Path(__file__).with_name("baseline.json")))
    p.add_argument("--write-baseline", action="store_true",
                    help="overwrite baseline.json with the current run (use after "
                          "you've verified the numbers improved intentionally)")
    p.add_argument("--tolerance-abs", type=float, default=0.02,
                    help="absolute drop that counts as a regression (default 0.02)")
    args = p.parse_args()

    cfg = GenerationConfig(
        n_gstins=args.n_gstins, months=args.months, n_rings=args.n_rings,
        ring_size_min=3, ring_size_max=6, seed=args.seed,
        out_dir=os.path.join(tempfile.gettempdir(), "graphgst_bench_all"),
    )
    try:
        report = run_all(cfg)
    except Exception as e:
        print(f"BENCH CRASHED: {e!r}", file=sys.stderr)
        return 2

    _write(report, args.out)
    print(f"wrote {args.out}")

    from benchmarks.compare import compare_reports, format_diff_table
    baseline: Optional[Dict[str, Any]] = None
    if os.path.exists(args.baseline):
        with open(args.baseline, "r", encoding="utf-8") as f:
            baseline = json.load(f)
    diff = compare_reports(baseline, report, tolerance_abs=args.tolerance_abs)
    print()
    print(format_diff_table(diff))
    print()

    if args.write_baseline:
        _write(report, args.baseline)
        print(f"baseline updated -> {args.baseline}")
        return 0

    return 0 if diff["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
