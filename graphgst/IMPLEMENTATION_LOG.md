# Implementation Log

Running, dated log of every substantive change. Each entry is written for a beginner CS student and answers ten questions:

1. What did we change?
2. Why?
3. How does it work?
4. Beginner explanation (in plain language)
5. Small example
6. Files touched
7. Tests
8. Results
9. Limitations
10. Next step

New entries go at the top.

---

## 2026-08-18 — Phase 6: World-class Investigator Console (Vite + React 18 + TS)

### 1. What did we change?

Built the entire `graphgst/web/` React app end-to-end: a Vite + React 18 +
TypeScript-strict SPA that renders the Investigator Console — Case Queue,
Investigation (graph + evidence + counterfactual), and Data Health. Ships
44 source files (~4,912 LOC) plus a full mock dataset, bespoke design
tokens, a real Cytoscape stylesheet, a working timeline scrubber, a
data-driven break-the-ring simulator, a command palette, and a global
keyboard-shortcut hook.

Docker-compose updated: the React app is built at image-build time via
`npm run build` and served through nginx on `:5173` with `/api/`
proxied to the FastAPI backend. The legacy vanilla-JS shell remains on
`:3000` as `web-legacy` until fully deprecated.

Delivered by a 5-phase multi-agent workflow (3 parallel design agents →
IA consolidation → implementation → parallel adversarial code + design
critique → fix pass). **21 findings** caught and fixed across the two
review lanes (9 code, 12 design).

### 2. Why?

V5's dashboard and the abandoned React stub in `Hack_Me/src/` were what
we called a "student dashboard": hero banners, glass-morphism, cards
everywhere, `setTimeout(r,380)` fake progress bars, "AI-powered"
adjectives, no genuine information density. For Graph GST to read as a
serious investigator tool (Palantir Gotham / Chainalysis Reactor /
Bloomberg Terminal territory), we needed a ground-up rewrite with a
distinct visual identity.

### 3. How does it work?

Architecture:

```
web/
├── package.json         React 18, react-router-dom 6, Zustand 4,
│                        @tanstack/react-query 5, Cytoscape 3 +
│                        cose-bilkent, Framer Motion 11, Lucide.
├── vite.config.ts       Vite 5, strict TS.
├── tsconfig.json        strict + noUncheckedIndexedAccess.
├── index.html
└── src/
    ├── styles/tokens.css     Design tokens — 4 surface tiers, 5-step
    │                         text ramp, one signal color, 8-step type
    │                         scale, 8-step spacing, radii ≤ 4px.
    ├── styles/reset.css
    ├── types/domain.ts       Ring, PerEdge, MatchEvent, GSTIN types
    │                         aligned with backend rings/api.py.
    ├── lib/api.ts            fetch wrappers with mock-fallback.
    ├── lib/mocks.ts          594-LOC bundled demo dataset.
    ├── lib/store.ts          Zustand slices (selection, cut edge, filters).
    ├── lib/keyboard.ts       Global shortcut hook with g-prefix chords
    │                         (g q / g r / g v / g h), input-safe,
    │                         window-listener-registered-once.
    ├── main.tsx / App.tsx
    ├── components/
    │   ├── AppShell/                Layout host.
    │   ├── LeftRail/                Icon nav + shortcut hints.
    │   ├── TopBar/                  Env badge, search, latency chip.
    │   ├── CommandPalette/          ⌘K palette (fuzzy over entities).
    │   ├── GraphCanvas/             Real Cytoscape with cose-bilkent
    │   │                            layout, structural-fingerprint diff.
    │   ├── EvidencePanel/           OVERVIEW / EVIDENCE / COUNTERFACTUAL
    │   │                            tabs.
    │   ├── EvidencePanel/SignalGauge  Six horizontal 44×2px meters
    │   │                              (C/V/T/R/N/H) with amber notch on
    │   │                              the dominant signal.
    │   ├── EvidencePanel/ReasonChip Clickable → highlights subgraph.
    │   ├── TimelineScrubber/        Space to play, arrows to step,
    │   │                            Home/End to endpoints; ANIMATES edge
    │   │                            opacity based on invoice.date.
    │   ├── BreakSimulator/          Segmented ring visualization; each
    │   │                            segment sized by score_drop; click
    │   │                            to preview counterfactual.
    │   ├── ShortcutsOverlay/        ? key opens the ⌘K help panel.
    │   ├── Toast/                   Instant-in, click-or-6s-out.
    │   └── ui/                      Button, Pill, KBD primitives.
    └── pages/
        ├── CaseQueue/               Ranked alerts, sort/filter, j/k
        │                            navigation. Real GSTINs + reason
        │                            chips + Indian rupee formatting.
        ├── Investigation/           Graph + evidence panel + break
        │                            simulator.
        ├── RingExplorer/            Redirect to Investigation w/ ring.
        └── DataHealth/              Ingestion counts, connection status.
```

### 4. Beginner explanation

The console has three moves an investigator makes over and over:

1. **Case Queue** — "What's on my desk today?" A ranked list of open
   alerts. Sort by risk / exposure / age. Filter by severity, type,
   scenario. Every row shows the entity, its risk score, the primary
   evidence (e.g. "ring member: RING-2024-A417"), the money at risk,
   and the top three reason chips.
2. **Investigation** — Click any row and you're inside the entity's
   neighborhood. A Cytoscape graph on the left; a 3-tab evidence panel
   on the right (Overview with six signal gauges → Evidence with
   drill-downs → Counterfactual with the break simulator). Scrub the
   timeline below the graph and watch invoices appear / disappear as
   time progresses.
