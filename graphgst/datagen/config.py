"""GenerationConfig — every knob the generator exposes.

We put every parameter here so a single dataclass fully describes a run.
`truth.json` embeds this config so that any dataset can be regenerated
byte-for-byte with `python -m datagen.cli --config truth.json`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional


@dataclass
class GenerationConfig:
    # ── scale ─────────────────────────────────────────────────────────────
    n_gstins: int = 1_000                # number of taxpayer nodes
    months: int = 6                      # how many monthly periods to simulate
    period_start: str = "2024-04-01"     # start of the first period (YYYY-MM-DD)

    # ── mix of transaction populations (must sum to 1.0) ─────────────────
    normal_share: float = 0.90           # invoices that reconcile cleanly
    recon_issue_share: float = 0.06      # invoices with a reconciliation defect
    circular_share: float = 0.03         # invoices that belong to a planted ring
    duplicate_share: float = 0.01        # duplicate / near-duplicate invoices

    # ── network topology ─────────────────────────────────────────────────
    avg_out_degree: float = 4.0          # mean fanout per supplier per period
    degree_power_law: float = 2.2        # heavier tail = more "hub" suppliers
    intra_state_pref: float = 0.7        # P(edge stays within the same state)

    # ── circular trading planting ────────────────────────────────────────
    n_rings: int = 15                    # how many rings to plant
    ring_size_min: int = 3
    ring_size_max: int = 8
    ring_temporal_window_days: int = 7   # ring completes within this window
    ring_value_inflation: float = 0.15   # +15% per hop (SC9-style)
    ring_common_vehicle: bool = True     # all EWBs use the same vehicle number
    ring_common_directors: bool = True   # ring members share Director nodes

    # ── reconciliation anomaly mix (conditional on recon_issue_share) ────
    anom_mix_missing_gstr1: float = 0.30
    anom_mix_missing_gstr3b: float = 0.15
    anom_mix_missing_tax: float = 0.10
    anom_mix_amount_mismatch: float = 0.20
    anom_mix_missing_ewb: float = 0.10
    anom_mix_cancelled_supplier: float = 0.05
    anom_mix_hsn_mismatch: float = 0.05
    anom_mix_date_mismatch: float = 0.05

    # ── economics ────────────────────────────────────────────────────────
    amount_lognorm_mu: float = 11.0      # ln(mean invoice value) ≈ ln(60,000)
    amount_lognorm_sigma: float = 1.1    # spread; 1.1 gives a nice long tail
    ewb_threshold_amount: float = 50_000.0  # EWB legally required above this

    # ── reproducibility ──────────────────────────────────────────────────
    seed: int = 42
    out_dir: str = "./datagen_output"

    # ── notes (embedded in truth.json for provenance) ────────────────────
    notes: str = ""

    # ────────────────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationConfig":
        # Only pass known fields to future-proof against extra keys in truth.json
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def start_date(self) -> date:
        y, m, d = map(int, self.period_start.split("-"))
        return date(y, m, d)

    # ── invariants ───────────────────────────────────────────────────────
    def validate(self) -> None:
        s = self.normal_share + self.recon_issue_share + self.circular_share + self.duplicate_share
        if abs(s - 1.0) > 1e-6:
            raise ValueError(
                f"Population shares must sum to 1.0; got {s:.6f}. "
                f"Adjust normal_share/recon_issue_share/circular_share/duplicate_share."
            )
        anom_mix = (
            self.anom_mix_missing_gstr1 + self.anom_mix_missing_gstr3b
            + self.anom_mix_missing_tax + self.anom_mix_amount_mismatch
            + self.anom_mix_missing_ewb + self.anom_mix_cancelled_supplier
            + self.anom_mix_hsn_mismatch + self.anom_mix_date_mismatch
        )
        if abs(anom_mix - 1.0) > 1e-6:
            raise ValueError(
                f"Anomaly mix must sum to 1.0; got {anom_mix:.6f}."
            )
        if self.n_gstins < max(20, self.n_rings * self.ring_size_max):
            raise ValueError(
                "n_gstins is too small to host requested rings without collisions."
            )
        if self.ring_size_min < 2 or self.ring_size_max < self.ring_size_min:
            raise ValueError("Invalid ring size bounds.")
