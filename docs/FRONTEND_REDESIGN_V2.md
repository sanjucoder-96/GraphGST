# Frontend — "SIGNAL" Design System (V2)

The current frontend direction, why the previous one was rejected, and what the
V6.2 pass changed. Written so a reviewer can judge the visual philosophy without
running the app.

> **Honest scope note.** The editorial→SIGNAL redesign (the substance of this
> document) was implemented in the phase before V6.2. The V6.2 pass **verified
> it renders correctly against the live backend**, wired the investigation queue
> to real composed risk, made the API base configurable, and documented the
> system here. Where this doc says "we did X", X is in the code today
> (`web/src/styles/tokens.css`, `web/src/components/*`, `web/src/pages/*`); it is
> not aspirational.

## Why the previous design was rejected

The earlier direction drifted into an **editorial / literary** aesthetic that
read as a magazine, not an intelligence tool:

- warm copper/orange accent overload and parchment/paper surfaces
- serif display type (Fraunces), heavy italic styling
- "case-file" branding language — *Docket, Dossier, Behavioural Kinship,
  Attestations, Provenance, Ledger*

None of that signals *financial-crime investigation software*. It looked
expensive in the wrong genre. It is gone: no Fraunces, no copper, no parchment,
no italic branding, and the vocabulary is now **Cases, Rings, Vendors,
Reconciliation, Risk, Data Sources, Model Card** (verified in
`web/src/components/LeftRail/LeftRail.tsx`).

## New visual philosophy — a cool, dark intelligence terminal

SIGNAL is a 2026 enterprise financial-intelligence workspace: graph-analytics ×
fraud-investigation × high-end fintech. Principles, all encoded as tokens
(`web/src/styles/tokens.css`):

- **Cool graphite/slate foundation.** Five near-black surfaces from `#070A0F`
  (app ground) up to `#1E2632` (selected). No warm hues anywhere.
- **Restraint.** One brand accent — electric indigo-blue `#4F80FF` — used *only*
  for selection / active / primary. Decoration does not get color.
- **Color = meaning.** A single risk ramp expresses severity and nothing else:
  `#29C79A` clean → `#E0A63A` elevated → `#F0743F` high → `#F24E63` critical.
  Semantic aliases (`--ok/--warn/--bad/--info`) forbid ad-hoc hexes in
  components.
- **High information density.** A 4px spacing base, a 10-46px type scale, 34px
  table rows, a 48px top bar — an analyst sees a lot at once, deliberately.
- **Subtle depth, no gimmicks.** Layered cool shadows; no glassmorphism overload,
  no neon cyberpunk, no gradients-as-personality.

## Typography

- **Product sans: Geist**, with Inter as fallback — modern, technical, neutral.
- **Mono: Geist Mono** for every technical identifier and figure — GSTINs, IRNs,
  invoice ids, amounts, timestamps — with `tabular-nums` so columns of numbers
  align. This is the one deliberate type contrast: prose in sans, evidence in
  mono. No serif anywhere.

## The workspace architecture (already built)

The component set maps directly onto an investigation workflow:

| Area | Component | Role |
|---|---|---|
| Shell | `AppShell`, `LeftRail`, `TopBar` | dense app chrome, sectioned nav, search/alerts/latency |
| **Case queue** | `pages/CaseQueue` | the investigation queue — a real table (Risk / Entity / Primary signal / Reasons / Exposure / Age / Status), severity/type/sort filters, `j`/`k`/`enter` keyboard nav |
| **Graph** | `components/GraphCanvas` (Cytoscape) | the centerpiece — node categories, directional edges, hover/selected/ring emphasis, layout modes |
| **Inspector** | `components/EvidencePanel`, `SignalGauge`, `ReasonChip` | why-flagged, the six signals, evidence, selected entity |
| **Temporal** | `components/TimelineScrubber` | replay of ring formation over time |
| **Network** | `components/RelatedVendors` | embedding-based related entities |
| Counterfactual | `components/BreakSimulator` | which edge, removed, most reduces the ring score |
| Command | `components/CommandPalette`, `ShortcutsOverlay` | ⌘K palette, `?` shortcuts |

Investigation flows: **Case queue → open entity/ring → graph + evidence
inspector → timeline replay → break simulator.** Progressive disclosure, not
everything at once.

## V6.2: wiring the queue to REAL composed risk

The most important V6.2 frontend change is not visual — it is that the
investigation queue now shows **real data from Neo4j**, fast:

- The queue previously read the legacy `/api/vendors/risk` endpoint, which
  recomputes IsolationForest + graph centrality **per request** (~9s against a
  remote Aura instance) and returns a `{vendors, summary}` shape the UI could
  not map — so live data rendered **zero rows** and the UI silently fell back to
  demo fixtures.
- It now reads the **modern composer** `GET /api/risk/summary` (~2.6s), enriched
  server-side with entity `name`/`state`/`scenario`, and normalized to the
  queue's row shape in `web/src/lib/api.ts::getCases`. Verified live: 200 real
  entities (e.g. *Tirupati Foods & Co*, *Sunrise Textiles Enterprises*) with real
  composed scores and real reason text, `LIVE` badge, no fixtures.
- The API base is now configurable via `VITE_API_BASE` (`web/src/lib/api.ts`) so
  the backend can run on any port, and the client abort budget was raised from
  2.5s → 8s so genuine remote-DB queries complete instead of spuriously falling
  back to mocks.

The mock fallback remains **by design** — when the backend is unreachable the UI
serves labelled demo fixtures and shows a `DEMO` badge, so the product is always
demonstrable. It is a fallback, not the default when live.

## Accessibility & keyboard workflow

- Focus is always visible: a 2px brand focus ring (`--ring`) on
  `:focus-visible`, never removed.
- Full keyboard model: ⌘K command palette, `?` shortcuts overlay, `g c/r/v`
  section jumps, `j/k/enter` to move and open rows in the queue.
- Text ramp holds contrast on the dark ground (primary `#F1F5FB` on `#070A0F`).
- Mono `tabular-nums` keeps financial figures scannable.

## On 21st.dev

This pass did **not** fetch 21st.dev components — the SIGNAL system and its
components already existed and are internally coherent, so importing external
components would have fragmented the design rather than improved it. The
components above are bespoke to Graph GST and share one token system. If a future
pass adds a component (e.g. a virtualized data grid), it should adopt these
tokens rather than arrive with its own look.

## What a future visual pass could still do

Honest backlog (not blockers): richer per-entity **exposure** and **ring**
columns in the live queue (needs a dedicated cases endpoint that joins invoice
totals + ring membership); a graph **minimap** for large neighborhoods; and a
screenshot-based visual regression check (blocked in this environment by a
Windows browser-pane compositing issue, so V6.2 verification used the DOM +
computed styles instead of pixels).
