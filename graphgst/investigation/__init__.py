"""Investigation domain — the canonical Case service + API.

A "case" is one entity (GSTIN) under investigation, assembled server-side into
ONE coherent object (entity + composed risk + rings + reconciliation + exposure
+ related vendors + timeline + subgraph) so the frontend never reconstructs an
investigation from 6-10 unrelated endpoints. See docs/INVESTIGATION_MODEL.md.
"""
