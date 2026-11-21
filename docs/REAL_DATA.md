# Real / Public Data Evaluation

Graph GST ships with a **synthetic** demo (`datagen/`, seed 42) and a
**benchmark** suite (`benchmarks/`) that both run on generated data with known
ground truth. This document is about the third track — `realdata/` — which lets
you point the engines at **real / public datasets**, honestly.

It is written to be readable if you have never seen this project before.

---

## 1. The uncomfortable truth first: real GST transaction data is not public

We researched this thoroughly (government portals, Kaggle, academic papers,
GitHub, open-data repos). The conclusion is **categorical**:

> **There is no public dataset of real, taxpayer-level GST invoices** — i.e.
> individual invoices with real GSTINs, line amounts, and above all
> **supplier → buyer links** — and there legally cannot be one.

Three walls make this permanent, not accidental:

1. **CGST Act §158** bars a public servant from disclosing the particulars in
   any return / statement / account furnished under the Act. The only carve-out
   is for **aggregate** data in the public interest.
2. **CGST Act §158A** (Finance Act 2023) lets GSTN share return / e-invoice
   data **only** with other notified government systems and **only with the
   taxpayer's consent** — a consent-gated government pipe, the opposite of open
   data.
3. **GSTN's data policy** keeps the data encrypted, India-localised, and not for
   sale.

The only lawful **public** taxpayer-level surface is the GST portal's
**"Search Taxpayer"** lookup: you must already know a GSTIN, and it returns
**registration metadata only** (legal name, state, registration/cancellation
dates, filing status). **No invoices, no amounts, no counterparties → zero
supplier→buyer edges.** Everything else the government publishes (gst.gov.in
statistics, data.gov.in collections) is **aggregate** (state × month revenue,
filing counts) with no entity identifiers.

The real transaction data (GSTR-1/2A, e-invoice IRN JSON) exists inside
GSTN/IRP but is **authenticated per-taxpayer** — accessible only to a taxpayer
for their own GSTIN. **We do not scrape authenticated portals or use leaked
data**, and neither should you.

**Implication:** the ring detector, reconciliation, and ITC-mismatch logic
cannot be run on any officially-published Indian GST dataset. So we do the next
best, honest thing.

---

## 2. What we use instead, and why it's legitimate

We evaluate on **two complementary public datasets**, chosen to map onto the two
kinds of evaluation you can honestly do:

| Dataset | What it is | Why it's here | Evaluation mode |
|---|---|---|---|
| **Iron Dealers** | A **real** (non-synthetic) Indian commercial-tax dealer transaction graph — 130,535 directed seller→buyer transactions between 799 anonymised dealers, from published circular-trading research. | The closest thing to real GST data: genuine tax transactions in the exact "who sold to whom" shape the ring detector needs. | **Unsupervised** — it has no fraud labels, so we report *structure*, never precision/recall. |
| **IBM AMLworld (HI-Small)** | A published, **labelled** financial-crime payment graph (Altman et al., NeurIPS 2023): 5.08 M directed transfers, 0.1 % flagged `Is Laundering`, with a "simple cycle" typology = ground-truth circular trading. | The strongest legally-usable **labelled** directed graph. It lets the ring detector get a **real ground-truth score** on data it did not generate. | **Supervised** — labels present, so we report precision / recall / AUC. |

**Honesty flags baked in:**

- **Neither is real taxpayer data.** Iron Dealers is *real but anonymised*
  (dealers are integers, not GSTINs); AMLworld is *realistic synthetic* and is
  *money-laundering, not GST*. The console always shows a **PUBLIC DATASET**
  banner — synthetic data is never dressed up as real, nor the reverse.
- **Canonical ids are obviously not GSTINs.** Every entity id is
  `<TAG>:<source_id>` (e.g. `IRONDLR:1309`), which no real 15-character GSTIN can
  match.
- **"Laundering" ≠ "GST circular trading".** It is a documented *analog*. The
  supervised report carries that caveat inline.

Licences: Iron Dealers has **no licence file** (treated as all-rights-reserved —
research/testing only, ask the author before redistributing); AMLworld is
**CDLA-Sharing-1.0** (commercial OK, share-alike).

---

## 3. How a real dataset flows through the system

