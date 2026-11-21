"""Deterministic RNG helpers.

Every module in datagen imports `derive(seed, tag)` and uses the returned
`random.Random` instance for its draws. Tagging isolates streams so that
adding a new anomaly type doesn't shift every previously-generated ID.
"""
from __future__ import annotations

import hashlib
import random
from typing import Iterable


def derive(base_seed: int, tag: str) -> random.Random:
    """Return a Random instance seeded deterministically from (seed, tag).

    Example
    -------
    >>> rng_a = derive(42, "network")
    >>> rng_b = derive(42, "network")
    >>> rng_a.random() == rng_b.random()
    True
    """
    h = hashlib.blake2b(digest_size=8)
    h.update(str(base_seed).encode())
    h.update(b"::")
    h.update(tag.encode())
    return random.Random(int.from_bytes(h.digest(), "big"))


def weighted_choice(rng: random.Random, weights: dict) -> str:
    """Sample a key from a {key: weight} dict; weights need not sum to 1."""
    keys, ws = zip(*weights.items())
    return rng.choices(keys, weights=ws, k=1)[0]


def weighted_sample_without_replacement(
    rng: random.Random, population: Iterable, weights: Iterable[float], k: int
) -> list:
    """Draw k items from population without replacement, weighted.

    Uses Efraimidis-Spirakis: assign each item a key = u^(1/w) and take
    the top-k by key. Robust to zero-weight items (those are excluded).
    """
    population = list(population)
    weights = list(weights)
    keyed = [
        (rng.random() ** (1.0 / w) if w > 0 else -1.0, i, item)
        for i, (item, w) in enumerate(zip(population, weights))
    ]
    keyed.sort(reverse=True)
    return [item for _, _, item in keyed[:k]]