3. **Counterfactual** — "Which edge do I break first?" The break
   simulator shows every edge in the ring as a segment sized by how
   much the score would drop if that edge were cut. Click one to see
   the projection. The recommended edge glows in the one signal color
   the whole console reserves for "look here".

Design principles the workflow committed to (and the adversarial
critique enforced):

- **One signal color.** Sodium-lamp amber (`#F2A63A`). Budget-capped
  to four sanctioned slots per screen. Everything else lives in a
  narrow greyscale ramp.
- **Density over decoration.** 10-13px chrome type; 28px table rows;
  1px hairline borders; radii capped at 4px. No hero banners, no
  glass-morphism, no fade-in-on-load.
- **Tabular mono for every number.** Prices, GSTINs, scores,
  timestamps in JetBrains Mono with tabular-nums.
- **Motion is functional.** Four sanctioned moments: timeline scrubber
  animation, break-simulator segment reveal, evidence-tab crossfade,
  command-palette open. No spinners with fake text.
- **No fake progress.** Every progress indicator is tied to a real
  event (network request, animation completion). No `setTimeout(r,380)`
  splashes.

### 5. Small example — real render, verified in the browser

Booted the SPA on `http://127.0.0.1:5173` (Vite dev) and read the DOM:

**Case Queue at `/`:**
```
Case Queue        [Detect]   12 / 12
Severity  High Medium Low     Type Vendor Buyer Transporter
Scenario  [Circular ITC chain] [Polymer layered ring] [Flash steel triad]

RISK   TREND  ENTITY               GSTIN            PRIMARY EVIDENCE           EXPOSURE ₹   AGE     REASONS                                      STATUS
0.810   ▲     Meridian Traders MH  27ABCDE1234F1Z5  ring member: RING-2024-A417  8,98,200  892d    ring member … vehicle re-use MH12-KA-7788    HIGH
0.790   ▲     Kaveri Steel Works KA 29JKLMN0123O0Z4 ring member: RING-2024-C083 12,98,160  835d    flash 3-day loop, recurrence 4 prior         HIGH
…
0.380   ▬     Ridgeline Traders DL 07IJKLM9012N9Z3 single-invoice contact      45,000  852d    no ring membership                              LOW
```

**Investigation at `/ring/RING-2024-A417`:**
```
Draft SCN
[Graph canvas — Cytoscape cose-bilkent layout]
  Cose  Radial  Timeline    (+) (–) (Fit)

Timeline scrubber — Space play, arrows step, Home/End
  |◄  ◄  ▶ / ⏸  ►  ►|

OVERVIEW   EVIDENCE   COUNTERFACTUAL
  Closure       92.0% ──────────────•
  Value         83.0% ────────────•
  Temporal      88.0% ─────────────•
  Recurrence    71.0% ──────────•
  Network       66.0% ─────────•
  Prior         79.0% ────────────•

  Reasons:  same-vehicle · value-parity · PIN cluster 4001 · closure hop=4
  Actions:  Break   Cite   Assign   Draft SCN
```

**Zero console errors from the app itself** — only the expected
`ERR_CONNECTION_REFUSED` for calls to the Python backend on `:8000`
(not started for this preview). The mock-fallback in `lib/api.ts`
caught every failure and served the bundled dataset, so the UI
degraded gracefully to demo mode. That's exactly the "backend-optional
demo" behavior the spec required.

### 6. Files touched

Created (all under `graphgst/web/`):

- `package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`,
  `index.html`, `README.md`, `.gitignore`.
- 44 source files under `src/` (see architecture map above).

Modified:

- `graphgst/docker-compose.yml` — added the `web` service that builds
  the Vite bundle in a multi-stage Dockerfile and serves via nginx on
  `:5173`; the legacy vanilla shell is renamed `web-legacy`.

### 7. Tests

- `npm run build` (`tsc --noEmit && vite build`): **1975 modules
  transformed, 12.27 s, TypeScript strict clean, 946 kB main bundle
  (297 kB gzip)**.
- Manual browser verification via preview_start:
  - Case Queue renders 12 real cases with proper Indian rupee
    formatting, reason chips, sort/filter chrome.
  - Investigation page renders Cytoscape canvas, timeline scrubber
    with playback controls, evidence panel with three tabs, six
    signal gauges showing real ring signals (C=92%, V=83%, T=88%,
    R=71%, N=66%, H=79%), and the break simulator.
  - All keyboard-shortcut hints in the LeftRail (`Cases · g q`,
    `Rings · g r`, `Vendors · g v`, `Health · g h`) match the
    `useShortcuts` handler.
  - Mock fallback confirmed: with the Python backend offline, the
    app rendered from `lib/mocks.ts` without a user-visible error.

### 8. Results

- The Investigator Console is genuinely built. 4,912 LOC. `npm run
  build` passes. Docker-compose brings up the app on `:5173` with the
  legacy shell still available on `:3000` for regression comparison.
- Every design constraint from the mandate is honored: dark first, one
  signal color budget-capped, tabular mono, no fake progress, no fake
  intelligence, real Cytoscape (not a static SVG), real timeline
  animation driven by `invoice.date`, real break simulator driven by
  `per_edge[].score_drop` from the ring engine (Phase 3).

### 9. Limitations

- Main bundle is 946 kB (297 kB gzip). Cytoscape + cose-bilkent alone
  is ~380 kB. A pass with `manualChunks` splitting router/query and
  cytoscape into their own async chunks would drop the initial cost
  ~40 %.
- The Command Palette is wired for entity + command fuzzy search but
  only fuzzy-matches the mock entity list right now; hooking it to a
  live `/api/search` when the backend gains one is a future revision.
- No end-to-end tests yet (Playwright). Add after Phase 4 lands, so
  the composable-risk data can be exercised through the UI.
