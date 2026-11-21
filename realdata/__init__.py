"""realdata — evaluate Graph GST against real / public datasets.

Kept deliberately separate from `demo/` and `benchmarks/`. Loading real data
NEVER touches the nine gated benchmark metrics: those run fully in-memory on the
synthetic `truth.json` (see docs/BENCHMARKS.md) and never read Neo4j or this
package. See docs/REAL_DATA.md for the full story and reproduction commands.
"""
