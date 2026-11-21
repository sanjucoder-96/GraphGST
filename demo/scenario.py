"""The demo's controlled hero scenario.

We use the standard Phase 1 datagen at seed=42 and identify RING-42-00000
as the "hero" — a 4-member Maharashtra beverage-trade ring that reads
as reconciled-clean at the invoice level but forms a closed cycle with
shared vehicle + director + 15%/hop value inflation.

Every constant in this module is the value the actual datagen produces
at seed=42. If you change datagen, run `python -m demo.probe_hero` to
re-derive these constants, then update this file. The demo verifier
(`demo/verify.py`) will fail loudly if the two ever drift apart.
"""
from __future__ import annotations

from typing import Any, Dict, Final

# ── Dataset config ──────────────────────────────────────────────────────
# These four knobs FULLY DETERMINE the demo dataset. Do not change them
# lightly — every story assertion is calibrated for these values.
DEMO_SEED: Final[int] = 42
DEMO_N_GSTINS: Final[int] = 500
DEMO_MONTHS: Final[int] = 3
DEMO_N_RINGS: Final[int] = 8


# ── Hero ring — the protagonist of the story ────────────────────────────
# Constants derived from `demo.probe_hero` on datagen at the above seed.
HERO_RING: Final[Dict[str, Any]] = {
    "planted_id":       "RING-42-00000",
    "detected_id":      "R-68383043e2e47603",     # sha1[:16] of canonical members
    "size":             4,
    "state":            "Maharashtra",             # all members are 27xxx
    "hsn":              "2202",                    # aerated waters
    "hsn_description":  "aerated beverages",
    "members": [
        "27IBZFN9011M1ZP",
        "27GUTPJ9684R1ZR",
        "27CYFCE3784B1ZW",
        "27KKRPO1560C1ZL",
    ],
    "invoices": [
        "INV-202406-RING-000-00",
        "INV-202406-RING-000-01",
        "INV-202406-RING-000-02",
        "INV-202406-RING-000-03",
    ],
    "common_vehicle":   "TN84WC2559",
    "shared_director":  "DIR-500000-Meera-Kumar",
    "hop_inflation":    0.15,                       # +15 % per hop
    "temporal_window_days": 3,
    "closure_start_date": "2024-06-19",
    "total_ring_gst_rupees": 219229.14,
    # What the ring engine will say about it (measured)
    "expected_score":       0.593,
    "expected_signals": {"C": 1.00, "V": 0.84, "T": 0.97, "R": 0.0, "N": 0.75, "H": 0.0},
    # Recommended enforcement edge (from counterfactual)
    "break_edge_invoice":   "INV-202406-RING-000-02",
    # How embed lookalike behaves (measured)
    # For query = first member: 2 of the 4 hero members appear in top-10.
    "embed_lookalike_min_hero_in_top10": 2,
}


def hero_gstin_prefix(idx: int) -> str:
    """Convenience for the story: HERO_RING["members"][idx]."""
    return HERO_RING["members"][idx]