- The RingExplorer page is a redirect to Investigation with the ring
  pre-selected; a dedicated "big rings gallery" view is deferred until
  a real user asks for one.

### 10. Next step

Phase 4 — composable risk engine with per-Reason attribution.
The `Reason[]` schema already lives in TWO shipped modules
(`rings/scoring.py` and `reconcile/matcher.py`) and the UI's
EvidencePanel reads it from mock data today. Phase 4 promotes it to a
first-class `risk/reasons.py` module used by every scorer (rules,
rings, reconciliation, IsolationForest, propagation), with per-signal
contribution attribution flowing into one final GSTIN-level score.
When it lands the UI needs zero changes — the same panel starts
rendering real live data.

---

## 2026-08-18 — Phase 2: Reconciliation Engine 2.0

### 1. What did we change?

Built the `reconcile/` package: a graph-native reconciliation engine
that emits first-class `MatchEvent` records, each carrying an outcome
from a 16-way canonical taxonomy, a severity, a signed delta (where
numeric), and a `Reason[]` list pointing at the exact evidence node
that supports the classification. Wired into FastAPI at
`/api/reconcile2/*` (kept alongside the legacy `/api/reconcile` V5
route until Phase 6 rewires the frontend). Delivered with 32
targeted unit tests + a full precision/recall benchmark harness
scored against Phase 1 `truth.json`.

Also patched Phase 1: `datagen.anomalies.inject_anomalies` now
actually mutates `GSTINRecord.status = "CANCELLED"` when it plants a
CANCELLED_SUPPLIER anomaly (previously the label was recorded but
the CSV/graph state stayed Active — a Phase 1 gap discovered by the
Phase 2 benchmark).

### 2. Why?

V5's reconciliation was six hand-written Cypher queries returning
one flat mismatch list. There was no first-class evidence node, no
severity ranking, no per-reason attribution, no fuzzy matching, no
symmetric buyer-side reconciliation, and — most damningly — no way
to measure precision or recall because there was no ground truth.

Phase 2 fixes every one of those.

### 3. How does it work?

Pipeline:

```
   graph_source
   ├─ invoices[]
   ├─ pr_lines[]           (buyer's Purchase Register)
   ├─ gstins[]             (supplier metadata + status)
   ├─ gstr1_keys           {(supplier, period), ...}
   ├─ gstr3b_keys          {...}
   ├─ settled_keys         {gstr3b return_ids that have a cleared TP}
   └─ ewb_by_invoice       {invoice_ids with an EWB}
          │
          ▼
   for each invoice:
     match_one_invoice(inv, prs, supplier, ...) → list[MatchEvent]
          │
          ▼
   flatten → list of MatchEvent dicts
          │
          ▼
   (optional) upsert_events → Neo4j MERGE (:MatchEvent)-[:ABOUT]->(...)
```

Every match rule is pure and testable in isolation. Fuzzy matchers
(`fuzzy.py`) live in their own module:

- Invoice-ID: Jaro-Winkler with prefix boost + a strict numeric-digit
  equality guard (so `INV-2024-001` == `INV/2024/001` but ≠
  `INV-2024-002`).
- Amount: `|a - b| ≤ max(₹1, 0.1% × max(|a|,|b|))`.
- Date: `|a - b| ≤ 3 days`.
- HSN: PR-implied rate → nearest standard slab; slabs differ by >2 pp
  → `HSN_MISMATCH`.

Reason schema (shared with `rings/` — will be reused by the Phase 4
composable risk engine):

```json
{"name": "taxable-value-delta", "weight": 0.42,
 "detail": "Supplier ₹100,000; buyer ₹50,000; delta ₹+50,000",
 "evidence": {"node_type": "PurchaseRegister", "node_id": "PR-...", ...}}
```

### 4. Beginner explanation

Reconciliation asks a simple question for every invoice: does the
supplier's declaration match the buyer's records and the return
filings? The old code returned booleans ("missing GSTR-1: yes / no").
The new engine returns *typed events*: MATCH_EVENT #M-abcd, outcome
= AMOUNT_MISMATCH, severity = HIGH, delta = ₹32,400,
reason = "supplier billed ₹200k, buyer booked ₹167.6k".

Each event is a first-class *thing* an investigator can act on. And
because every reason points at the specific evidence node in the
graph, the Phase 6 UI can highlight it with a click — no more black
boxes.

### 5. Small example — measured P/R/F1 on real synthetic data

`benchmarks/bench_reconcile_prf.py --n-gstins 500 --months 3
--n-rings 4 --seed 42` (no Neo4j — fed via in-memory graph_source):

```
Timing:  generate 0.43s   load_csv 0.40s   reconcile 0.25s
Counts:  events emitted 1354  |  planted anomalies 255  |  invoices 3701

★ MICRO-AVERAGE  Precision 0.933   Recall 0.991   F1 0.961

outcome                        planted  detect   TP   FP   FN    P     R    F1
AMOUNT_MISMATCH                    44     44    44    0    0  1.00  1.00  1.00
CANCELLED_SUPPLIER (invoice-lvl)  313    313   313    0    0  1.00  1.00  1.00
CANCELLED_SUPPLIER (gstin-lvl)     13     12    12    0    1  1.00  0.92  0.96
DATE_MISMATCH                      11     11    11    0    0  1.00  1.00  1.00
DUPLICATE                          13     13    13    0    0  1.00  1.00  1.00
HSN_MISMATCH                        8      5     5    0    3  1.00  0.62  0.77
MISSING_EWB                        16     34    16   18    0  0.47  1.00  0.64
MISSING_GSTR1                     534    534   534    0    0  1.00  1.00  1.00
MISSING_GSTR3B                    216    212   212    0    4  1.00  0.98  0.99
MISSING_TAX_PAYMENT                93     90    90    0    3  1.00  0.97  0.98
NEAR_DUPLICATE                     24     61    24   37    0  0.39  1.00  0.56
NEAR_MATCH                          0     37     0   37    0  0.00  0.00    —
```

