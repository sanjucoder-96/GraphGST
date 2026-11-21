"""`python -m realdata.ingest --source <dataset> [--dataset-id <id>]`

The real-data ingestion pipeline:
  1. adapter        (real columns → CanonicalDataset)
  2. quality audit  (comprehensive REAL DATA QUALITY REPORT — reports, never drops)
  3. anonymize      (optional, --anonymize: real ids → stable pseudonyms)
  4. validate       (drop only structurally-impossible rows, counted; prune orphans)
  5. canonical CSVs (exact datagen/loader schema) + reports
  6. Neo4j load     (optional, when --dataset-id given: dataset-tagged, integrity-checked,
                     provenance-stamped; additive unless --wipe)

Steps 1–5 need neither Neo4j nor the network beyond the one-time raw download,
and cannot change the nine gated benchmarks.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from .registry import load_dataset, ADAPTERS
from .schemas.canonical import write_canonical_csvs, mapping_markdown
from .validation.quality import (
    validate_and_normalize, feature_availability, matrix_markdown,
    quality_report, quality_markdown,
)
from .normalization.anonymize import anonymize_dataset


def run(dataset: str, limit=None, out_dir=None, anonymize=False,
        dataset_id=None, wipe=False, refresh=False) -> dict:
    ds = load_dataset(dataset, limit=limit)

    # (2) comprehensive quality audit on the data AS LOADED (before any cleaning)
    q = quality_report(ds)

    # (3) optional anonymization
    if anonymize:
        ds = anonymize_dataset(ds)

    # (4) minimal cleaning the engines require (counted, never silent)
    ds, rep = validate_and_normalize(ds)

    out_dir = out_dir or os.path.join(os.path.dirname(__file__), "reports", dataset)
    os.makedirs(out_dir, exist_ok=True)

    csv_counts = write_canonical_csvs(ds, out_dir, dataset_id=dataset_id)
    features = feature_availability(ds)

    report = {
        "dataset": {"name": ds.name, "source_url": ds.source_url, "license": ds.license,
                    "description": ds.description, "notes": ds.notes,
                    "is_real_taxpayer_data": ds.is_real_taxpayer_data,
                    "anonymized": ds.anonymized,
                    "field_availability": ds.field_availability},
        "quality": asdict(q),
        "validation": asdict(rep),
        "canonical_csv_rows": csv_counts,
        "feature_availability": [f.__dict__ for f in features],
        "field_mapping": [m.__dict__ for m in ds.mapping],
    }
    with open(os.path.join(out_dir, "ingestion_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    md = [f"# Data quality — {ds.name}", "",
          f"- **Source:** {ds.source_url}", f"- **License:** {ds.license}",
          f"- **Real taxpayer data:** {'yes' if ds.is_real_taxpayer_data else 'NO (public / anonymised / synthetic)'}",
          f"- **Anonymized:** {'yes' if ds.anonymized else 'no'}", "",
          quality_markdown(q, ds), "",
          "## Canonical field mapping", "", mapping_markdown(ds), "",
          "## Feature availability", "", matrix_markdown(features), ""]
    if rep.notes:
        md += ["## Cleaning notes", ""] + [f"- {n}" for n in rep.notes]
    with open(os.path.join(out_dir, "data_quality.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"[ingest] {ds.name}: {rep.entities_out} entities, {rep.txns_out} txns "
          f"({rep.txns_rejected} rejected {rep.reject_reasons or ''}) -> {out_dir}")

    result = {"report": report}
    # (6) optional Neo4j load
    if dataset_id:
        from .loaders.neo4j_loader import load_to_neo4j
        print(f"[ingest] loading into Neo4j as dataset_id='{dataset_id}' (wipe={wipe}, refresh={refresh})...")
        loaded = load_to_neo4j(ds, dataset_id, rep, out_dir, wipe=wipe, refresh=refresh)
        print(f"[ingest] Neo4j: {loaded['integrity']}")
        result["neo4j"] = loaded
    return result


def main():
    ap = argparse.ArgumentParser(description="Ingest a real/public dataset into the GST canonical schema.")
    ap.add_argument("--source", "--dataset", dest="dataset", required=True, choices=sorted(ADAPTERS))
    ap.add_argument("--limit", type=int, default=None, help="cap rows (for quick tests)")
    ap.add_argument("--anonymize", action="store_true", help="pseudonymize identifiers (topology preserved)")
    ap.add_argument("--dataset-id", default=None,
                    help="load into Neo4j under this id (e.g. real_iron_dealers_v1); omit to skip Neo4j")
    ap.add_argument("--wipe", action="store_true", help="DETACH DELETE the graph first (never automatic)")
    ap.add_argument("--refresh", action="store_true", help="run refresh_intelligence after the Neo4j load")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.wipe and not args.dataset_id:
        ap.error("--wipe only applies with --dataset-id (a Neo4j load)")
    run(args.dataset, limit=args.limit, out_dir=args.out, anonymize=args.anonymize,
        dataset_id=args.dataset_id, wipe=args.wipe, refresh=args.refresh)


if __name__ == "__main__":
    main()