```
   public CSV / zip
        │  realdata/<name>/adapter.py   (dataset-specific: columns → canonical)
        ▼
   CanonicalEntity[] + CanonicalTxn[]   (realdata/schema.py — nothing fabricated)
        │  realdata/validate.py          (drop self-loops/bad rows, prune orphans,
        │                                 measure missing-field %, feature matrix)
        ▼
   CanonicalDataset  ─────────────┬───────────────────────────────┐
        │                         │                               │
        │ write_canonical_csvs    │ to_ring_graph_source           │ to_risk_graph_source
        ▼                         ▼                               ▼
   gstins.csv + invoices.csv   rings.engine.run_pipeline      risk composer
   (EXACT datagen schema)      (in-memory, persist=False)     (in-memory, partial)
        │                         │                               │
        │ realdata/load_neo4j.py  └──────────► evaluation_report.{json,md} ◄──┘
        ▼                                        (graph stats, rings, temporal,
   datagen.loader.load_directory                  supervised metrics IF labels)
        ▼
   the SAME Neo4j graph model the whole app reads
   (GSTIN)-[:ISSUED_INVOICE]->(Invoice)-[:BILLED_TO]->(GSTIN)
   + a :Dataset(active) provenance node → GET /api/dataset/current → console banner
```

We deliberately **reuse the existing graph model and engines** — no second
schema, no re-implemented detector. The adapter's only job is *columns →
canonical objects*; everything after that is the real product code.

---

## 4. What Graph GST can and cannot test on this data

Both datasets are directed transaction graphs **without GST filings, tax splits,
or e-way bills**, so the same capabilities are on/off (temporal and labels
differ):

| Feature | Iron Dealers | IBM AMLworld | Why |
|---|:--:|:--:|---|
| Ring / circular-trade detection | **YES** | **YES** | needs directed supplier→buyer edges — present |
| GSTIN / entity relationships | **YES** | **YES** | graph structure present |
| Graph embeddings (structural) | **YES** | **YES** | graph structure present |
| Risk scoring (composed) | **PARTIAL** | **PARTIAL** | ring+temporal fire; reconcile/rules need filings the data lacks |
| Temporal analysis | **NO** | **YES** | Iron Dealers has no dates; AMLworld does |
| Reconciliation (GSTR-1↔2B↔3B) | **NO** | **NO** | no GSTR filing rows in either source |
| ITC-mismatch detection | **NO** | **NO** | needs statutory tax + returns |
| Ground-truth evaluation | **NO** | **YES** | Iron Dealers is unlabeled; AMLworld has `Is Laundering` |