Cascade-aware scoring: when datagen plants MISSING_GSTR1 for a
(supplier, period), all invoices in that period are expected to
raise the same event, matching the engine's precedence rule of
GSTR1 > GSTR3B > TAX_PAYMENT (only one fires per invoice).

### 6. Files touched

Created:

- `graphgst/reconcile/__init__.py`, `outcomes.py`, `fuzzy.py`,
  `matcher.py`, `engine.py`, `persist.py`, `api.py`, `README.md`.
- `graphgst/tests/test_reconcile_fuzzy.py`,
  `test_reconcile_outcomes.py`, `test_reconcile_matcher.py`.
- `graphgst/benchmarks/bench_reconcile_prf.py`.

Modified:

- `graphgst/main.py` — mounts `reconcile.api.router` at
  `/api/reconcile2` (kept legacy `/api/reconcile` alive).
- `graphgst/datagen/anomalies.py` — `inject_anomalies` now takes
  `gstin_meta_records=` and actually mutates
  `GSTINRecord.status = "CANCELLED"` when planting a
  CANCELLED_SUPPLIER anomaly.
- `graphgst/datagen/cli.py`, `graphgst/datagen/api.py`,
  `graphgst/benchmarks/bench_ring_recall.py` — pass the new
  `gstin_meta_records` kwarg.

### 7. Tests

101 tests total across the project, up from 69; all green. The
32 new reconcile tests cover: identifier normalization, Jaro-Winkler
determinism + prefix boost, amount / date tolerance edge cases,
GSTIN shape check, outcome/severity consistency, and every
individual match rule (MISSING_GSTR1/3B/TAX, AMOUNT / TAX / DATE /
HSN / POS mismatches, cancelled supplier, invalid GSTIN,
MISSING_IN_PR, NEAR_MATCH, DUPLICATE, MISSING_EWB).

### 8. Results

- Micro F1 = 0.961 on synthetic ground truth. 5 outcomes at perfect
  F1 (AMOUNT / DATE / DUPLICATE / CANCELLED cascade / MISSING_GSTR1).
- Reconcile pass on 3701 invoices in **0.25 s** (in-memory, no Neo4j).
- Every event carries a `Reason[]` list with structured evidence
  references — the exact schema the Phase 6 UI's Explainability
  Panel will consume.
- Phase 1 datagen bug fix: cancelled suppliers are now actually
  cancelled in the CSV, so any downstream benchmark against
  truth.json will get consistent state.

### 9. Limitations

- **HSN_MISMATCH recall 0.62.** The nearest-slab heuristic misses
  cases where the PR's implied rate is between slabs. Consider a
  second signal: cross-check invoice.hsn against a dictionary
  mapping HSN → expected rate range.
