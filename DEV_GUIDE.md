# Developer Guide — Graph GST V6

Written for a CS student. If a term seems obvious skip it; if not read the box.

## 0. The 30-second mental model

Imagine every GSTIN, every invoice, every tax return, every payment, every e-Way Bill in India as a labeled dot. Now draw arrows between them: "this taxpayer issued this invoice", "this invoice was declared in this GSTR-1", "this GSTR-3B was settled by this challan". That giant labeled dots-and-arrows picture is a **knowledge graph**.

Graph GST is a service that stores this picture in Neo4j and then asks questions like:

- "Is there a closed loop of invoices among a group of taxpayers?" (circular trading)
- "Did the supplier actually pay tax on this invoice?" (ITC validation)
- "Give me every taxpayer whose invoices in the last month produced ≥ 3 amount-mismatch events *and* participate in a temporal loop." (multi-signal risk)

Traditional SQL databases can answer the first two if you write enough JOINs. The third one, and everything that involves following a chain of relationships of unknown length, is where a graph database becomes the right tool.

## 1. Repository tour

```
graphgst/
├── main.py                 ← FastAPI app; every HTTP route
├── db.py                   ← Neo4j driver + run_query / run_write helpers
├── seeder.py               ← Hand-crafted demo scenarios SC1..SC9
├── risk_engine.py          ← Rule scoring, cycle detection, audit narrative, ML
├── risk_propagation.py     ← Placeholder for Phase 4 personalized-PageRank
├── datagen/                ← Synthetic GST generator (Phase 1)
│   ├── config.py           ← GenerationConfig dataclass
│   ├── rng.py              ← Deterministic randomness helper
│   ├── identifiers.py      ← GSTIN / IRN / EWB / challan generators
│   ├── catalog.py          ← HSN → GST rate tables; Indian state distribution
│   ├── network.py          ← Business-network graph sampler
│   ├── transactions.py     ← Invoice + return + payment sampler
│   ├── anomalies.py        ← Injects reconciliation mismatches with truth
│   ├── rings.py            ← Plants circular-trading rings with truth
│   ├── emitters.py         ← Writes CSVs and truth.json
│   ├── loader.py           ← Reads CSVs and MERGEs into Neo4j
│   └── cli.py              ← argparse entry point (python -m datagen.cli)
├── pages/                  ← Vanilla-JS pages (Phase 0 stopgap)
├── assets/                 ← core.js and app.css (Phase 0 stopgap)
├── index.html              ← Shell that loads pages/*.js
├── tests/                  ← pytest test suite
├── ARCHITECTURE.md         ← Target design (V6)
├── IMPLEMENTATION_LOG.md   ← Running change log — read this first
└── README.md               ← Quick start
```

## 2. Neo4j 101 — Cypher

Neo4j speaks a query language called **Cypher**. Three shapes to remember:

```cypher
// A pattern reads "left to right, node with label GSTIN, connected by ISSUED_INVOICE,
// to a node with label Invoice".
MATCH (g:GSTIN)-[:ISSUED_INVOICE]->(i:Invoice)
WHERE g.state = 'Karnataka'
RETURN g.name, i.invoice_id, i.total_gst
LIMIT 10

// MERGE = get-or-create. Never inserts a duplicate as long as the key matches.
MERGE (g:GSTIN {gstin_id: '29CGST0001R1ZA'})
ON CREATE SET g.name = 'Sunrise Impex', g.state = 'Karnataka'

// Variable-length paths — the * is the key.
// *1..5 = "between 1 and 5 hops long"
// This one finds cycles: same node at both ends.
MATCH path = (a:GSTIN)-[:ISSUED_INVOICE*2..5]->(a)
RETURN path
```

## 3. Terms defined in beginner language

**SCC (Strongly Connected Component).** In a directed graph, a strongly connected component is a group of nodes where every node can reach every other node in the group by following the arrows. Non-trivial SCCs are the ONLY places cycles can hide, so if you compute SCCs first, you can look for cycles only inside each SCC — a huge speedup. Algorithms: Tarjan (O(V+E)) or Kosaraju.

**Johnson's algorithm.** Finds every elementary cycle in a directed graph. It's exponential in the worst case (some graphs have exponentially many cycles) but polynomial per cycle output. Combined with SCC pre-filter and a hop bound, it becomes usable.

