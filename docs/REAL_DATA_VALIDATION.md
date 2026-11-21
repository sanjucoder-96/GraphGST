# Real-Data Validation Report

*Phase 8 deliverable. What happened when we ran Graph GST's real engines over
the best legally-usable real/public datasets. Everything here is **measured** by
the reproducible commands in §6 of `docs/REAL_DATA.md` and written to
`realdata/reports/<dataset>/`. Companion docs: `docs/REAL_DATASETS.md` (the
dataset survey) and `realdata/README.md` (how the layer is built).*

> **Framing (read once).** Real, taxpayer-level GST invoice data is not public
> and cannot legally be (CGST Act §158/§158A — see `docs/REAL_DATASETS.md`). So
> we validate on two complementary public datasets. Everything below is a
> **REAL-DATA OBSERVATION** — candidate patterns and structure — **not verified
> fraud**, and (for the labelled set) an *analog* evaluation, not GST accuracy.
> None of this touches the nine gated synthetic benchmarks.

---

## Dataset 1 — Iron Dealers  (REAL, unsupervised)

**1. Dataset.** Iron Dealers commercial-tax transaction graph.
**2. Source.** https://github.com/Sindhuja-5/circular-trade-detection (raw CSV).
**3. License.** No LICENSE file → treated as all-rights-reserved (research/testing
only). Not identifiable taxpayer data (dealers are anonymised integers).
**4. Dataset size.** 799 dealers · 130,535 directed seller→buyer transactions ·
5,358 distinct directed edges · ₹90,473,348,410 total transaction value.
**5. Data quality** (from `data_quality.md`): 0 structurally-invalid rows; date
100% missing, tax 100% missing, label 100% missing; 318 reciprocal pairs; every
dealer id is non-GSTIN (public/anonymised). Nothing discarded silently.
**6. Graph statistics.** 3 weakly-connected components (largest 794); **9
strongly-connected (cyclic) groups**, largest 219 dealers; **237 dealers sit in a
cyclic component**.
**7. Reconciliation.** **Not run** — no GSTR filings / tax in the source
(feature matrix = NO). Honestly disabled, not faked.
**8. Ring candidates.** The Graph GST ring engine (bounded to ≤4 hops — the
219-node SCC explodes beyond that, a logged bound) found **19,006 candidate
cycles** covering **229 dealers**; the six-signal scorer put **810 in the HIGH
band**. Example explainable evidence chain (an *investigation candidate*, not
confirmed fraud):

```
IRONDLR:1001 → invoice (value 234,482) → IRONDLR:1136
IRONDLR:1136 → invoice (value 234,482) → IRONDLR:1001
```

The **identical value on both legs** of a reciprocal pair is a classic
round-tripping signal — exactly what an investigator would open next.
**9. Risk distribution.** Composed *entity* risk is muted (all LOW) — with no
dates, tax, filings or directors, only the structural ring signal fires, so the
composite barely moves. This is the honest consequence of missing fields.
**10. Interesting patterns.** 318 reciprocal (A↔B) round-trip pairs; a dense
219-dealer core that concentrates the cyclic structure; high-value 2-cycles up to
₹2.7 M.
**11. Results.** `realdata/reports/iron_dealers/evaluation_report.md` (+ `.json`),
`data_quality.md`; the Investigator Console shows a **PUBLIC DATASET** banner and
a Data-Provenance panel when the graph is loaded (§Console below).
**12. Limitations.** No dates → no temporal; no tax → no reconciliation/ITC; no
labels → no accuracy; anonymised integer ids → no real-GSTIN semantics.
**13. Cannot conclude.** That any candidate ring *is* fraud. There is no ground
truth; these are structures to investigate, not verdicts.
**14. Next data needed.** Per-invoice dates, CGST/SGST/IGST split, and the
matching GSTR-1/2B would unlock temporal + reconciliation + ITC on this exact
graph; a labelled subset would allow accuracy measurement.

---

## Dataset 2 — IBM AMLworld (HI-Small)  (LABELLED, supervised)

**1. Dataset.** IBM "Transactions for Anti-Money Laundering" (AMLworld) HI-Small.
**2. Source.** https://github.com/IBM/AML-Data (HuggingFace parquet/zip mirror).
**3. License.** CDLA-Sharing-1.0 (commercial OK, share-alike).
**4. Dataset size** (deterministic sample — all 5,177 laundering txns + every 40th
normal txn; composition logged): 134,952 entities · 117,253 transactions · 98,567
edges · ~$524 B value · dated 2022-09-01 → 2022-09-18.
**5. Data quality.** ~56% of source rows are self-transfers (dropped as
self-loops, counted); dates 100% present; labels 100% present; no tax/filings.
**6. Graph statistics.** 59 cyclic groups (largest 25 accounts); 307 accounts in
cyclic components.
**7. Reconciliation.** **Not run** — no GST filings/tax (same honest disable).
**8. Ring candidates.** **610 candidate cycles** (≤6 hops) covering 143 accounts.
**9. Risk distribution** (partial composite): HIGH 1,163 · MED 66,808 · LOW 76,136.
**10. Ground-truth evaluation** (6,357 / 134,952 = **4.71 % illicit**):
- **Ring membership vs labels: precision 0.958, recall 0.022, 20.3× lift**
  (tp 137, fp 6). When Graph GST flags an entity as ring-involved it is ~96 %
  laundering-involved — but it recovers only the small **cyclic** slice of
  laundering (most laundering is fan/scatter, non-circular). **This validates
  Graph GST as a circular-trading detector: high precision on cycles, by design
  not a general AML tool.**
- **Composed-risk ranking vs labels: ROC-AUC 0.564, precision@100 0.33** (~7×
  base) — modest and honest (partial composite; no reconcile/rules inputs).
**11. Results.** `realdata/reports/ibm_aml/evaluation_report.md` (+ `.json`).
**12. Limitations.** Realistic *synthetic* AML, not real taxpayers and not GST;
"laundering" is an *analog* of circular trading; no tax/filings/IRN.
**13. Cannot conclude.** GST-specific accuracy, or general AML recall. The
number that matters is *precision on cycles*, which is high.
**14. Next data needed.** A GST-native labelled dataset with real circular-trading
rings + dates + tax + filings would let us measure GST detection directly.

---

## Console (Phase 9)

When a real dataset is loaded into Neo4j
(`python -m realdata.ingest --source iron_dealers --dataset-id real_iron_dealers_v1`),
the Investigator Console:

- shows a **PUBLIC DATASET** badge in the top bar (distinct teal, never the
  synthetic-demo grey), and
- shows a **Data Provenance** panel on *Data Sources* with: source, dataset
  version, date range, records, entities, license, last imported, anonymization
  status, real-taxpayer-data flag, and the data-quality warnings.

Every loaded node carries a `dataset_id` (e.g. `real_iron_dealers_v1`) so real
data is traceable and individually removable, and never mixes with the demo
(the default load is additive and never auto-deletes; use `--wipe` for a
real-data-only graph).

---

## Machine-readable summary

`realdata/reports/latest.json` holds the latest run's **non-sensitive**
aggregates only (counts, structure, ring band distribution, and — for labelled
data — the precision/recall/AUC). No entity ids, no evidence chains, nothing
that could identify a party.

## Existing V7 gates

Unchanged. The nine gated benchmark metrics run in-memory on the synthetic
`truth.json` and never read this data; `pytest`, the benchmark suite, and demo
verification remain green (see the final report / `IMPLEMENTATION_LOG.md`).
