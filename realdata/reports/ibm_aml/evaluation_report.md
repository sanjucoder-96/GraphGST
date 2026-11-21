# Real-data evaluation — ibm_aml

**Source:** https://github.com/IBM/AML-Data  
**License:** CDLA-Sharing-1.0 (commercial OK, share-alike)  
**Real taxpayer data:** NO (public / anonymised / synthetic)  
**Anonymized:** no  
**Evaluation mode:** GROUND_TRUTH (supervised)

> IBM AMLworld HI-Small: a published, labelled directed payment graph (Altman et al., NeurIPS 2023). Directed From→To account transfers with timestamps, amounts, and a per-transaction Is-Laundering label whose typologies include a 'simple cycle' (ground-truth circular trading).

## Feature availability

| Feature | Can run? | Why |
|---|:--:|---|
| Reconciliation (GSTR-1↔2B↔3B, ITC) | **NO** | requires GSTR-1/2B/3B filing rows the source does not provide |
| ITC-mismatch detection | **NO** | needs statutory tax amounts and filed returns |
| Ring / circular-trade detection | **YES** | the core graph capability; runs on the edge list |
| GSTIN / entity relationships | **YES** | neighbourhood + community structure |
| Temporal analysis | **YES** | runs on transaction timestamps |
| Risk scoring (composed) | **PARTIAL** | ring + temporal scorers fire; reconcile/rules contribute ~0 without filing/status data |
| Graph embeddings (structural) | **YES** | node2vec/PMI-SVD over the real graph |
| Ground-truth evaluation (precision/recall) | **YES** | labels present → supervised eval |

## Graph statistics (measured — REAL-DATA OBSERVATIONS, not verified fraud)

- Entities: **134,952** · Transactions: **117,253** · Distinct directed edges: **98,567**
- Total transaction value: **524,165,616,815**
- Weakly-connected components: 37,122 (largest 25,401)
- Cyclic groups (SCC>1): **59** · entities that can be in a ring: **307** (largest SCC 25)
- Reciprocal supplier↔buyer pairs (2-cycles): **49**

## Candidate circular-trading rings (Graph GST engine)

- Cycle bound: ≤ **6 hops** (logged bound; the largest SCC combinatorially explodes beyond this)
- Candidate rings: **610** in 3.37s · entities in rings: **143**
- Band distribution: {'HIGH': 17, 'MED': 556, 'LOW': 37}

Top candidates (NOT confirmed fraud):

| Ring | Hops | Score | Band | Value |
|---|:--:|--:|:--:|--:|
| `R-f0f7e22b2ea9b36c` | 2 | 0.3273 | HIGH | 24,515 |
| `R-17e315dd02e4e3ee` | 2 | 0.3261 | HIGH | 12,885 |
| `R-113e6e80aba71cd0` | 2 | 0.3229 | HIGH | 93,512 |
| `R-59e17c9b4efd82a5` | 2 | 0.3215 | HIGH | 370 |
| `R-11045956fd38e488` | 2 | 0.3204 | HIGH | 30,067 |
| `R-8b82dc2c8b920d24` | 2 | 0.3186 | HIGH | 538,684 |
| `R-025cfd9cfada7223` | 2 | 0.315 | HIGH | 89,864 |
| `R-3dd4b900256e8b3c` | 4 | 0.3117 | HIGH | 28,957 |
| `R-b9e7d2a7a734f3b2` | 2 | 0.3111 | HIGH | 3,853 |
| `R-d21cb7d8e88c2fa0` | 3 | 0.3087 | HIGH | 158,927 |

## Explainable evidence chains (top candidates)

**`R-f0f7e22b2ea9b36c`** — score 0.3273 (HIGH) — investigation candidate:

- `IBMAML:005425-807982750` → invoice `IBMAML-TXN-04908875` (2022-09-10, value 12,698, tax —, recon unknown) → `IBMAML:028183-807341220`
- `IBMAML:028183-807341220` → invoice `IBMAML-TXN-04908876` (2022-09-10, value 11,816, tax —, recon unknown) → `IBMAML:005425-807982750`

**`R-17e315dd02e4e3ee`** — score 0.3261 (HIGH) — investigation candidate:

- `IBMAML:001686-80113D5D0` → invoice `IBMAML-TXN-02252772` (2022-09-04, value 6,507, tax —, recon unknown) → `IBMAML:0121303-80BDDEE60`
- `IBMAML:0121303-80BDDEE60` → invoice `IBMAML-TXN-02252773` (2022-09-05, value 6,378, tax —, recon unknown) → `IBMAML:001686-80113D5D0`

**`R-113e6e80aba71cd0`** — score 0.3229 (HIGH) — investigation candidate:

- `IBMAML:0118-811A67510` → invoice `IBMAML-TXN-04723796` (2022-09-10, value 45,385, tax —, recon unknown) → `IBMAML:0119-81235E8B0`
- `IBMAML:0119-81235E8B0` → invoice `IBMAML-TXN-04269460` (2022-09-09, value 48,126, tax —, recon unknown) → `IBMAML:0118-811A67510`

## Temporal

- Dated transactions: 117,253 · range 2022-09-01 → 2022-09-18 · 1 month(s)

## Risk scoring (partial composite)

_PARTIAL composite: only the ring + temporal scorers have inputs; reconcile/rules need GSTR filings + status this dataset lacks._

- Scored entities: 134952 · bands: {'HIGH': 1163, 'MED': 66808, 'LOW': 66981}

## Evaluation vs ground truth

> Labels denote money-laundering / fraud in the SOURCE domain, a documented ANALOG of GST circular trading — not identical. Measures concentration on labelled-illicit entities on an independent labelled graph, not GST-specific accuracy.

- Labelled-illicit entities: 6,357 / 134,952 (prevalence 0.0471)
- **Ring membership vs labels:** {'tp': 137, 'fp': 6, 'fn': 6220, 'precision': 0.958, 'recall': 0.0216, 'f1': 0.0422, 'precision_lift_vs_base': 20.34}
- **Risk ranking vs labels:** {'roc_auc': 0.5637, 'precision_at_50': 0.3, 'precision_at_100': 0.33, 'base_rate': 0.0471}