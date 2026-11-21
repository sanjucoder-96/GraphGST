# `realdata/` — Graph GST on real / public datasets

Evaluate Graph GST against **real / public** datasets, kept strictly separate
from `demo/` (synthetic story) and `benchmarks/` (gated synthetic metrics). It
never fabricates values, never fakes ground truth, and **cannot change the nine
gated benchmark metrics** (those run in-memory on `truth.json` and never touch
this code or Neo4j).

Read `docs/REAL_DATASETS.md` (what data exists) and `docs/REAL_DATA_VALIDATION.md`
(what the runs found) alongside this.

## TL;DR

```bash
# from graphgst/
python -m realdata.ingest   --source iron_dealers               # real, unsupervised
python -m realdata.evaluate --source iron_dealers --hop-max 4

python -m realdata.ingest   --source ibm_aml                    # labelled, supervised
python -m realdata.evaluate --source ibm_aml      --hop-max 6

# load into Neo4j under a traceable dataset id (additive; never auto-deletes):
python -m realdata.ingest   --source iron_dealers --dataset-id real_iron_dealers_v1
#   add --wipe for a real-data-only graph, --anonymize to pseudonymize ids,
#   --refresh to run rings+reconcile+risk+embeddings after load.

python -m pytest tests/test_realdata.py -q                      # tests (no Neo4j/network)
```

Reports land in `realdata/reports/<dataset>/` (`data_quality.md`,
`ingestion_report.json`, `evaluation_report.{md,json}`) plus a non-sensitive
`realdata/reports/latest.json`.

## Architecture

```
realdata/
  registry.py            # dataset name → adapter
  ingest.py              # CLI: adapter → quality → anonymize? → validate → CSVs → Neo4j?
  evaluate.py            # CLI: in-memory rings + risk + evidence chains + supervised (if labels)
  adapters/              # dataset-specific: raw columns → canonical objects
    iron_dealers.py  ibm_aml.py
  schemas/canonical.py   # CanonicalDataset/Entity/Txn, FieldMapping, graph_source + CSV emit
  normalization/
    normalize.py         # GSTIN-format validator + numeric/date coercion
    anonymize.py         # deterministic real-id → stable pseudonym (topology preserved)
  validation/quality.py  # comprehensive quality report + feature matrix + minimal cleaning
  loaders/neo4j_loader.py# dataset-tagged, integrity-checked, provenance-stamped Neo4j import
  raw/<dataset>/         # downloaded raw files (git-ignored)
  reports/<dataset>/     # generated reports (md/json kept; csv git-ignored)
```

## The two datasets

| name | what | download | labels | licence |
|---|---|---|---|---|
| `iron_dealers` | real Indian commercial-tax seller→buyer graph (799 dealers, 130,535 tx) | direct CSV | none → unsupervised | none (research/testing only) |
| `ibm_aml` | IBM AMLworld HI-Small labelled payment graph (5.08 M tx, 0.1 % laundering) | direct zip (~91 MB) | `Is Laundering` → supervised | CDLA-Sharing-1.0 |

Neither is real taxpayer data. Raw files auto-download on first run into
`realdata/raw/<dataset>/`.

## Canonical mapping (per adapter)

Each adapter declares a `MAPPING` of `SOURCE FIELD → CANONICAL FIELD → GRAPH
NODE/RELATIONSHIP → DOWNSTREAM ENGINE` (rendered into `data_quality.md`). Example
(Iron Dealers): `Seller ID → supplier_id → (:GSTIN) → rings/risk`,
`Buyer ID → buyer_id → (:Invoice)-[:BILLED_TO]->(:GSTIN)`,
`Value → taxable_value → Invoice.taxable_value`.

## Anonymization (privacy)

`--anonymize` replaces every identifier with a stable keyed-HMAC pseudonym
`ANON-<hex>` (topology preserved, imports idempotent, one-way). The salt comes
from `REALDATA_ANON_SALT` (env) — **set a secret salt for real sensitive data**
so pseudonyms are not derivable; the default is a fixed non-secret value for the
non-sensitive public datasets. Original ids/names are scrubbed, never persisted.

## Dataset isolation

The Neo4j load reuses the canonical `datagen.loader` (same graph model) and tags
every loaded node with `dataset_id`. Single Aura database ⇒ run one dataset at a
time for clean analysis (`--wipe` for real-data-only); `dataset_id` keeps every
node traceable and individually removable
(`MATCH (n {dataset_id:'real_iron_dealers_v1'}) DETACH DELETE n`). The default
load is **additive** and never deletes the demo automatically.

## Adding a dataset

1. `realdata/adapters/<name>.py` with `load(limit=None) -> CanonicalDataset` and a
   declared `MAPPING`; leave unknown fields `None`; set `label` only for a real
   ground-truth column; `is_real_taxpayer_data=False` for any public source.
2. Register it in `registry.py`. Everything downstream is free.

## Guarantees

- **Separation:** benchmarks/demo untouched; real-data output only under `realdata/`.
- **No fabrication:** missing fields stay `None`, measured as % missing, features disabled.
- **No fake ground truth:** precision/recall/AUC only when real labels exist.
- **Reuse:** existing graph model + engines; no second schema, no re-implemented detector.
