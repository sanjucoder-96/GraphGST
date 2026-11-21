"""Benchmark: does the embedding + k-NN find OTHER ring members when
queried with ONE ring member?

Metric — ring-cohesion recall@K:
  For every planted-ring member m of ring R:
      hits(m) = |top_K(m) ∩ (R \\ {m})|
      max     = min(K, |R| - 1)
      recall  = hits / max
  Report mean and median across all planted members, plus hit@K (the
  fraction of planted members whose top-K contains ≥ 1 other member).

Also reports a random-baseline recall to show the model is doing
something better than pure chance.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datagen.anomalies import inject_anomalies                    # noqa: E402
from datagen.config import GenerationConfig                        # noqa: E402
from datagen.emitters import emit                                  # noqa: E402
from datagen.network import sample_edges, sample_gstins            # noqa: E402
from datagen.rings import plant_rings                              # noqa: E402
from datagen.transactions import derive_returns, sample_transactions  # noqa: E402
from embed import EmbedConfig, LookalikeIndex, train               # noqa: E402


def _generate(cfg: GenerationConfig) -> None:
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


def _load_edges(dir: str) -> list[dict]:
    with open(os.path.join(dir, "invoices.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [{"src": r["supplier_gstin"], "dst": r["buyer_gstin"],
              "amount": float(r.get("taxable_value") or 0)} for r in rows]


def _cohesion_at_k(index: LookalikeIndex, rings: list[dict], k: int,
                    adjacency: dict[str, set] | None = None) -> dict:
    """Cohesion recall / hit@k over planted-ring members.

    Two flavours (audit F3):
      * adjacency   — do a member's top-K neighbours include ANY same-ring
                      member? Ring members transact in a cycle so their cycle
                      neighbours are 1-hop; this is largely an adjacency check.
      * structural  — do the top-K include a same-ring member that is NOT a
                      direct transaction counterparty (≥2 hops away in the
                      cycle)? This isolates genuine structural similarity from
                      trivial adjacency and is the HONEST lookalike claim.
    """
    adjacency = adjacency or {}
    per_member_recall: list[float] = []
    hit_flags: list[int] = []
    struct_hit_flags: list[int] = []
    struct_queries = 0

    for r in rings:
        members = r.get("members") or []
        if len(members) < 2:
            continue
        others = set(members)
        for m in members:
            if m not in index.id_to_idx:
                continue
            neighbours = {g for g, _ in index.similar_to(m, k=k)}
            other_hits = neighbours & (others - {m})
            max_possible = min(k, len(others) - 1)
            per_member_recall.append(len(other_hits) / max_possible if max_possible else 0.0)
            hit_flags.append(1 if other_hits else 0)

            # structural: co-members that are NOT direct transaction partners
            direct = adjacency.get(m, set())
            non_adjacent_comembers = (others - {m}) - direct
            if non_adjacent_comembers:      # only rings with ≥1 non-adjacent co-member
                struct_queries += 1
                struct_hit_flags.append(1 if (neighbours & non_adjacent_comembers) else 0)

    if not per_member_recall:
        return {"k": k, "n_queries": 0}
    return {
        "k": k,
        "n_queries": len(per_member_recall),
        "cohesion_recall_mean": round(statistics.mean(per_member_recall), 3),
        "cohesion_recall_median": round(statistics.median(per_member_recall), 3),
        "hit_at_k": round(statistics.mean(hit_flags), 3),
        # honest structural metric
        "structural_queries": struct_queries,
        "structural_hit_at_k": (round(statistics.mean(struct_hit_flags), 3)
                                 if struct_hit_flags else None),
    }


def _random_baseline(all_ids: list[str], rings: list[dict], k: int, seed: int) -> float:
    """Baseline: for each member, sample K random OTHER GSTINs and count
    how many are same-ring members. Report mean recall."""
    rng = random.Random(seed)
    recalls = []
    for r in rings:
        members = r.get("members") or []
        if len(members) < 2:
            continue
        others = set(members)
        pool = [g for g in all_ids if g not in members]
        if not pool:
            continue
        for m in members:
            sample = rng.sample(pool + list(others - {m}),
                                    k=min(k, len(pool) + len(others) - 1))
            hits = {g for g in sample} & (others - {m})
            max_possible = min(k, len(others) - 1)
            recalls.append(len(hits) / max_possible if max_possible > 0 else 0.0)
    return round(statistics.mean(recalls), 3) if recalls else 0.0


def bench_prepared(cfg: GenerationConfig, out_dir: str, k: int,
                    walks: int, walk_len: int) -> dict:
    """Run the embed lookalike benchmark on a pre-generated dataset dir."""
    t_gen = 0.0

    with open(os.path.join(out_dir, "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)
    planted_rings = truth.get("planted_rings", [])

    t1 = time.perf_counter()
    edges = _load_edges(out_dir)
    t_load = time.perf_counter() - t1

    t2 = time.perf_counter()
    model = train(graph_source={"edges": edges},
                    config=EmbedConfig(dim=64, walks_per_node=walks,
                                          walk_len=walk_len, window=5, seed=cfg.seed))
    t_train = time.perf_counter() - t2
    index = LookalikeIndex(ids=list(model.ids), matrix=model.matrix)

    # Direct-transaction adjacency (both directions) for the structural metric.
    adjacency: dict[str, set] = {}
    for e in edges:
        s, d = e.get("src"), e.get("dst")
        if s and d:
            adjacency.setdefault(s, set()).add(d)
            adjacency.setdefault(d, set()).add(s)

    ks = [3, 5, 10, 25]
    per_k = [_cohesion_at_k(index, planted_rings, k=kk, adjacency=adjacency) for kk in ks]
    baselines = {kk: _random_baseline(list(model.ids), planted_rings,
                                         k=kk, seed=cfg.seed) for kk in ks}

    return {
        "config": cfg.to_dict(),
        "embed_config": {
            "dim": 64, "walks_per_node": walks, "walk_len": walk_len,
            "window": 5, "seed": cfg.seed,
        },
        "timing_sec": {"generate": round(t_gen, 3),
                        "load_csv": round(t_load, 3),
                        "train_embed": round(t_train, 3)},
        "counts": {"n_edges": len(edges), "n_indexed_gstins": len(model.ids),
                    "n_planted_rings": len(planted_rings),
                    "n_planted_members": sum(len(r.get("members") or []) for r in planted_rings)},
        "stats": model.stats,
        "per_k": per_k,
        "random_baseline_recall": baselines,
    }


def bench(cfg: GenerationConfig, k: int, walks: int, walk_len: int) -> dict:
    _generate(cfg)
    return bench_prepared(cfg, cfg.out_dir, k, walks, walk_len)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n-gstins", type=int, default=500)
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--n-rings", type=int, default=8)
    p.add_argument("--ring-size-min", type=int, default=3)
    p.add_argument("--ring-size-max", type=int, default=6)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--walks", type=int, default=15)
    p.add_argument("--walk-len", type=int, default=25)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--out-dir", type=str, default="./_bench_embed")
    args = p.parse_args()
    cfg = GenerationConfig(
        n_gstins=args.n_gstins, months=args.months, n_rings=args.n_rings,
        ring_size_min=args.ring_size_min, ring_size_max=args.ring_size_max,
        seed=args.seed, out_dir=args.out_dir,
    )
    cfg.validate()
    print(json.dumps(bench(cfg, args.k, args.walks, args.walk_len), indent=2))


if __name__ == "__main__":
    main()
