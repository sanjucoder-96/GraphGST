"""Canonical wire schemas (Pydantic v2) — the single source of truth for the
API contract the Investigator UI consumes.

Before this module the codebase carried the same concepts in several
incompatible shapes: three `Reason` dataclasses, four `Ring` payloads, two risk
scales (0-1 float vs 0-100 int) with three band vocabularies, and 47/48
endpoints returning bare `dict[str, Any]`. These models collapse the
investigation-path concepts into one typed contract so the frontend receives
predictable, strongly-typed structures.

Scope note: this is applied to the *investigation path* first — the Case API,
composed risk, rings, reconciliation events, related vendors, timeline. Other
legacy endpoints keep their ad-hoc dicts for now and are migrated incrementally;
see docs/INVESTIGATION_MODEL.md.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────
class Band(str, Enum):
    """Canonical composed-risk band. Single vocabulary everywhere (replaces the
    legacy HIGH/MEDIUM/LOW at 71/31 and the MED vs MEDIUM spelling drift).
    Thresholds live in risk.reasons.band_for: LOW <0.30 · MED <0.55 · HIGH <0.80
    · CRITICAL ≥0.80."""
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class InvestigationStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


# ── Evidence & Reason (the one canonical explanation contract) ───────────
class Evidence(BaseModel):
    """Points at the cited graph node(s) so the UI can highlight a subgraph."""
    node_type: Optional[str] = None
    node_id: Optional[Union[str, List[str]]] = None
    path: Optional[str] = None


class Reason(BaseModel):
    """One cite-able tell. Unifies risk.reasons.Reason and
    reconcile.outcomes.Reason. `scorer`/`contribution` are set by the composer."""
    name: str
    weight: float = 0.0
    detail: str = ""
    evidence: Dict[str, Any] = Field(default_factory=dict)
    scorer: Optional[str] = None
    contribution: Optional[float] = None


# ── Risk ─────────────────────────────────────────────────────────────────
class RiskScore(BaseModel):
    """Composed risk for one entity. `score` is canonical (0-1); `score_100` is
    the 0-100 integer mirror kept for the legacy index and dashboards."""
    score: float = Field(ge=0.0, le=1.0)
    score_100: int = Field(ge=0, le=100)
    band: Band
    contributions: Dict[str, float] = Field(default_factory=dict)
    reasons: List[Reason] = Field(default_factory=list)
    scorers_fired: List[str] = Field(default_factory=list)
    scorers_run: List[str] = Field(default_factory=list)
    materialized: bool = Field(
        default=False,
        description="True if read from a materialized GSTIN node; False if composed live.",
    )
    scored_at: Optional[str] = None


# ── Entity ───────────────────────────────────────────────────────────────
class EntityRef(BaseModel):
    gstin_id: str
    name: Optional[str] = None
    state_code: Optional[str] = None
    status: Optional[str] = None
    scenario: Optional[str] = None


# ── Ring ─────────────────────────────────────────────────────────────────
class RingEdge(BaseModel):
    """One hop of a ring: the invoice from one member to the next."""
    src: str
    dst: str
    invoice_id: str
    date: Optional[str] = None
    amount: float = 0.0
    gst_amount: float = 0.0
    vehicle_id: Optional[str] = None
    hsn: Optional[str] = None


class RingSummary(BaseModel):
    """One detected circular-trading ring. Supersedes DetectedRing/DetectedRingOut
    /persisted-dict/legacy-fraud-dict — and keeps `temporal` (which
    DetectedRingOut silently dropped)."""
    ring_id: str
    score: float
    band: Optional[Band] = None
    members: List[str] = Field(default_factory=list)
    member_count: int = 0
    invoices: List[str] = Field(default_factory=list)
    invoice_count: int = 0
    hops: int = 0
    date_span_days: int = 0
    total_gst: float = 0.0
    signals: Dict[str, float] = Field(default_factory=dict)
    contribution: Dict[str, float] = Field(default_factory=dict)
    share: Dict[str, float] = Field(default_factory=dict)
    break_edge: Optional[Dict[str, Any]] = None
    temporal: Optional[Dict[str, Any]] = None
    velocity_inr_per_day: Optional[float] = None
    edges: List[RingEdge] = Field(default_factory=list)  # per-hop invoice edges


# ── Reconciliation ───────────────────────────────────────────────────────
class MatchEventOut(BaseModel):
    """One reconciliation outcome. `role` says whether the case entity is the
    supplier or buyer on this event."""
    event_id: str
    outcome: str
    severity: str
    delta: Optional[float] = None
    at: Optional[str] = None
    invoice_id: Optional[str] = None
    supplier_gstin: Optional[str] = None
    buyer_gstin: Optional[str] = None
    role: Optional[str] = None  # 'supplier' | 'buyer'
    reasons: List[Reason] = Field(default_factory=list)


# ── Related vendors (embedding lookalikes, enriched) ─────────────────────
class RelatedVendor(BaseModel):
    gstin_id: str
    name: Optional[str] = None
    similarity: float
    risk_score: Optional[float] = None
    band: Optional[Band] = None
    shares_ring: bool = False


# ── Exposure ─────────────────────────────────────────────────────────────
class ExposureBreakdown(BaseModel):
    """ITC value the entity's own non-compliant ISSUED invoices put at risk
    (supplier-side): the tax credit its buyers may be denied because of this
    entity's blocking outcomes. `total_inr` and `invoice_count` are over DISTINCT
    invoices; `by_outcome` buckets may overlap and need not sum to the total."""
    total_inr: float = 0.0
    by_outcome: Dict[str, float] = Field(default_factory=dict)
    invoice_count: int = 0


# ── Timeline ─────────────────────────────────────────────────────────────
class TimelineEvent(BaseModel):
    date: str
    kind: str            # 'invoice' | 'ring_hop' | 'filing' | ...
    label: str = ""
    ref: Optional[str] = None
    amount: Optional[float] = None
    gst: Optional[float] = None


# ── Materialization / staleness ──────────────────────────────────────────
class MaterializationInfo(BaseModel):
    materialized_at: Optional[str] = None
    stale: bool = True
    # content-sensitive fingerprint: mixed int/float/str aggregates (see
    # risk.materialize.current_fingerprint)
    fingerprint: Dict[str, Any] = Field(default_factory=dict)
    current_fingerprint: Dict[str, Any] = Field(default_factory=dict)
    n_scored: int = 0
    composer_version: Optional[str] = None


# ── Case (the coherent investigation object) ─────────────────────────────
class CaseListItem(BaseModel):
    case_id: str
    gstin_id: str
    name: Optional[str] = None
    state_code: Optional[str] = None
    status: Optional[str] = None
    scenario: Optional[str] = None
    risk_score: float = Field(ge=0.0, le=1.0)
    band: Band
    exposure_inr: float = 0.0
    ring_ids: List[str] = Field(default_factory=list)
    ring_count: int = 0
    top_reasons: List[str] = Field(default_factory=list)
    primary_signal: Optional[str] = None
    investigation_status: InvestigationStatus = InvestigationStatus.OPEN


class CaseList(BaseModel):
    count: int
    band_counts: Dict[str, int] = Field(default_factory=dict)
    materialization: MaterializationInfo
    cases: List[CaseListItem] = Field(default_factory=list)


class Case(BaseModel):
    """Everything the investigation workspace needs, in ONE response — so the
    frontend never reassembles a case from 6-10 unrelated calls."""
    case_id: str
    entity: EntityRef
    risk: RiskScore
    exposure: ExposureBreakdown
    rings: List[RingSummary] = Field(default_factory=list)
    reconciliation: List[MatchEventOut] = Field(default_factory=list)
    related_vendors: List[RelatedVendor] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    subgraph: Optional[Dict[str, Any]] = None
    investigation_status: InvestigationStatus = InvestigationStatus.OPEN
    latest_activity: Optional[str] = None
    generated_at: Optional[str] = None
    materialization: MaterializationInfo


# ── Case workflow status ─────────────────────────────────────────────────
class CaseStatusUpdate(BaseModel):
    """PATCH body — set an investigation's workflow status."""
    status: InvestigationStatus


class CaseStatusResult(BaseModel):
    case_id: str
    investigation_status: InvestigationStatus
    updated_at: Optional[str] = None


# ── Refresh result ───────────────────────────────────────────────────────
class RefreshResult(BaseModel):
    ok: bool = True
    rings_persisted: int = 0
    events_persisted: int = 0
    gstins_scored: int = 0
    materialized_at: Optional[str] = None
    fingerprint: Dict[str, Any] = Field(default_factory=dict)
    elapsed_sec: float = 0.0