**Cycle canonicalization.** When you find a cycle like A→B→C→A, the same cycle can also be discovered as B→C→A→B or C→A→B→C. To deduplicate, rotate every cycle to start with its lexicographically smallest member. Then A→B→C→A and its rotations all hash to the same string.

**PageRank.** Google's original ranking algorithm. It assigns each node a "importance" score by simulating a random walker who occasionally teleports. A node has high PageRank if lots of highly-ranked nodes link to it. In GST-land, high PageRank ≈ "many suppliers or buyers depend on this taxpayer".

**Personalized PageRank.** Same idea but the random walker's teleport isn't uniform — it teleports back to a specific set of "seed" nodes. If you seed from confirmed fraudulent GSTINs, the resulting scores rank every other GSTIN by "closeness (in the graph sense) to known fraud". This is the propagation used in Phase 4.

**Betweenness centrality.** For each node, count the fraction of shortest paths between other pairs of nodes that pass through it. High betweenness = "bridge" or "chokepoint". Expensive: O(V·E) for exact computation.

**Node2Vec / embeddings.** A way to turn each node into a fixed-length vector of numbers such that nodes that appear in similar graph contexts end up with similar vectors. Once you have vectors you can do k-NN (find the k closest ones by cosine similarity). Application: "vendors that behave like this suspect".

**Graph motif.** A small, specific sub-shape (3-node triangle, 4-node square, star). Frequent unusual motifs can flag structural anomalies.

**Temporal graph.** A graph where edges have valid-from / valid-to timestamps, so you can ask "what did the graph look like on 15 Nov?" or "did this cycle appear within 72 hours?".

**Anomaly detection.** ML task: find points that are unlike the rest. IsolationForest, Local Outlier Factor, and autoencoders are common approaches. In a graph, features can be structural (degree, PageRank, community size).

**IsolationForest.** Builds many random trees; a data point is anomalous if it lands in a shallow leaf on average (few random splits isolate it). Works well without labels, unlike supervised classifiers.

**Precision, Recall, F1.** Precision = of the things you flagged, how many were truly bad? Recall = of the truly-bad things, how many did you flag? F1 = harmonic mean. Ground truth is required — hence Phase 1.

**Counterfactual analysis.** Ask "what if I change one thing?" Here: "if I remove *this* invoice edge from the ring, does the risk score still stay above threshold?" The edge with the largest score drop is the "break point" the investigator should attack first.

## 4. Running things locally

- **Everything.** `docker compose up --build`
- **Just the backend after code edits.** `docker compose restart backend`
- **Fresh graph.** `curl -X DELETE -H "X-Admin-Token: dev-admin-token-change-in-prod" http://localhost:8000/api/seed`
- **Seed demo scenarios.** `curl -X POST http://localhost:8000/api/seed`
- **Generate 10K-invoice synthetic dataset.** `python -m datagen.cli --n-gstins 3000 --months 6 --seed 42 --out ./datagen_output`
- **Load a generated dataset.** `curl -X POST -H "X-Admin-Token: dev-admin-token-change-in-prod" "http://localhost:8000/api/datagen/load?dir=./datagen_output"`
- **Run tests.** `pytest -q`

## 5. Common pitfalls

- **Line endings.** Windows editors often save with CRLF; git may re-write LF↔CRLF. Prefer UTF-8 + LF for source files. `.gitattributes` in a future commit will enforce this.
- **`nx.simple_cycles` on a real graph.** Do not call `networkx.simple_cycles(G)` without a hop bound. NetworkX explores all cycles; graphs with even a small dense SCC can have millions.
- **`MATCH path=(a)-[*..K]->(a) LIMIT N`.** The `LIMIT N` limits results but Neo4j still explores every path first. Combine with an SCC pre-filter or a specific start node.
- **The IsolationForest pickle.** Never commit trained models to git. Always retrain from live data on first run.
- **CRLF-mode diff noise.** When diffing V6 against V5, use `git diff --ignore-cr-at-eol` or `tr -d '\r'` first, or every line will show as changed.

## 6. Contributing (self-directed)

1. Pick a phase from `IMPLEMENTATION_LOG.md`'s "Next step" section.
2. Write a plan-shaped PR description before writing code.
3. Write the test first if the module can be tested (loaders, parsers, scorers).
4. Update `IMPLEMENTATION_LOG.md` with a new dated entry using the 10-question template.
5. Update `ARCHITECTURE.md` if you changed the design, not the code.
