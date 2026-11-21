"""Business-network sampler.

Produces a directed graph over synthetic GSTIN nodes where an edge (a → b)
means "a is a possible supplier to b". Later, `transactions.py` places
actual invoices on these edges.

Two goals:

1. **Heavy-tailed hubs.** Real supplier networks look like power laws:
   most taxpayers have a few counterparts, a handful have thousands.
   We sample out-degree from a truncated power law.
2. **Geographic + sector coherence.** With probability `intra_state_pref`
   an edge stays within the same state; sector similarity further tilts
   selection so a steel supplier connects to construction buyers, not
   spice buyers.

The result is a list of `GSTINRecord` objects plus a `sample_counterparty`
helper the transaction generator calls.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .catalog import SECTOR_WEIGHTS, STATES
from .config import GenerationConfig
from .identifiers import (synth_director_id, synth_gstin, synth_pincode)
from .rng import derive, weighted_choice


@dataclass
class GSTINRecord:
    gstin_id: str
    name: str
    state_code: str
    state: str
    pincode: str
    sector: str
    status: str = "Active"                # or "CANCELLED"
    cancellation_date: Optional[str] = None
    incorp_date: str = ""
    directors: list[str] = field(default_factory=list)
    out_degree: int = 0                   # sampled expected fanout
    scenario: str = "NORMAL"              # tagged when planted for rings

    def to_row(self) -> dict:
        return {
            "gstin_id": self.gstin_id,
            "name": self.name,
            "state_code": self.state_code,
            "state": self.state,
            "pincode": self.pincode,
            "sector": self.sector,
            "status": self.status,
            "cancellation_date": self.cancellation_date or "",
            "incorp_date": self.incorp_date,
            "directors": ";".join(self.directors),
            "scenario": self.scenario,
        }


def _sample_state_code(rng: random.Random) -> str:
    return weighted_choice(rng, {s: STATES[s]["weight"] for s in STATES})


def _sample_sector(rng: random.Random) -> str:
    return weighted_choice(rng, SECTOR_WEIGHTS)


def _sample_out_degree(rng: random.Random, mean: float, alpha: float, max_deg: int) -> int:
    """Truncated Zipf-like degree draw with the given mean.

    We sample `k` from a Pareto with shape α, shifted to have mean ≈ `mean`,
    and cap at max_deg. Zero-fanout GSTINs are allowed — they are buyers-only.
    """
    if alpha <= 1.5:
        alpha = 1.5
    # inverse-CDF sampling of Pareto with x_min = 1
    u = rng.random()
    x = (1.0 - u) ** (-1.0 / (alpha - 1.0))
    # rescale so mean ≈ target
    scale = mean * (alpha - 2.0) / (alpha - 1.0) if alpha > 2.0 else mean * 0.5
    k = int(max(0, round(x * scale)))
    return min(k, max_deg)


def _synth_business_name(rng: random.Random, sector: str) -> str:
    prefix = rng.choice(["Sunrise", "Moonlight", "Star", "Horizon", "Zenith",
                          "Everest", "Ocean", "Crest", "Vertex", "Falcon",
                          "Sapphire", "Emerald", "Northern", "Southern",
                          "Bharat", "Aryan", "Vedic", "Tirupati"])
    kind_map = {
        "Metals": "Steels",
        "Electronics": "Electronics",
        "Chemicals": "Chemicals",
        "Textiles": "Textiles",
        "Food": "Foods",
        "Machinery": "Industries",
        "Automotive": "Motors",
        "Furniture": "Furnishings",
        "Personal care": "Beauty",
        "Stationery": "Papers",
        "Beverages": "Beverages",
        "Tobacco": "Tobacco Co",
    }
    kind = kind_map.get(sector, "Enterprises")
    suffix = rng.choice(["Pvt Ltd", "LLP", "Ltd", "& Co", "Enterprises", "Corp"])
    return f"{prefix} {kind} {suffix}"


def sample_gstins(cfg: GenerationConfig) -> list[GSTINRecord]:
    """Sample `cfg.n_gstins` taxpayer records, deterministically."""
    rng = derive(cfg.seed, "network.gstins")
    max_deg = max(20, int(cfg.avg_out_degree * 20))
    records: list[GSTINRecord] = []
    seen: set[str] = set()

    for i in range(cfg.n_gstins):
        # Ensure unique GSTIN — collisions are rare but possible with checksums.
        while True:
            sc = _sample_state_code(rng)
            gid = synth_gstin(rng, sc, entity_number=1)
            if gid not in seen:
                seen.add(gid)
                break
        sector = _sample_sector(rng)
        state_name = STATES[sc]["name"]
        pin = synth_pincode(rng, sc)
        # ~2 % cancelled suppliers for realism
        status = "CANCELLED" if rng.random() < 0.02 else "Active"
        cancel_dt = None
        if status == "CANCELLED":
            start = cfg.start_date()
            cancel_dt = start.replace(year=start.year).isoformat()
        deg = _sample_out_degree(rng, cfg.avg_out_degree, cfg.degree_power_law, max_deg)
        directors = [synth_director_id(rng, i * 3 + j) for j in range(rng.randint(1, 3))]
        records.append(GSTINRecord(
            gstin_id=gid,
            name=_synth_business_name(rng, sector),
            state_code=sc,
            state=state_name,
            pincode=pin,
            sector=sector,
            status=status,
            cancellation_date=cancel_dt,
            incorp_date=cfg.period_start,
            directors=directors,
            out_degree=deg,
        ))
    return records


def sample_edges(
    cfg: GenerationConfig,
    gstins: list[GSTINRecord],
) -> list[tuple[str, str]]:
    """Return supplier→buyer directed edges honoring intra-state + sector bias.

    Deterministic in the seed. We don't force network connectivity — a real
    network has isolated pockets. Rings will still be plantable because
    ring GSTINs are placed on their own edges.
    """
    rng = derive(cfg.seed, "network.edges")
    by_state: dict[str, list[GSTINRecord]] = {}
    for g in gstins:
        by_state.setdefault(g.state_code, []).append(g)
    all_gstins = gstins
    edges: set[tuple[str, str]] = set()
    for s in gstins:
        if s.status != "Active":
            continue
        for _ in range(s.out_degree):
            if rng.random() < cfg.intra_state_pref and len(by_state.get(s.state_code, [])) > 1:
                pool = by_state[s.state_code]
            else:
                pool = all_gstins
            b = rng.choice(pool)
            if b.gstin_id == s.gstin_id:
                continue
            edges.add((s.gstin_id, b.gstin_id))
    return list(edges)
