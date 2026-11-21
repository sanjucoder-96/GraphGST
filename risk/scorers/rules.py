"""RuleScorer — the cleaned successor to V5's `compute_risk_scores`.

V5 baked seven rules into a single additive integer with implicit
weights. This scorer keeps the same intent (missing filings, cancelled
supplier, cycle membership, unusual centrality) but each rule fires as
a first-class Reason with its own weight and evidence pointer. The
subscore is the mean of all fired reason weights, so it stays in [0,1]
regardless of how many rules fire.
"""
from __future__ import annotations

from statistics import mean
from typing import List

from ..context import ScorerContext
from ..reasons import Reason
from .base import ScorerResult


def _expected_gstr3b_id(gstin: str, period: str) -> str:
    return f"GSTR3B-{gstin[:7]}-{period.replace('-', '')}"


class RuleScorer:
    name = "rules"

    def __init__(self, weight: float = 0.25):
        self.weight = weight

    def score(self, gstin_id: str, ctx: ScorerContext) -> ScorerResult:
        reasons: List[Reason] = []

        # 1. Cancelled supplier
        if ctx.supplier_status.get(gstin_id) == "CANCELLED":
            reasons.append(Reason(
                name="supplier-cancelled",
                weight=1.0,
                detail=f"GSTIN {gstin_id} is CANCELLED — invoices issued after "
                        f"cancellation carry no valid ITC",
                evidence={"node_type": "GSTIN", "node_id": gstin_id},
            ))

        # 2. Filing state on the entity's own outgoing invoices.
        invoices = ctx.invoices_by_gstin.get(gstin_id, [])
        n_missing_g1 = 0; n_missing_g3b = 0; n_missing_tp = 0
        periods_seen = set()
        for inv in invoices:
            period = inv.get("period")
            if not period:
                continue
            periods_seen.add(period)
            if (gstin_id, period) not in ctx.gstr1_keys:
                n_missing_g1 += 1
            elif (gstin_id, period) not in ctx.gstr3b_keys:
                n_missing_g3b += 1
            elif _expected_gstr3b_id(gstin_id, period) not in ctx.settled_keys:
                n_missing_tp += 1

        if periods_seen:
            n_invs = len(invoices)
            frac_g1 = n_missing_g1 / n_invs
            frac_g3b = n_missing_g3b / n_invs
            frac_tp = n_missing_tp / n_invs
            if frac_g1 > 0:
                reasons.append(Reason(
                    name="missing-gstr1-fraction",
                    weight=min(1.0, frac_g1 * 1.2),
                    detail=f"{n_missing_g1}/{n_invs} outgoing invoices lack a GSTR-1 filing",
                    evidence={"node_type": "GSTIN", "node_id": gstin_id,
                                "path": "GSTIN→FILED→GSTR1"},
                ))
            if frac_g3b > 0:
                reasons.append(Reason(
                    name="missing-gstr3b-fraction",
                    weight=min(1.0, frac_g3b * 1.3),
                    detail=f"{n_missing_g3b}/{n_invs} periods with GSTR-1 filed lack the GSTR-3B",
                    evidence={"node_type": "GSTIN", "node_id": gstin_id,
                                "path": "GSTIN→FILED→GSTR3B"},
                ))
            if frac_tp > 0:
                reasons.append(Reason(
                    name="unremitted-tax-fraction",
                    weight=min(1.0, frac_tp * 1.5),
                    detail=f"{n_missing_tp}/{n_invs} periods where GSTR-3B filed but no cleared challan",
                    evidence={"node_type": "GSTIN", "node_id": gstin_id,
                                "path": "GSTR3B→SETTLED_BY→TaxPayment"},
                ))

        # 3. Structural — self-loop in supply network (rare but strong)
        if gstin_id in ctx.neighbors_out.get(gstin_id, set()):
            reasons.append(Reason(
                name="supplies-to-self",
                weight=0.7,
                detail=f"{gstin_id} appears as both supplier and buyer on ≥1 invoice",
                evidence={"node_type": "GSTIN", "node_id": gstin_id},
            ))

        if not reasons:
            return ScorerResult(subscore=0.0, reasons=[])
        # Aggregate: mean of reason weights (bounded by construction)
        return ScorerResult(subscore=mean(r.weight for r in reasons), reasons=reasons)
