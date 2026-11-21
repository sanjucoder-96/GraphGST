"""Risk-engine ablation study.

Answers three questions the audit (F1/F2) demands:

  1. What is each scorer's MARGINAL value? (add-one-in ladder + leave-one-out)
  2. Do MLScorer / PropagationScorer help or hurt?
  3. Does the composite discriminate fraud that is NOT ring detection?

Two labels are scored for every scorer combination:

  * ring        — 1 iff GSTIN is a planted-ring member. RingScorer trivially
                  owns this (the label ~= ring detection), so it mainly shows
                  circularity.
  * recon       — 1 iff GSTIN is the SUPPLIER of an invoice with a planted
                  reconciliation anomaly AND is NOT a ring member. This is a
                  ring-INDEPENDENT fraud-ish label: RingScorer cannot see it,
                  so it isolates the value of the non-ring signals.

Deterministic (seed 42, PYTHONHASHSEED pinned). Emits risk_ablation.json and
prints a table. Label columns are stripped before any scorer runs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from datagen.catalog import HSN_CATALOG                                # noqa: E402
from datagen.config import GenerationConfig                            # noqa: E402
from reconcile.engine import ReconcileConfig, run_reconcile            # noqa: E402
from rings.engine import EngineConfig, run_pipeline                    # noqa: E402
from risk import ComposerConfig, RiskComposer, build_context_from_graph_source  # noqa: E402
from risk.scorers import (MLScorer, PropagationScorer, ReconcileScorer,  # noqa: E402
                          RingScorer, RuleScorer, TemporalScorer)

from benchmarks.bench_risk_discrimination import (_generate, _load_graph_source,  # noqa: E402
                                                   _member_meta, _roc_auc,
                                                   _precision_at_k, build_labels)
from benchmarks.evalsafe import strip_graph_source                     # noqa: E402


# Scorer registry — name → (factory, weight). The four default-composer scorers
# use the SHIPPED weights (risk.api.default_composer: reconcile 0.35, ring 0.30,
# rules 0.20, temporal 0.15) so the ablation's headline reflects the config that
# actually ships (an earlier version used ring-heavy weights and understated the
# shipped 4-scorer recon-AUC). propagate/ml carry test weights — they are being
# measured for marginal value, not shipped.
SCORERS = {
    "reconcile":(lambda: ReconcileScorer(weight=0.35),   0.35),
    "ring":     (lambda: RingScorer(weight=0.30),        0.30),
    "rules":    (lambda: RuleScorer(weight=0.20),        0.20),
    "temporal": (lambda: TemporalScorer(weight=0.15),    0.15),
    "propagate":(lambda: PropagationScorer(weight=0.15), 0.15),
    "ml":       (lambda: MLScorer(weight=0.10),          0.10),
}

# Add-one-in ladder (the brief's combinations 1..7)
LADDER = [
    ["ring"],
    ["ring", "reconcile"],
    ["ring", "reconcile", "rules"],
    ["ring", "reconcile", "rules", "temporal"],
    ["ring", "reconcile", "rules", "temporal", "propagate"],
    ["ring", "reconcile", "rules", "temporal", "propagate", "ml"],
]
FULL = ["ring", "reconcile", "rules", "temporal", "propagate", "ml"]


def _score_combo(names: List[str], ctx) -> Dict[str, float]:
    scorers = [SCORERS[n][0]() for n in names]
    composer = RiskComposer(ComposerConfig(scorers=scorers))
    ranked = composer.compose_all(ctx)
    return {r.gstin_id: r.score for r in ranked}


def _auc_pk(scores: Dict[str, float], label: Dict[str, int], ks=(50, 100)) -> dict:
    pairs = [(scores.get(g, 0.0), label[g]) for g in label]
    auc = _roc_auc(pairs)
    out = {"auc": None if auc != auc else round(auc, 4)}   # NaN-safe
    for k in ks:
        out[f"p@{k}"] = round(_precision_at_k(pairs, k), 4)
    out["n_pos"] = sum(label.values())
    return out


def run_ablation(cfg: GenerationConfig) -> dict:
    _generate(cfg)
    with open(os.path.join(cfg.out_dir, "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)

    gs = _load_graph_source(cfg.out_dir)
    ring_label, recon_label = build_labels(gs, truth)

    # Shared upstream engines (run once).
    events = run_reconcile(graph_source=gs,
                            config=ReconcileConfig(include_matched=False, hsn_catalog=HSN_CATALOG))
    rings = run_pipeline(graph_source={"edges": gs["edges"], "member_meta": _member_meta(gs["gstins"])},
                          config=EngineConfig(hop_max=cfg.ring_size_max + 2, window_days=90,
                                               persist=False, propagate=False))

    gs_safe = strip_graph_source(gs)     # F5: no label columns to scorers
    ctx = build_context_from_graph_source(
        gs_safe, match_events=events,
        detected_rings=[r.__dict__ for r in rings],
        member_meta=_member_meta(gs_safe["gstins"]))

    report: dict = {
        "config": cfg.to_dict(),
        "labels": {
            "ring_positives": sum(ring_label.values()),
            "recon_positives": sum(recon_label.values()),
        },
        "single_scorer": {},
        "add_one_in_ladder": [],
        "leave_one_out": {},
    }

    # Each scorer alone
    for name in SCORERS:
        scores = _score_combo([name], ctx)
        report["single_scorer"][name] = {
            "ring": _auc_pk(scores, ring_label),
            "recon": _auc_pk(scores, recon_label),
        }

    # Add-one-in ladder
    prev_ring_auc = None
    for combo in LADDER:
        scores = _score_combo(combo, ctx)
        ring_m = _auc_pk(scores, ring_label)
        recon_m = _auc_pk(scores, recon_label)
        added = combo[-1]
        delta = (None if prev_ring_auc is None or ring_m["auc"] is None
                 else round(ring_m["auc"] - prev_ring_auc, 4))
        report["add_one_in_ladder"].append({
            "scorers": combo, "added": added,
            "ring": ring_m, "recon": recon_m,
            "ring_auc_delta_vs_prev": delta,
        })
        prev_ring_auc = ring_m["auc"]

    # Leave-one-out from the full model
    full_scores = _score_combo(FULL, ctx)
    full_ring = _auc_pk(full_scores, ring_label)
    full_recon = _auc_pk(full_scores, recon_label)
    report["full_model"] = {"scorers": FULL, "ring": full_ring, "recon": full_recon}
    for name in FULL:
        combo = [n for n in FULL if n != name]
        scores = _score_combo(combo, ctx)
        loo_ring = _auc_pk(scores, ring_label)
        loo_recon = _auc_pk(scores, recon_label)
        report["leave_one_out"][name] = {
            "without_scorer": combo,
            "ring": loo_ring, "recon": loo_recon,
            # marginal value of `name` = full − (full without name)
            "ring_auc_marginal": (None if full_ring["auc"] is None or loo_ring["auc"] is None
                                   else round(full_ring["auc"] - loo_ring["auc"], 4)),
            "recon_auc_marginal": (None if full_recon["auc"] is None or loo_recon["auc"] is None
                                    else round(full_recon["auc"] - loo_recon["auc"], 4)),
        }
    return report


def format_table(report: dict) -> str:
    lines: List[str] = []
    lines.append("ADD-ONE-IN LADDER  (label: ring = circular; recon = ring-independent)")
    lines.append(f"{'scorers':52s}  {'ring.auc':>8s}  {'d_vs_prev':>9s}  {'recon.auc':>9s}")
    lines.append("-" * 84)
    for row in report["add_one_in_ladder"]:
        combo = "+".join(row["scorers"])
        ra = row["ring"]["auc"]; rd = row["ring_auc_delta_vs_prev"]; ca = row["recon"]["auc"]
        lines.append(f"{combo:52s}  {ra:>8}  {('' if rd is None else f'{rd:+.4f}'):>8s}  {ca:>9}")
    lines.append("")
    lines.append("LEAVE-ONE-OUT FROM FULL  (marginal = full minus without)")
    lines.append(f"{'remove scorer':16s}  {'ring.marginal':>13s}  {'recon.marginal':>14s}")
    lines.append("-" * 50)
    for name, r in report["leave_one_out"].items():
        lines.append(f"{name:16s}  {str(r['ring_auc_marginal']):>13s}  {str(r['recon_auc_marginal']):>14s}")
    lines.append("")
    lines.append("SINGLE SCORER  (each alone)")
    lines.append(f"{'scorer':12s}  {'ring.auc':>8s}  {'recon.auc':>9s}")
    lines.append("-" * 36)
    for name, r in report["single_scorer"].items():
        lines.append(f"{name:12s}  {str(r['ring']['auc']):>8s}  {str(r['recon']['auc']):>9s}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n-gstins", type=int, default=500)
    p.add_argument("--n-rings", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(Path(__file__).with_name("risk_ablation.json")))
    args = p.parse_args()

    if os.environ.get("PYTHONHASHSEED") != "0":
        import subprocess
        env = dict(os.environ); env["PYTHONHASHSEED"] = "0"
        return subprocess.call([sys.executable, "-m", "benchmarks.ablation.ablate_risk", *sys.argv[1:]], env=env)

    cfg = GenerationConfig(n_gstins=args.n_gstins, months=3, n_rings=args.n_rings,
                            ring_size_min=3, ring_size_max=6, seed=args.seed,
                            out_dir=os.path.join(tempfile.gettempdir(), "graphgst_ablate"))
    cfg.validate()
    report = run_ablation(cfg)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(format_table(report))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
