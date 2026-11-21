# Real-data evaluation — iron_dealers

**Source:** https://github.com/Sindhuja-5/circular-trade-detection  
**License:** No license file (treat as all-rights-reserved; research/testing use only)  
**Real taxpayer data:** NO (public / anonymised / synthetic)  
**Anonymized:** no  
**Evaluation mode:** UNSUPERVISED (no labels — real-world analysis only)

> Real (non-synthetic) Indian commercial-tax dealer transaction graph used in circular-trading research: 130,535 directed seller→buyer transactions between 799 anonymised dealers. Anonymised dealer integers (NOT GSTINs).

## Feature availability

| Feature | Can run? | Why |
|---|:--:|---|
| Reconciliation (GSTR-1↔2B↔3B, ITC) | **NO** | requires GSTR-1/2B/3B filing rows the source does not provide |
| ITC-mismatch detection | **NO** | needs statutory tax amounts and filed returns |
| Ring / circular-trade detection | **YES** | the core graph capability; runs on the edge list |
| GSTIN / entity relationships | **YES** | neighbourhood + community structure |
| Temporal analysis | **NO** | source has no per-transaction dates → temporal engine skipped |
| Risk scoring (composed) | **PARTIAL** | ring + temporal scorers fire; reconcile/rules contribute ~0 without filing/status data |
| Graph embeddings (structural) | **YES** | node2vec/PMI-SVD over the real graph |
| Ground-truth evaluation (precision/recall) | **NO** | no labels → UNSUPERVISED analysis only (no P/R/AUC) |

## Graph statistics (measured — REAL-DATA OBSERVATIONS, not verified fraud)

- Entities: **799** · Transactions: **130,535** · Distinct directed edges: **5,358**
- Total transaction value: **90,473,348,410**
- Weakly-connected components: 3 (largest 794)
- Cyclic groups (SCC>1): **9** · entities that can be in a ring: **237** (largest SCC 219)
- Reciprocal supplier↔buyer pairs (2-cycles): **318**

## Candidate circular-trading rings (Graph GST engine)

- Cycle bound: ≤ **4 hops** (logged bound; the largest SCC combinatorially explodes beyond this)
- Candidate rings: **19,006** in 17.57s · entities in rings: **229**
- Band distribution: {'HIGH': 810, 'MED': 18196}

Top candidates (NOT confirmed fraud):

| Ring | Hops | Score | Band | Value |
|---|:--:|--:|:--:|--:|
| `R-bfc003dfbabbc4df` | 2 | 0.3333 | HIGH | 468,964 |
| `R-fb2c1038eb384c54` | 2 | 0.3333 | HIGH | 1,507,756 |
| `R-b23e6951e25c1f7f` | 2 | 0.3333 | HIGH | 66,278 |
| `R-0a277ddcccc7d9b5` | 2 | 0.3333 | HIGH | 90,308 |
| `R-3426dab749246b23` | 2 | 0.3333 | HIGH | 116,621 |
| `R-947e8d1aa869cc70` | 2 | 0.3333 | HIGH | 1,809,364 |
| `R-6a1d7e26f53ffce0` | 2 | 0.3333 | HIGH | 2,725,788 |
| `R-b8dbed18459dfe64` | 2 | 0.3331 | HIGH | 1,030,339 |
| `R-ac07757f4a5ec075` | 2 | 0.333 | HIGH | 491,075 |
| `R-2b7fbd665f1b8639` | 2 | 0.333 | HIGH | 1,971,007 |

## Explainable evidence chains (top candidates)

**`R-bfc003dfbabbc4df`** — score 0.3333 (HIGH) — investigation candidate:

- `IRONDLR:1001` → invoice `IRONDLR-TXN-079997` (no-date, value 234,482, tax —, recon unknown) → `IRONDLR:1136`
- `IRONDLR:1136` → invoice `IRONDLR-TXN-027645` (no-date, value 234,482, tax —, recon unknown) → `IRONDLR:1001`

**`R-fb2c1038eb384c54`** — score 0.3333 (HIGH) — investigation candidate:

- `IRONDLR:1010` → invoice `IRONDLR-TXN-062922` (no-date, value 753,878, tax —, recon unknown) → `IRONDLR:1147`
- `IRONDLR:1147` → invoice `IRONDLR-TXN-031327` (no-date, value 753,878, tax —, recon unknown) → `IRONDLR:1010`

**`R-b23e6951e25c1f7f`** — score 0.3333 (HIGH) — investigation candidate:

- `IRONDLR:1077` → invoice `IRONDLR-TXN-084301` (no-date, value 33,139, tax —, recon unknown) → `IRONDLR:1431`
- `IRONDLR:1431` → invoice `IRONDLR-TXN-002317` (no-date, value 33,139, tax —, recon unknown) → `IRONDLR:1077`

## Temporal

_Skipped — no per-transaction dates._

## Risk scoring (partial composite)

_PARTIAL composite: only the ring + temporal scorers have inputs; reconcile/rules need GSTR filings + status this dataset lacks._

- Scored entities: 799 · bands: {'LOW': 799}

## Evaluation vs ground truth

_dataset has no fraud/ring labels; reporting graph structure and detected suspicious cycles instead of precision/recall._