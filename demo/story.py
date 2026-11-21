"""The demo story — an ordered list of steps.

Each step has:
  * a title + narrator prompt (what the presenter says)
  * a route (which UI page to be on)
  * a "trace" — the endpoints or values the presenter will point at
  * "expected" — assertions the demo verifier runs against real state

The verifier reads THIS file, hits the endpoints, and asserts every
`expected` clause. If a step's expected value drifts from what the
system actually produces, the demo fails BEFORE the presenter is on
stage — never during.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .scenario import HERO_RING


STORY: List[Dict[str, Any]] = [
    {
        "step": 1,
        "duration_sec": 30,
        "title": "Setup — one command reset",
        "route": None,
        "narrator": (
            "One command wipes and re-seeds the entire demo. "
            "500 GSTINs, 3701 invoices, 8 planted circular-trading rings, "
            "seed 42, PYTHONHASHSEED 0. Byte-deterministic. Every subsequent "
            "run starts from the identical graph."
        ),
        "action": "python -m demo.reset",
        "trace": ["demo.reset.reset()"],
        "expected": {
            "counts.gstins":            500,
            "counts.invoices":          {"min": 3600, "max": 3800},
            "counts.planted_rings":     8,
        },
    },

    {
        "step": 2,
        "duration_sec": 30,
        "title": "Ingest & reconcile — what the tables show",
        "route": "/",
        "narrator": (
            "Case Queue populates. Reconciliation 2.0 emits typed events for "
            "every mismatch it can prove at the invoice level: missing filings, "
            "amount mismatches, cancelled suppliers, duplicates. "
            "Micro F1 0.961 on planted anomalies — we know this because the "
            "Model Card gates it."
        ),
        "route_alt": "/api/reconcile2/summary",
        "trace": ["GET /api/reconcile2/summary"],
        "expected": {
            "reconcile.total_events":   {"min": 1300, "max": 1600},
            "reconcile.by_outcome.MISSING_GSTR1":    {"min": 500, "max": 800},
            "reconcile.by_outcome.CANCELLED_SUPPLIER": {"min": 250, "max": 400},
            "reconcile.by_outcome.AMOUNT_MISMATCH":  {"min": 30, "max": 60},
            "reconcile.by_outcome.DUPLICATE":        {"min": 8, "max": 20},
        },
    },

    {
        "step": 3,
        "duration_sec": 30,
        "title": "What reconciliation misses — the hero ring's invoices are clean",
        "route": "/",
        "narrator": (
            f"The four invoices of ring {HERO_RING['planted_id']} produce "
            f"ZERO reconciliation events. They pass every pairwise check — "
            f"the amounts line up, the returns are filed, the tax is paid. "
            f"A table-based system stops here. The graph engine does not."
        ),
        "trace": [
            "GET /api/reconcile2/summary — hero invoices excluded from events list",
        ],
        "expected": {
            "hero.reconcile_events":    0,
        },
    },

    {
        "step": 4,
        "duration_sec": 60,
        "title": f"The graph engine catches ring {HERO_RING['planted_id']}",
        "route": f"/ring/{HERO_RING['detected_id']}",
        "narrator": (
            f"Ring Investigation. Cytoscape lays out the 4-node cycle in "
            f"cose-bilkent. Six-signal explainer: closure 1.00 (perfect "
            f"return), value-similarity 0.84 (paired supplies), temporal "
            f"compactness 0.97 (3-day window), network 0.75 (shared vehicle "
            f"{HERO_RING['common_vehicle']} and shared director "
            f"{HERO_RING['shared_director'].replace('DIR-500000-','')}). "
            f"Composed ring score {HERO_RING['expected_score']:.2f} — above the "
            f"0.55 gating threshold. Total GST at risk "
            f"₹{HERO_RING['total_ring_gst_rupees']:,.0f}."
        ),
        "trace": [
            f"GET /api/rings/{HERO_RING['detected_id']}",
        ],
        "expected": {
            "ring.detected":            True,
            "ring.members_count":       HERO_RING["size"],
            "ring.score":               {"min": 0.55, "max": 0.65},
            "ring.signals.C":           {"min": 0.95, "max": 1.01},
            "ring.signals.V":           {"min": 0.75, "max": 0.95},
            "ring.signals.T":           {"min": 0.90, "max": 1.01},
            "ring.signals.N":           {"min": 0.60, "max": 0.90},
        },
    },

    {
        "step": 5,
        "duration_sec": 45,
        "title": "Temporal replay — watch the ring form over 3 days",
        "route": f"/ring/{HERO_RING['detected_id']}",
        "narrator": (
            f"Scrub the timeline from left to right. Invoice "
            f"{HERO_RING['invoices'][0]} appears first on "
            f"{HERO_RING['closure_start_date']}. One per day, values inflated "
            f"~{int(HERO_RING['hop_inflation']*100)}% per hop, until "
            f"{HERO_RING['invoices'][-1]} closes the loop. The whole ring "
            f"lives inside {HERO_RING['temporal_window_days']} days — a "
            f"velocity signal only a temporal graph can express."
        ),
        "trace": [
            f"GET /api/rings/{HERO_RING['detected_id']} → edges[].date",
        ],
        "expected": {
            "ring.date_span_days":      {"min": 1, "max": 10},
            "ring.total_gst":           {"min": 150000, "max": 500000},
        },
    },

    {
        "step": 6,
        "duration_sec": 45,
        "title": "Break-edge counterfactual — which edge to freeze first",
        "route": f"/ring/{HERO_RING['detected_id']}",
        "narrator": (
            f"Open the Counterfactual tab. The break simulator drops each "
            f"ring edge in turn and rescores the ring under the same six-"
            f"signal rules. The recommendation is the edge whose removal "
            f"drops the score the most: invoice "
            f"{HERO_RING['break_edge_invoice']}. Enforcement action — "
            f"freeze that invoice's ITC — breaks the closure while leaving "
            f"the honest legs intact."
        ),
        "trace": [
            f"GET /api/rings/{HERO_RING['detected_id']} → break_edge, per_edge",
        ],
        "expected": {
            "ring.has_break_edge":      True,
        },
    },

    {
        "step": 7,
        "duration_sec": 45,
        "title": "Related vendors — the embedding finds ring co-members",
        "route": None,
        "narrator": (
            f"Query the graph-ML lookalike for one of the hero members "
            f"({HERO_RING['members'][0]}). Top-10 by cosine similarity "
            f"contains at least "
            f"{HERO_RING['embed_lookalike_min_hero_in_top10']} of the OTHER "
            f"3 hero members. The embedding never saw a 'ring' label — it "
            f"grouped them because they trade in the same graph "
            f"neighbourhood."
        ),
        "trace": [
            f"GET /api/embed/lookalike/{HERO_RING['members'][0]}?k=10",
        ],
        "expected": {
            "embed.hero_hits_in_top_10": {"min": HERO_RING["embed_lookalike_min_hero_in_top10"], "max": 3},
        },
    },

    {
        "step": 8,
        "duration_sec": 45,
        "title": "Model Card — every claim you just saw, with the number backing it",
        "route": "/model-card",
        "narrator": (
            "Nine headline metrics. Nine gated thresholds. All UNCHANGED. "
            "Ring recall 1.000. Reconcile F1 0.961. Risk AUC 0.937. "
            "Embed hit@10 0.912. Every number the demo just quoted is "
            "traceable to one of these cards — measured on the same "
            "dataset, deterministically, at this git commit. If a future "
            "refactor drops any of them, `benchmarks/run_all.py` returns "
            "exit code 1 and the CI fails."
        ),
        "trace": [
            "GET /api/benchmarks/model-card",
        ],
        "expected": {
            "model_card.overall_pass":  True,
            "model_card.card_count":    9,
        },
    },
]


def story_json() -> Dict[str, Any]:
    """Return the demo story in a shape the frontend can render."""
    return {
        "hero_ring": {k: v for k, v in HERO_RING.items()
                        if not k.startswith("expected_")},
        "total_duration_sec": sum(s["duration_sec"] for s in STORY),
        "steps": [
            {"step": s["step"], "title": s["title"],
                "duration_sec": s["duration_sec"], "route": s.get("route"),
                "narrator": s["narrator"], "trace": s["trace"]}
            for s in STORY
        ],
    }
