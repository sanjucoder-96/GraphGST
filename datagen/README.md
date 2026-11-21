# datagen — Synthetic Indian GST Dataset Generator

A pure-Python package that produces a plausible, deterministic Indian GST
dataset — GSTINs, invoices, GSTR-1 / 2B / 3B, TaxPayments, e-Way Bills, IRNs,
buyer-side Purchase Register lines — together with a `truth.json` that
labels every planted anomaly and circular-trading ring.

Everything downstream of `datagen` (reconciliation benchmarks, ring detection
recall, ML AUC) depends on this ground-truth file. If you skip datagen, none
of those numbers can be measured; you can only demo.

## What "ground truth" means here

Every deviation from a clean, matched invoice is stamped with a label
in `truth.json`:

```json
{
  "planted_anomalies": [
    {"type": "AMOUNT_MISMATCH", "invoice_id": "INV-...", "delta_amount": -12345},
    {"type": "MISSING_GSTR1",   "invoice_id": "INV-..."},
    {"type": "DUPLICATE",       "of_invoice": "INV-..."}
  ],
  "planted_rings": [
    {
      "ring_id": "RING-42-00003", "size": 5, "members": ["27...", "27...", ...],
      "invoices": ["INV-...", ...], "common_vehicle": "KA01AB1234",
      "shared_director": "DIR-000042-Ravi-Kumar", "total_ring_gst": 234567.0
    }
  ]
}
```

Given this file, you can score any detector:

```
precision = |detector_rings ∩ planted_rings| / |detector_rings|
recall    = |detector_rings ∩ planted_rings| / |planted_rings|
```

## Quick start

```bash
# 3K GSTINs · 6 months · seed 42 → ./datagen_output/
python -m datagen.cli \
  --n-gstins 3000 --months 6 --seed 42 \
  --normal-share 0.90 --recon-issue-share 0.06 \
  --circular-share 0.03 --duplicate-share 0.01 \
  --n-rings 15 --ring-size-min 3 --ring-size-max 8 \
  --out-dir ./datagen_output
```

Output files (all in `--out-dir`):

| File | Rows |
|---|---|
| `gstins.csv` | 1 per GSTIN |
| `invoices.csv` | 1 per invoice |
| `ewb.csv` | 1 per invoice with EWB |
| `irn.csv` | 1 per invoice |
| `pr.csv` | 1 per buyer-side book entry |
| `gstr1.csv` | 1 per (supplier, period) that filed |
| `gstr3b.csv` | 1 per (supplier, period) that filed |
| `gstr2b.csv` | 1 per (buyer, period) |
| `taxpayments.csv` | 1 per cleared challan |
| `truth.json` | 1 (the ground truth) |

## Loading into Neo4j

Two paths:

**A) HTTP.** With the backend running and an admin token set:

```bash
curl -X POST \
     -H "X-Admin-Token: $ADMIN_TOKEN" \
     "http://localhost:8000/api/datagen/load?dir=$(pwd)/datagen_output"
```

**B) Direct Python.** From `graphgst/`:

```python
from datagen.loader import load_directory
load_directory("./datagen_output")
```

Both call `seeder.create_constraints()` first, so uniqueness + range
indexes are in place before batch MERGE.

## Reproducibility

- **Same `(seed, config)` → byte-identical output.** All RNG draws go
  through `datagen.rng.derive(seed, tag)`, so adding a new anomaly stream
  doesn't shift previously-generated IDs.
- **Configuration is embedded in truth.json.** Regenerate any dataset
  with `python -m datagen.cli --config path/to/truth.json`.
- **CSV serialization is stable.** Column order is fixed per file;
  `lineterminator="\n"`; UTF-8 without BOM.

## Design notes for a CS student

- **Network model.** Supplier→buyer edges are sampled by a power-law
  out-degree distribution (`degree_power_law` α ≈ 2.2 → heavy tail:
  most suppliers ship to a few buyers, a handful ship to thousands).
  Same-state preference is `intra_state_pref ∈ [0, 1]`.
- **Invoice amounts.** Log-normal (mu ≈ 11, sigma ≈ 1.1) → mean ≈ ₹60K
  with a long tail up to ₹10M+.
- **Rings.** Members are sampled from the same state to be geographically
  tight; the same `Vehicle` node is reused if `--ring-common-vehicle`;
  a single `Director` is shared across all ring members if
  `--ring-common-directors`. Invoice values are inflated by
  `ring_value_inflation` per hop (default 15 %) — this is the SC9
  signature.
- **Reconciliation defects.** Eight types, weighted by
  `anom_mix_*` fields (must sum to 1). Duplicates come in two flavors:
  exact (same invoice_id booked twice) and near (invoice_id lightly
  mangled, amount ± ₹1).

## Disclaimer

This generator produces **synthetic** data that looks like Indian GST
records. It is intended for algorithm development and demos. The
identifiers, HSN → rate mapping, and legal narratives are not authoritative;
never treat generator output as a real tax filing.
