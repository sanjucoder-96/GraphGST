"""Load a real dataset into the EXISTING Graph GST Neo4j model, with dataset
isolation + provenance (Phase 5).

We reuse the canonical `datagen.loader` (same node/relationship model — no
second graph) and then:
  * tag every loaded source node with `dataset_id` (e.g. real_iron_dealers_v1)
    so it is traceable and individually removable
    (`MATCH (n {dataset_id:$id}) DETACH DELETE n`);
  * verify graph integrity (every invoice has a supplier + buyer edge);
  * stamp a singleton `:Dataset(active)` provenance node read by
    GET /api/dataset/current → the console's PUBLIC DATASET banner.

Isolation model (single Aura database): analysis engines query all
GSTIN/Invoice nodes, so run ONE dataset at a time for clean analysis — use
`--wipe` for a real-data-only graph. The default is ADDITIVE and never deletes
the existing graph automatically. Loading real data does NOT affect the nine
gated benchmarks (they run in-memory on truth.json and never read Neo4j).
"""
from __future__ import annotations

import os
from dataclasses import asdict
from typing import Optional

from ..schemas.canonical import CanonicalDataset, write_canonical_csvs
from ..validation.quality import ValidationReport, feature_availability


def _verify_integrity(dataset_id: str) -> dict:
    from db import run_query
    g = run_query("MATCH (g:GSTIN {dataset_id:$d}) RETURN count(g) AS c", {"d": dataset_id})[0]["c"]
    i = run_query("MATCH (i:Invoice {dataset_id:$d}) RETURN count(i) AS c", {"d": dataset_id})[0]["c"]
    e = run_query(
        "MATCH (:GSTIN {dataset_id:$d})-[:ISSUED_INVOICE]->(i:Invoice {dataset_id:$d}) "
        "RETURN count(*) AS c", {"d": dataset_id})[0]["c"]
    b = run_query(
        "MATCH (i:Invoice {dataset_id:$d})-[:BILLED_TO]->(:GSTIN {dataset_id:$d}) "
        "RETURN count(*) AS c", {"d": dataset_id})[0]["c"]
    dangling = run_query(
        "MATCH (i:Invoice {dataset_id:$d}) "
        "WHERE NOT (()-[:ISSUED_INVOICE]->(i)) OR NOT ((i)-[:BILLED_TO]->()) "
        "RETURN count(i) AS c", {"d": dataset_id})[0]["c"]
    return {"gstins": g, "invoices": i, "issued_edges": e, "billed_edges": b,
            "invoices_missing_an_edge": dangling,
            "integrity_ok": (dangling == 0 and e == i and b == i)}


def _stamp_provenance(ds: CanonicalDataset, dataset_id: str, rep: ValidationReport,
                      q=None) -> None:
    from db import run_write
    features = feature_availability(ds)
    warnings = [f.reason for f in features if f.can_run in ("NO", "PARTIAL")]
    dr = ("—", "—")
    dated = [t.date[:10] for t in ds.txns if t.date]
    if dated:
        dr = (min(dated), max(dated))
    run_write(
        """
        MERGE (d:Dataset {id:'active'})
        SET d.name=$name, d.dataset_id=$did, d.kind='PUBLIC_DATASET',
            d.source=$source, d.license=$license, d.description=$description,
            d.is_real_taxpayer_data=$real, d.anonymized=$anon,
            d.entities=$entities, d.transactions=$txns,
            d.date_min=$dmin, d.date_max=$dmax,
            d.warnings=$warnings, d.notes=$notes, d.ingested_at=datetime()
        """,
        {"name": ds.name, "did": dataset_id, "source": ds.source_url,
         "license": ds.license, "description": ds.description,
         "real": ds.is_real_taxpayer_data, "anon": ds.anonymized,
         "entities": rep.entities_out, "txns": rep.txns_out,
         "dmin": dr[0], "dmax": dr[1], "warnings": warnings, "notes": ds.notes},
    )


def load_to_neo4j(ds: CanonicalDataset, dataset_id: str, rep: ValidationReport,
                  out_dir: str, wipe: bool = False, refresh: bool = False) -> dict:
    """Load a validated CanonicalDataset into Neo4j under `dataset_id`."""
    from db import run_write
    write_canonical_csvs(ds, out_dir, dataset_id=dataset_id)

    if wipe:
        run_write("MATCH (n) DETACH DELETE n")

    from datagen.loader import load_directory
    stats = load_directory(out_dir)

    # Tag every loaded source node with the dataset_id (traceability + isolation).
    # The canonical CSVs wrote scenario=dataset_id, so this targets exactly them.
    for label in ("GSTIN", "Invoice"):
        run_write(f"MATCH (n:{label} {{scenario:$did}}) SET n.dataset_id=$did", {"did": dataset_id})

    integrity = _verify_integrity(dataset_id)
    _stamp_provenance(ds, dataset_id, rep)

    if refresh:
        try:
            from risk.materialize import refresh_intelligence
            refresh_intelligence()
        except Exception as ex:  # noqa: BLE001
            integrity["refresh_error"] = str(ex)

    return {"load": stats, "integrity": integrity, "dataset_id": dataset_id}
