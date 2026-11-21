# Graph GST — Investigator Console (web)

A Vite + React 18 + TypeScript (strict) SPA that drives the Graph GST fraud
investigation workflow. Renders a live Cytoscape.js graph of GSTINs, invoices,
rings and vehicles; a six-signal explainer for every detected ring; a real
timeline scrubber that animates ring edges by `invoice.date`; and a
data-driven "break the ring" counterfactual simulator.

The console is designed to feel like an instrument — dark charcoal chrome,
narrow greyscale ramp, tabular monospace numerics, one signal color
(#F2A63A sodium-lamp amber) for the thing the investigator must look at next.

## Setup

Prereqs: **Node 20+** and **npm 10+**.

```bash
cd graphgst/web
npm install
npm run dev            # http://127.0.0.1:5173
```

Type-check without a build:

```bash
npm run typecheck
```

Production build:

```bash
npm run build
npm run preview        # http://localhost:4173
```

The dev server is hosted on `127.0.0.1` for consistency across platforms
and calls the backend at `http://localhost:8000` (see
`src/lib/api.ts` for `API_BASE`).

## Mock fallback (no backend needed)

When the FastAPI backend is offline every API function in `src/lib/api.ts`
resolves from `src/lib/mocks.ts`. The environment badge in the top bar flips
from **LIVE** (amber) to **DEMO** (grey) whenever any request has fallen
back in the last 30 seconds, and a 20-second health probe against
`/api/dashboard/summary` restores it to LIVE the moment the backend answers.

The demo fixture is deliberately small but complete:

- **3 real rings** (`RING-2024-A417`, `RING-2024-B209`, `RING-2024-C083`) with
  live 6-signal scores that discriminate against **2 noise rings** with
  deliberately low scores.
- **12 unique GSTINs** across three Indian states (MH, DL, KA).
- **8 audit trails** with 8 narrative hops each — covering all 4 legs of
  ring 1 plus the first two legs of rings 2 and 3.
- A Cytoscape graph payload derived from those rings so the canvas has a
  real substrate.

Every visible number in the app either resolves to an API field
(`ring.score`, `signals.C..H`, `per_edge[].score_drop`, `audit.hops[]`, …)
or to one of these labeled DEMO values. There are no fabricated confidence
or progress numbers on the frontend — `xai_confidence` is surfaced when the
backend provides it.

## Integrating with the backend

The frontend expects these endpoints (see `graphgst/rings/api.py` and
`main.py` in the parent repo):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/rings/`                                    | list rings (score-sorted) |
| GET | `/api/rings/{ring_id}`                           | ring detail (signals, per_edge, break_edge) |
| POST | `/api/rings/detect`                             | run detection pipeline |
| GET | `/api/vendors/risk`                              | vendor risk + IsolationForest anomaly |
| GET | `/api/graph/full`                                | Cytoscape-shaped nodes + edges |
| GET | `/api/reconcile/audit-trail/{invoice_id}`        | 8-hop audit narrative |
| GET | `/api/dashboard/summary`                         | overview counters + neo4j status |
| POST | `/api/agent/query`                              | intent-routed explanation (e.g. `circular_fraud`) |

To point the console at a different backend, change `API_BASE` in
`src/lib/api.ts`. The health-probe cadence and fallback window can be tuned
via the constants at the top of the same file.

## Replacing the DEMO fixture

`src/lib/mocks.ts` is intentionally the only place that fabricates data.
Replace the `MOCK_RINGS`, `MOCK_VENDORS`, `MOCK_AUDIT_TRAILS`, `MOCK_GRAPH`
and `MOCK_DASHBOARD` exports with real captures from your backend to demo
against a snapshot. The exports match the domain types in
`src/types/domain.ts` exactly, so type-checking your captures against those
types is the safest replacement path.

## Keyboard

| Combo | Action |
| --- | --- |
| `⌘K` / `Ctrl+K` / `/` | Open command palette |
| `g q` | Go to Case Queue |
| `g v` | Go to Vendors |
| `g h` | Go to Data Health |
| `j` / `k` | Next / previous row (Case Queue) |
| `Enter` | Open selected row |
| `1` / `2` / `3` | Overview / Evidence / Counterfactual tab |
| `[` / `]` | Prev / next ring |
| `+` / `-` / `0` / `f` | Graph zoom / fit / frame |
| `⇧E` / `I` / `H` / `M` / `⌘C` / `A` | Expand / isolate / hide / mark / copy / audit |
| `Space` | Timeline play / pause |
| `←` / `→` | Timeline step (Shift = ×7) |
| `Home` / `End` | Timeline first / last |
| `Esc` | Close palette / clear selection |

## What this app does NOT do

- No fake progress bars anywhere. Every ticking widget is bound to a real
  event (fetch resolve, timeline tick with a corresponding invoice date).
- No fabricated confidence numbers. `xai_confidence` is displayed only when
  the API returns it; otherwise the field is omitted.
- No decorative loading text or shimmer skeletons under 100 ms.
- No CDN icon library — Lucide is bundled via npm.
- No Tailwind and no shadcn. All styling is CSS Modules + tokens in
  `src/styles/tokens.css`. The visual identity is deliberately its own.

## Repo layout

```
web/
  index.html
  package.json
  tsconfig.json
  vite.config.ts
  README.md
  src/
    App.tsx               — routes + QueryClient
    main.tsx              — React entry
    index.css             — imports reset + tokens
    styles/
      reset.css
      tokens.css          — the entire design vocabulary
    lib/
      api.ts              — typed fetch wrappers with mock fallback
      mocks.ts            — the DEMO fixture
      store.ts            — Zustand (light)
      keyboard.ts         — global shortcuts hook
    types/
      domain.ts           — Ring, Vendor, AuditTrail, GraphPayload
    components/
      AppShell/           — grid + status footer
      LeftRail/           — 52px icon nav
      TopBar/             — search + env badge + latency
      CommandPalette/     — ⌘K fuzzy palette
      GraphCanvas/        — real Cytoscape.js + cose-bilkent
      EvidencePanel/      — 3-tab evidence sidebar + SignalGauge + ReasonChip
      TimelineScrubber/   — real per-date edge animation
      BreakSimulator/     — segmented ring driven by per_edge[]
      RiskSparkline/      — 64×16 tabular-nums sparkline
      Toast/              — real-event toast stack
      ui/                 — Button, Pill, KBD primitives
    pages/
      CaseQueue/          — ranked open alerts
      Investigation/      — canvas + evidence (entity + ring modes)
      RingExplorer/       — Investigation with timeline docked
      DataHealth/         — backend + fixture health board
```

## Runbook — offline demo

If Neo4j is down mid-demo:

1. The environment badge in the top bar reads **DEMO**.
2. The status footer shows `NEO4J OFF`.
3. Every screen still works; every number is served from `mocks.ts`.
4. Detection and wipe buttons remain enabled but a toast will confirm that
   the call fell back.
5. The Draft SCN button falls back to a local template, and the toast
   surfaces the fact that the agent intent was unavailable.