**Why missing data matters (and why we don't fake it):** a real dataset almost
never has everything the synthetic generator invents. When a field is absent we
keep it `None`, record the % missing, and **disable the features that genuinely
need it** — rather than fabricate a value and report a number that isn't real.
That is the whole point of the feature-availability matrix.

**Why no labels limits evaluation:** with no ground truth you *cannot* honestly
report ROC-AUC / F1 — there is nothing to be right or wrong against. So on Iron
Dealers we report **graph statistics and detected structures** (an *unsupervised
real-world analysis*), and we clearly label it as such. Only AMLworld, which
carries real labels, gets a **supervised** score.

---

## 5. Results from the real-data runs (measured facts)

> Everything in this section is produced by the reproducible commands in §6 and
> written to `realdata/<name>/processed/evaluation_report.{json,md}`. Numbers are
> **measured**, not asserted.

### 5a. Iron Dealers — real, unsupervised

- **Graph:** 799 entities, 130,535 transactions, 5,358 distinct directed edges,
  ₹90.47 billion total transaction value.
- **Structure:** 9 strongly-connected groups (cycles possible), **237 dealers
  sit in a cyclic component**, the largest such component has 219 dealers, and
  there are **318 reciprocal (A↔B round-trip) pairs**.
- **Ring detection:** the engine found **19,006 candidate cycles** (bounded to
  ≤ 4 hops — see the note on bounding below), covering **229 dealers**; the
  6-signal scorer places 810 of them in the HIGH band. The top-scored structures
  are reciprocal round-trips worth ₹0.5 M–₹2.7 M.
- **What this shows:** Graph GST's circular-trade detector runs, unmodified, on a
  genuine commercial-tax graph and surfaces real cyclic structures for an analyst
  to inspect. It is a **discovery** result, not an accuracy result — there is no
  ground truth to score against.
- **Honest caveat:** because the data has no dates, no tax split, and no director
  info, the composed *entity* risk is muted (structural signal only). That is the
  expected consequence of missing fields, not a defect.

### 5b. IBM AMLworld — labelled, supervised (ground truth)

- **Graph (deterministic sample):** 134,952 entities, 117,253 transactions after
  dropping self-transfers, ~$524 B total value, 98,567 distinct edges, dated
  2022-09-01 → 2022-09-18. (All 5,177 laundering transactions are kept; normal
  transactions are systematically down-sampled every 40th row — the exact
  composition is logged in the report, nothing is silently dropped.)
- **Structure & rings:** 59 cyclic components (largest 25 accounts), **610 rings
  detected** (≤ 6 hops) covering 143 accounts.
- **Ground-truth evaluation** (6,357 / 134,952 = 4.71 % illicit entities):
  - **Ring membership vs labels: precision 0.958, recall 0.022, 20.3× lift**
    over the base rate (tp 137, fp 6). Read this correctly: when Graph GST flags
    an entity as ring-involved it is ~96 % likely to be laundering-involved, but
    it only *recovers* the small **cyclic** slice of laundering — because most
    laundering is *not* circular (fan-in/out, scatter-gather). **This validates
    that Graph GST is a circular-trading detector: high precision on cycles, by
    design not a general AML tool.**
  - **Composed-risk ranking vs labels: ROC-AUC 0.564, precision@100 = 0.40**
    (~8.5× the 4.7 % base rate). Modest and honest — the composite is *partial*
    here (no reconcile/rules inputs), so only ring + temporal signal is doing the
    ranking.
- **Caveat carried in the report:** these labels are money-laundering, a
  documented *analog* of GST circular trading, not the same thing. This measures
  concentration on labelled-illicit entities on an independent labelled graph —
  **not** GST-specific accuracy, and it does **not** replace or change the nine
  gated synthetic benchmarks.

### A note on bounding the cycle search (no silent caps)

Real transaction graphs can have very dense strongly-connected cores (Iron
Dealers' largest is 219 nodes / 2,161 edges). Enumerating *all* simple cycles
there is combinatorially explosive, so `realdata.evaluate` bounds the search to
`--hop-max` hops (default 4 for the dense Iron Dealers graph; 6 for the sparser
AMLworld sample). This bound is **logged in the report**, not hidden — longer
cycles exist and are deliberately not enumerated.

---

## 6. Reproduce it (exact commands)

From `graphgst/`, with the Python env set up (`pip install -r requirements.txt`).
Neither command needs Neo4j, and **neither can change the nine gated benchmarks**
(those run in-memory on `truth.json` and never read this data).

```bash
# 1. Ingest: download (once) → canonical schema → data-quality report.
python -m realdata.ingest   --dataset iron_dealers
python -m realdata.ingest   --dataset ibm_aml

# 2. Evaluate: in-memory ring detection + graph stats + partial risk + (labels ⇒ supervised).
python -m realdata.evaluate --dataset iron_dealers --hop-max 4
python -m realdata.evaluate --dataset ibm_aml      --hop-max 6

# Reports land in realdata/<name>/processed/:
#   data_quality.md, ingestion_report.json, evaluation_report.md, evaluation_report.json
```

Optional — load a real dataset into Neo4j to explore it in the Investigator
Console (this **replaces** the demo graph; restore it with `python -m demo.reset`):

```bash
python -m realdata.load_neo4j --dataset iron_dealers --wipe --refresh
# the console's top-bar banner now reads "PUBLIC DATASET · iron_dealers"
```

Tests for this layer (no Neo4j, no network):

```bash
python -m pytest tests/test_realdata.py -q
```

---

## 7. Measured facts vs assumptions

**Measured (produced by the code above):** every number in §5 — entity/edge
counts, total value, connected-component and cycle structure, rings detected,
band distribution, and for AMLworld the precision/recall/AUC against its labels.

**Assumptions / interpretations (not measured):**

- That circular structures in Iron Dealers are *fraud*. They are **candidates**;
  the dataset has no labels, so suspicion ≠ confirmed fraud.
- That AMLworld's "laundering" cycles behave like GST "circular trading". They
  are a reasonable **analog**, not the same offence.
- That these results predict Graph GST's accuracy on *real Indian GST data*.
  They do **not** — real GST data is unavailable (see §1); the nine gated
  synthetic benchmarks remain the accuracy story, unchanged.

---

## 8. See also

- `realdata/README.md` — setup + file-by-file guide.
- `docs/NEO4J_SCHEMA.md` — the graph model the loader targets.
- `docs/BENCHMARKS.md` — the synthetic gated metrics (kept entirely separate).
