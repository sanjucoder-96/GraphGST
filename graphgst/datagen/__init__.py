"""datagen — synthetic GST dataset generator with ground truth.

Modules
-------
config        : GenerationConfig dataclass, defaults, CLI parsing helper.
rng           : deterministic RNG wrapper — every random draw is seeded.
identifiers   : GSTIN / PAN / IRN / EWB / challan / vehicle number synthesis.
catalog       : Indian state codes, HSN → GST rate table, sector taxonomy.
network       : samples the supplier-buyer bipartite backbone.
transactions  : samples invoices, GSTR-1/2B/3B, TaxPayments, EWBs.
anomalies     : plants reconciliation mismatches with truth labels.
rings         : plants circular-trading rings with truth labels.
emitters      : writes CSVs (one per return type) + truth.json.
loader        : batch MERGE into Neo4j via UNWIND.
cli           : `python -m datagen.cli` entry point.
api           : FastAPI router mounted at /api/datagen by main.py.

Every RandomState in this package is derived from `GenerationConfig.seed`
so a given (seed, config) always produces the same output. That guarantee
is what lets us report reproducible precision/recall numbers.
"""

__all__ = [
    "config",
    "rng",
    "identifiers",
    "catalog",
    "network",
    "transactions",
    "anomalies",
    "rings",
    "emitters",
    "loader",
]