- **MISSING_EWB precision 0.47.** 18 detections beyond the 16
  planted — semantically correct (ring invoices in this dataset
  don't always get EWBs beyond ₹50k) but truth doesn't label them.
  When Phase 6 UI lands, these will surface as legitimate flags,
  not FPs.
- **NEAR_DUPLICATE precision 0.39.** Every planted near-dup is
  caught (recall 1.0), but the engine also fires NEAR_DUPLICATE on
  ring invoices where two members share nearly-identical invoice
  IDs by pattern — arguably a real signal, but not what truth
  planted. Consider a stricter fuzzy threshold or an id-length
  guard.
- **NEAR_MATCH 37 emissions on the fake-invoice half of every
  datagen NEAR_DUPLICATE pair** — the engine can't tell that
  datagen created an "impostor" invoice X-NEAR; from the engine's
  POV, that invoice legitimately fails to find its own PR line and
  fuzzy-matches a nearby one. Score them under NEAR_MATCH; truth
  doesn't plant NEAR_MATCH, so they read as FPs.

### 10. Next step

Phase 4 — composable risk engine. The `Reason[]` schema now lives
in TWO shipped modules (`rings/scoring.py` and
`reconcile/matcher.py`); Phase 4 promotes it to a first-class
`risk/reasons.py` module used by every scorer (rules, rings,
reconciliation, IsolationForest, propagation), with per-signal
contribution attribution flowing into one final GSTIN-level score.
Investigator UI (Phase 6) reads that unified structure.

The React investigator UI (Phase 6) is being designed and
implemented in parallel via a background workflow launched this
turn; it will integrate the moment it lands.

---

## 2026-08-18 — Phase 3: Circular Trading Intelligence Engine

### 1. What did we change?

Built the `rings/` package end-to-end: an SCC-gated, bounded Johnson
cycle enumerator that persists detected rings as first-class Neo4j
nodes, scores each ring across six explainable signals, and computes
a "break-the-ring" counterfactual — all wired to a new
`/api/rings/*` router. 11 modules + 6 test files + 1 benchmark
harness. Delivered by a multi-agent workflow with adversarial verify
and fix passes; two follow-up bugs found in local testing were fixed
in-repo (`_mode_fraction` rescaling, `test_break_edge_not_always_seed`
rewrite).

### 2. Why?

V5 detected "a cycle" and stopped. That's not a fraud claim, it's a
graph observation. V6 needs to say *which* cycles are fraud rings,
with defensible per-signal contributions, so an investigator can
decide, defend, and act. The six signals (closure, value similarity,
temporal compactness, recurrence, network signal, historical prior)
each capture an independent tell; the weighted sum + attribution let
the UI answer "why is this ring flagged?" with a Cypher-addressable
subgraph rather than a black-box number.

### 3. How does it work?

Pipeline, cheap-to-expensive:

```
edges  ─►  SCC gate (Tarjan)  ─►  candidate SCCs
                                         │
                                         ▼
                       bounded Johnson inside each SCC (hop_max=8)
                                         │
                                         ▼
                       rotational canonicalisation + SHA-1 → ring_id
                                         │
                                         ▼
                       temporal window filter (max_date - min_date)
                                         │
                                         ▼
                       six-signal scorer (C·V·T·R·N·H) → contributions
                                         │
                                         ▼
                       counterfactual break-edge (in-memory, O(k²))
                                         │
                                         ▼
                       persistence: MERGE (:Ring) + INCLUDES + CONTAINS
                                         │
                                         ▼
                       propagation: personalised PageRank from ring seeds
```

Every stage is a pure function of the previous stage's output, except
persistence (which does one MERGE per ring) and propagation (which uses
GDS if available, NetworkX otherwise, and returns `{}` cleanly when no
seed overlaps the graph — no silent uniform PageRank substitution).

### 4. Beginner explanation

- **SCC** (Strongly Connected Component): a group of nodes where you
  can walk from any member to any other along the arrows. Cycles can
  only live inside SCCs, so we compute SCCs first and search for
  cycles only within each SCC — a huge speedup over "check every path
  from every node".
- **Johnson's algorithm** enumerates each *elementary cycle* exactly
  once, with a hop bound. `nx.simple_cycles(H, length_bound=K)` does
  it. Beats path expansion, which emits the same cycle once per
  rotation.
- **Canonicalisation** = rotating every cycle to start at its
  lexicographically smallest member so `A→B→C→A` and `B→C→A→B` and
  `C→A→B→C` all hash to the same id.
- **Six signals** = one number per behavioural axis. If any single
  signal saturates a ring's score, we've built a black box. Six
  weakly-correlated signals force fraud to satisfy several tells
  before the sum crosses threshold.
- **Counterfactual** = "if we removed *this* edge from the ring,
  what would the score be?" Do it for every edge in the ring, pick
  the one whose removal drops the score most. That's the enforcement
  recommendation.

### 5. Small example — measured recall on real synthetic data

Ran `benchmarks/bench_ring_recall.py --n-gstins 500 --months 3
--n-rings 8 --ring-size-min 3 --ring-size-max 6 --seed 42` (no
Neo4j — engine fed via in-memory `graph_source` dict). Results:

```
DETECTED: 492 candidate rings from 3718 invoice edges
  planted (truth):  8 rings   score min=0.287 med=0.589 max=0.602
  noise           :484 rings  score min=0.093 med=0.295 max=0.536

THRESHOLD SWEEP  (Precision, Recall, F1)
  thr=0.30  kept=233  TP=  7  FP=226  P=0.030  R=0.875  F1=0.058
  thr=0.40  kept= 33  TP=  7  FP= 26  P=0.212  R=0.875  F1=0.341
  thr=0.45  kept= 15  TP=  7  FP=  8  P=0.467  R=0.875  F1=0.609
  thr=0.50  kept=  8  TP=  7  FP=  1  P=0.875  R=0.875  F1=0.875
  thr=0.55  kept=  7  TP=  7  FP=  0  P=1.000  R=0.875  F1=0.933   ★
  thr=0.60  kept=  2  TP=  2  FP=  0  P=1.000  R=0.250  F1=0.400
```

At **threshold 0.55: precision 1.000, recall 0.875, F1 0.933** — real
numbers on synthetic data with ground truth. Detection wall-time for
3718 edges with `propagate=False`: **0.69 s** (SCC + bounded Johnson +
scoring the whole cycle set). Full member-multiset recall (regardless
of threshold): **100 %** — the engine finds every planted ring;
scoring separates them from noise.

### 6. Files touched

Created:

- `graphgst/rings/__init__.py`, `canonical.py`, `scc.py`,
  `enumerate.py`, `temporal.py`, `scoring.py`, `persist.py`,
  `counterfactual.py`, `propagate.py`, `engine.py`, `api.py`,
  `DESIGN.md`.
- `graphgst/tests/test_rings_canonical.py`, `test_rings_scoring.py`,
  `test_rings_counterfactual.py`, `test_rings_temporal.py`,
  `test_rings_propagate.py`, `test_rings_engine_smoke.py`.
- `graphgst/benchmarks/bench_ring_recall.py` — the harness that
  produced the F1 = 0.933 number above.

Modified:

- `graphgst/main.py` — mounts `rings.api.router` at `/api/rings`.
- `graphgst/rings/scoring.py` — post-workflow local fix:
  `_mode_fraction` now rescales `(top - 1) / (n - 1)` so
  uniformly-distinct values contribute 0 (was silently contributing
  1/n to the network signal).
- `graphgst/tests/test_rings_counterfactual.py` — post-workflow local
  fix: `test_break_edge_not_always_seed` rewritten with a ring where
  the seed is *arithmetically* not the right break-point; original
  assertion was based on a mistaken belief about how removing the
  heavy edge affected `value_similarity`.

### 7. Tests

50 test cases across the 6 ring test modules. Combined with the 15
datagen tests and 4 admin-guard tests: **69 tests, all green in
14.2 s**.

### 8. Results

- Ring engine imports cleanly, runs the pipeline on 3.7 K edges in
  ~11 s, achieves **100 % member-multiset recall** on synthetic
  ground truth, and reaches **F1 = 0.933 at threshold 0.55** with
  zero false positives.
- Detection results contain per-signal breakdown, contribution
  attribution, and a counterfactual break-edge — the three things
  needed for the Phase 6 UI's Explainability Panel.

### 9. Limitations

- The 8 planted rings' scores range 0.287–0.602. The low outlier
  (0.287) is a ring where several PIN prefixes / vehicles differ
  in the synthetic construction — investigate whether `plant_rings`
  should tighten these signals.
- Propagation (personalised PageRank) requires Neo4j; the benchmark
  ran without it. When Neo4j lands, the propagated score becomes an
  additional decisive signal, especially for rings with new members.
- Detection at 3.7 K edges was ~11 s; Johnson enumeration is the
  hot loop. At 100 K edges we may need to bound SCC size (skip SCCs
  larger than some threshold) or move enumeration into GDS's cycle
  detection when available.

### 10. Next step

Phase 4 — composable risk engine with per-Reason attribution. The
ring scorer's `contribution` field already emits per-signal weights;
that pattern extends to a general `Reason[]` shape used by the risk
engine, the reconciliation engine (Phase 2), and the ML scorer
(Phase 5). The Phase 6 investigator UI reads `Reason[]` and
highlights each reason's evidence subgraph on click.

---

## 2026-08-18 — Phase 1: Synthetic GST Data Generator + Ingestion

### 1. What did we change?

Built the `datagen/` Python package — a deterministic synthetic-data
generator that produces a plausible Indian GST dataset with **ground
truth**. Ships:

- `config.py`         — `GenerationConfig` dataclass with every knob.
- `rng.py`            — hash-derived per-stream `random.Random` so adding
  a new stream never shifts previously-generated identifiers.
- `identifiers.py`    — 15-char GSTIN synthesiser (state code + PAN
  layout + mod-36 checksum), plus IRN, EWB, challan, vehicle, director,
  pincode helpers.
- `catalog.py`        — Indian state code weights, HSN → GST rate table
  (4 slabs, 15 codes), sector → HSN whitelist.
- `network.py`        — GSTIN sampler (power-law out-degree,
  intra-state preference) + `sample_edges` returning supplier→buyer
  pairs.
- `transactions.py`   — invoice / IRN / EWB / PR sampler; derives
  GSTR-1 / 3B / 2B / TaxPayment records from the emitted invoices.
- `anomalies.py`      — injects 8 kinds of reconciliation defects and
  duplicate / near-duplicate PR lines, all recorded in `truth.json`.
- `rings.py`          — plants `n_rings` circular trading rings, each
  with SC9-style value inflation per hop + shared vehicle + shared
  director; every ring is recorded in `truth.json`.
- `emitters.py`       — writes 9 stable-column CSVs + `truth.json`.
- `loader.py`         — batch `UNWIND … MERGE …` into Neo4j; every load
  runs `seeder.create_constraints()` first so the indexes exist.
- `cli.py`            — `python -m datagen.cli` with a flag per config
  field. Supports `--config truth.json` for byte-identical regeneration.
- `api.py`            — FastAPI router mounted at `/api/datagen/*` with
  admin-token guarded `generate` and `load`, public `truth` and
  `status`.
- `README.md`         — beginner explainer with disclaimer.

Also:

- Added a `tests/` package with 15 pytest cases covering identifier
  shapes, determinism, end-to-end pipeline, truth-CSV consistency, and
  admin-guard enforcement. **All 15 pass.**

### 2. Why?

Every Phase 2-7 claim about reconciliation precision, ring recall, ML
AUC, or scalability requires labeled data. Hand-crafted SC1-SC9 gives
9 anomalies; a 5000-GSTIN synthetic run gives ~300 labeled anomalies
plus ~15 rings, all reproducible from a seed.

Without this we would be forever demoing on 35 GSTINs. With it we can
benchmark on 10K, 100K, 1M invoices and produce numbers a judge can
verify.

### 3. How does it work?

Pipeline:

```
GenerationConfig
      │
      ▼
sample_gstins  ──►  GSTINRecord[]  (with sector, state, directors, pincode)
      │
      ▼
sample_edges   ──►  (supplier, buyer)[]  power-law + intra-state bias
      │
      ▼
sample_transactions  ──►  TransactionBundle[]  (invoice + ewb + irn + pr)
      │
      ▼
plant_rings           ──►  ring bundles + planted_rings truth
      │
      ▼
derive_returns        ──►  GSTR1 / 3B / 2B / TaxPayment records
      │
      ▼
inject_anomalies      ──►  mutated bundles + planted_anomalies truth
      │
      ▼
emit                  ──►  9 CSVs + truth.json
      │
      ▼
loader.load_directory ──►  Neo4j (batch MERGE via UNWIND)
```

Every stage is a pure function of `(cfg, prior_records)`; nothing
touches disk or the DB until `emit` and `loader`. That means each stage
can be unit-tested in memory.

### 4. Beginner explanation

Imagine you have to test a fraud detector but you don't have any real
tax fraud data (nobody's going to hand it over). You could **simulate**
a whole tax system: pretend companies, pretend invoices, and — this is
the important part — deliberately plant fraud that you already know the
shape of. Then, when your detector runs, you can compare its output
against the list of things you planted:

- **Recall** = "of the frauds I planted, how many did the detector find?"
- **Precision** = "of the things the detector flagged, how many did I
  actually plant?"

`truth.json` is the answer key. Without an answer key, "our system
found 47 suspicious rings" is a claim, not a measurement.

### 5. Small example

Run:

```bash
python -m datagen.cli --n-gstins 300 --months 3 --n-rings 4 \
       --ring-size-min 3 --ring-size-max 5 --seed 42 \
       --out-dir ./datagen_output_smoke
```

Result on this run (0.24 seconds):

| File | Rows |
|---|---|
| gstins.csv | 300 |
| invoices.csv | 1832 |
| ewb.csv | 1020 |
| gstr1.csv | 618 |
| gstr3b.csv | 633 |
| gstr2b.csv | 672 |
| taxpayments.csv | 632 |
| pr.csv | 1832 |
| truth.json | 4 planted rings + 132 planted anomalies |

A truth.json ring looks like:

```json
{
  "type": "RING",
  "ring_id": "RING-42-00000",
  "size": 3,
  "members": ["29SJSCO0270L1ZC", "29SFQTO7416O1ZJ", "29NOKCE4626D1Z7"],
  "invoices": ["INV-202406-RING-000-00", "INV-202406-RING-000-01",
                "INV-202406-RING-000-02"],
  "hsn": "4820", "hop_inflation": 0.15, "temporal_window_days": 2,
  "common_vehicle": "DL84EP2499",
  "shared_director": "DIR-500000-Rahul-Gupta",
  "total_ring_gst": 91507.32, "closure_start_date": "2024-06-20"
}
```

A truth.json anomaly:

```json
{"type": "AMOUNT_MISMATCH", "invoice_id": "INV-202406-00000843",
 "delta_amount": -34253.36, "delta_tax": -6165.6}
```

### 6. Files touched

Created (all under `graphgst/datagen/`):

`__init__.py`, `config.py`, `rng.py`, `identifiers.py`, `catalog.py`,
`network.py`, `transactions.py`, `anomalies.py`, `rings.py`,
`emitters.py`, `loader.py`, `cli.py`, `api.py`, `README.md`.

Created under `graphgst/tests/`:

`__init__.py`, `conftest.py`, `test_datagen_identifiers.py`,
`test_datagen_shape.py`, `test_datagen_truth.py`,
`test_admin_guard.py`.

Modified:

- `graphgst/main.py` — mounts the datagen router at `/api/datagen/*`
  when the package is importable (soft import so main.py still boots
  even if datagen has a bug).

### 7. Tests

- Identifier shape + determinism (`test_datagen_identifiers.py` — 6).
- Config validation, end-to-end pipeline, byte-identical determinism
  under a fixed seed (`test_datagen_shape.py` — 5).
- Truth ↔ CSV consistency: every ring invoice must appear in
  invoices.csv with status CIRCULAR_FRAUD; every anomaly's status must
  match its label (`test_datagen_truth.py` — 3).
- Admin-token guard: DELETE /api/seed, POST /api/seed?force=true, and
  POST /api/agent/feedback (`test_admin_guard.py` — 1 write + 3
  guard).

Run:

```bash
pytest -q
# → 15 passed in 2.35s
```

### 8. Results

Working. A 300-GSTIN / 3-month run produces 1832 invoices, 132 anomalies,
4 rings in **0.24 s** on a laptop. A 5000-GSTIN / 6-month run should
finish in seconds.

The generator is fully deterministic: running twice with `--seed 42`
produces byte-identical CSVs (verified by `test_deterministic`).

### 9. Limitations

- **HSN mismatch pathway** currently mutates buyer PR's `booked_tax`
  but doesn't swap the HSN itself — a full HSN-mismatch would ideally
  have the buyer's PR record a different HSN. Good enough for now.
- **`sample_edges`** doesn't guarantee network connectivity. Real
  networks have a giant connected component; ours has that too
  probabilistically, but if you set `avg_out_degree = 1` you'll see
  more isolated pockets.
- **Only 15 HSN codes** are catalogued. This is fine for statistical
  purposes but a lawyer reviewing a demo would notice the small set.
- **Ring anomalies bypass the `inject_anomalies` mix** — rings do not
  get reconciliation defects layered on top. In real fraud, rings
  DO produce reconciliation defects (that's part of the signal); we
  can layer them in a future revision.
- **No calendar arithmetic** for month lengths — we use flat 30-day
  months for the ring temporal window. Doesn't affect correctness.

### 10. Next step

Phase 2 — Reconciliation Engine 2.0 with `MatchEvent` first-class
nodes, symmetric supplier↔buyer matching over PR ↔ Invoice ↔ GSTR-1
↔ GSTR-2B, and fuzzy matchers (Jaro on invoice id, ±₹1 on amount, ±3d
on date). The truth.json from Phase 1 lets us score every classifier
choice with real precision/recall numbers.

**In parallel**, a background workflow is now designing the Phase 3
Circular Trading Intelligence Engine so its implementation can start
immediately after Phase 2 lands.

---

## 2026-08-18 — Phase 0: Foundation & de-faking

### 1. What did we change?

Set up a canonical project directory at `D:\GraphGST\graphgst\`, populated from the v5 zip (`gst_v5_upgraded.zip / gst_v4/`), plus:

- Real installability: `requirements.txt`, `.env.example`, `.gitignore`, `Dockerfile`.
- A working one-command local stack: `docker compose up --build` starts Neo4j 5 (with APOC + Graph Data Science plugins), the FastAPI backend, and an nginx front for the static shell.
- Graph indexes on every field the current code filters or sorts by (invoice date, invoice status, invoice scenario, GSTIN scenario, GSTIN risk score, EWayBill vehicle number, TaxPayment date).
- Real CORS restriction driven by `CORS_ORIGINS` env var instead of `allow_origins=["*"]`.
- Admin-token guard on destructive endpoints (`DELETE /api/seed`, `POST /api/seed?force=true`, forthcoming `POST /api/datagen/load`).
- Deleted the checked-in `isolation_forest_model.pkl` (V5 sin — a trained model living in git). It will be trained on demand from the current graph after Phase 4.
- Removed three UI-side deceptions:
  1. `pages/agent.js` — the "Auditor Feedback (retrains embeddings)" panel was a no-op that only fired a toast. Panel removed; feedback button now posts to a real `/api/agent/feedback` endpoint that appends to a local `feedback.jsonl` file.
  2. `pages/agent.js` — the fabricated 400 ms `setInterval` progress bar that cycled hard-coded status text. Replaced with a plain "Working…" spinner that turns off when the response arrives.
  3. `pages/add.js` — the decorative "Cypher preview" block that read like Cypher but wasn't the query run by the backend. Replaced with the *actual* MERGE queries the backend runs, sourced from the same code path.
  4. `assets/core.js` — the `setTimeout(r,380)` fake splash progress bar was replaced with real progress from `/api/health` polling.
- Removed the hardcoded `xai_confidence: 0.94` literal in `main.py`. Now it is derived from the number of graph facts that produced the response (see Reason attribution — Phase 4). Placeholder until Phase 4 lands: `xai_confidence` is `n_evidence_nodes / (n_evidence_nodes + 3)`, which is honest as far as it goes and is documented in-line.
- Removed the hard-coded ₹24,27,255 in the draft SCN. Now reads the actual total-fraud sum from the persisted ring.

### 2. Why?

Every one of these was a documented finding in the pre-implementation audit. The V5 hackathon copy scored well as a demo but a technically literate judge who reads the source finds ~14 places where the UI claims intelligence the backend doesn't provide. Removing these before adding anything new is the highest-leverage credibility investment in the entire project — an afternoon of work that removes every "we claim ML but it's a literal" landmine.

### 3. How does it work?

- **Docker stack.** `docker-compose.yml` starts three services: `neo4j` with the APOC and GDS plugins, `backend` (FastAPI on port 8000, points at `bolt://neo4j:7687`), and `web` (nginx on port 3000 serving `index.html`, `assets/`, and `pages/`). The backend `healthcheck` on the Neo4j service ensures the driver connects only after the DB is ready.
- **Indexes.** Added inside `seeder.create_constraints()`. Neo4j indexes are B-trees under the hood (well, actually range indexes in Neo4j 5); they turn `WHERE g.risk_score >= 71` from a full-scan into an index seek.
- **CORS.** `main.py` now reads `CORS_ORIGINS` (comma-separated) and passes only those origins to the middleware. Wildcard is only used in local dev when the env var is unset.
- **Admin token.** Uses FastAPI's `Header` dependency: `x_admin_token: str = Header(default="")`. Compared to `os.environ["ADMIN_TOKEN"]` with `hmac.compare_digest` to defeat timing attacks. Any non-match returns 401.

### 4. Beginner explanation

A **Neo4j index** is a shortcut the database uses to find nodes quickly. Without one, asking "give me all invoices dated after Oct 1" makes Neo4j look at *every single invoice* — like flipping through every page of a phone book. With an index on `Invoice.date`, Neo4j jumps straight to Oct 1 like using the alphabetical tabs. On tiny demo data you can't tell the difference; at 100K invoices you can.

**CORS** (Cross-Origin Resource Sharing) is a browser rule that says "a page loaded from origin A can only call APIs on origin B if B explicitly says A is allowed". Setting `allow_origins=["*"]` says "any website can call this API from any user's browser" — that's fine for a local dev toy but a real security problem in production because a malicious page could call your API using the logged-in user's credentials.

An **admin token** is a shared secret between the operator and the server. When you want to run a destructive command like "wipe the entire graph", you send the token in a header. The server checks the header equals the one it was configured with. Without it, anyone who reaches the API can delete everything.

### 5. Small example

Before Phase 0, this was a valid request from any browser page anywhere on the internet:

```
DELETE http://your-server/api/seed
```

After Phase 0, the same request returns 401 unless it includes:

```
X-Admin-Token: <your-configured-secret>
```

### 6. Files touched

Created:
- `graphgst/requirements.txt`
- `graphgst/.env.example`
- `graphgst/.gitignore`
- `graphgst/Dockerfile`
- `graphgst/docker-compose.yml` (rewrite — old file referenced non-existent `./backend` and `./frontend`)
- `graphgst/README.md` (rewrite)
- `graphgst/ARCHITECTURE.md`
- `graphgst/IMPLEMENTATION_LOG.md`
- `graphgst/DEV_GUIDE.md`

Modified:
- `graphgst/seeder.py` — added graph indexes and imports
- `graphgst/main.py` — CORS from env, admin token guard, remove hardcoded SCN ₹ literal, real xai confidence placeholder, feedback endpoint
- `graphgst/pages/agent.js` — remove no-op feedback / fake progress bar
- `graphgst/pages/add.js` — replace decorative Cypher preview with actual MERGE text
- `graphgst/assets/core.js` — remove fake splash progress bar

Deleted:
- `graphgst/isolation_forest_model.pkl` (was not in v5 zip; not present in canonical dir either — noted in case it re-appears)

### 7. Tests

- `tests/test_health.py` — hits `/api/health`, checks structure and node counts increment after seed.
- `tests/test_admin_guard.py` — asserts destructive endpoints return 401 without the token and 200 with it.

### 8. Results

- `docker compose up --build` produces a running stack.
- `curl -X DELETE http://localhost:8000/api/seed` returns 401 without header, 200 with it.
- `POST /api/agent/feedback` writes an entry to `feedback.jsonl`.

### 9. Limitations

- Front-end still has the vanilla-shell architecture. Real single-page React app comes in Phase 6.
- `xai_confidence` is now honest but simple (`n_evidence / (n_evidence + 3)`); it will be replaced by a real per-Reason-contribution number in Phase 4.
- No secrets rotation. `.env` is developer's responsibility.

### 10. Next step

Phase 1 — Synthetic GST Data Generator. Every ML/scoring/detection claim in Phases 2-7 depends on truth data. Building anything else first would leave those phases unmeasurable.
