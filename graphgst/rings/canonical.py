"""Rotational canonicalisation and content-hashing for detected cycles.

Why: Johnson's algorithm (and any DFS-based cycle enumerator) can emit
the SAME elementary cycle starting from any of its nodes — an n-cycle
can appear n times as rotations of one another. We want ONE stable id.

Strategy:
  1. If the cycle came in with the start node repeated at the end
     ([A,B,C,A]), strip that closing duplicate.
  2. Refuse self-loops ([A,A] -> after strip [A] which is degenerate)
     and non-elementary cycles (repeat non-adjacent to closure).
  3. Rotate so the lex-smallest member sits at index 0.
  4. Hash the joined tuple with SHA-1 (NOT builtin hash() — that is
     salted per process on Python 3, so ring ids would differ across
     runs and MERGE-idempotency in Neo4j would silently break).

Direction is preserved: [A,B,C] and its reverse [A,C,B] both rotate to
start with A but produce different tuples -> different ring_ids.
Circular trading is directed (supplier -> buyer), so this is correct.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, List, Sequence, Tuple


def _strip_closing(members: Sequence[str]) -> List[str]:
    m = list(members)
    if len(m) >= 2 and m[0] == m[-1]:
        m = m[:-1]
    return m


def canonicalize(members: Sequence[str]) -> Tuple[str, ...]:
    """Rotate `members` so it starts with its lex-smallest element.

    Rejects self-loops and non-elementary cycles (any repeat besides
    the optional closing dup which is stripped first).

    Returns an immutable tuple so callers can safely use it as a dict
    key or set element.
    """
    if members is None:
        raise ValueError("members is None")
    m = _strip_closing(members)
    if len(m) < 2:
        raise ValueError(f"cycle too short (self-loop or singleton): {members!r}")
    if len(set(m)) != len(m):
        raise ValueError(f"non-elementary cycle (duplicate member): {members!r}")
    smallest = min(range(len(m)), key=lambda i: m[i])
    rotated = m[smallest:] + m[:smallest]
    return tuple(rotated)


def ring_id(members: Sequence[str]) -> str:
    """Deterministic ring id derived from canonical member tuple."""
    canon = canonicalize(members)
    key = "|".join(canon)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"R-{digest}"


def dedup_cycles(cycles: Iterable[Sequence[str]]) -> List[Tuple[str, ...]]:
    """Collapse rotational duplicates. Preserves first-seen ordering."""
    seen: dict = {}
    for c in cycles:
        try:
            rid = ring_id(c)
        except ValueError:
            continue
        if rid not in seen:
            seen[rid] = canonicalize(c)
    return list(seen.values())
