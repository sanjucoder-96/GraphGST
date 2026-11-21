"""Identifier synthesis — GSTIN, PAN, IRN, EWB, challan, vehicle.

These emit strings that follow the *shape* of real Indian identifiers so
the demo looks credible. They are NOT valid tax IDs — checksums are
plausible but not GSTIN-portal-verified. Never seed a live GST portal
with output from this module.
"""
from __future__ import annotations

import random
import string
from typing import Optional

from .catalog import PAN_ENTITY_TYPES, PAN_ENTITY_WEIGHTS


def _rand_letters(rng: random.Random, n: int) -> str:
    return "".join(rng.choices(string.ascii_uppercase, k=n))


def _rand_digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choices(string.digits, k=n))


def synth_pan(rng: random.Random, entity_type: Optional[str] = None) -> str:
    """A synthetic 10-character PAN like 'AAPFU0939F'.

    Layout: 5 letters + 4 digits + 1 letter.
    Position 4 = entity type (P/F/C/H/A/T…). Position 5 = a surname letter.
    """
    et = entity_type or rng.choices(PAN_ENTITY_TYPES, weights=PAN_ENTITY_WEIGHTS, k=1)[0]
    base = _rand_letters(rng, 3) + et + _rand_letters(rng, 1)
    return base + _rand_digits(rng, 4) + _rand_letters(rng, 1)


_GSTIN_CHECK_ALPHABET = string.digits + string.ascii_uppercase


def _gstin_checksum(payload14: str) -> str:
    """Mod-36 checksum used by many GST demo tools.

    Real GSTIN checksum is proprietary; this is a plausible mod-36 stand-in
    that produces a stable character. Consistent enough to look real.
    """
    total = 0
    for i, ch in enumerate(payload14):
        v = _GSTIN_CHECK_ALPHABET.index(ch)
        factor = 2 if i % 2 == 0 else 1
        prod = v * factor
        total += prod // 36 + prod % 36
    return _GSTIN_CHECK_ALPHABET[(36 - (total % 36)) % 36]


def synth_gstin(
    rng: random.Random,
    state_code: str,
    entity_type: Optional[str] = None,
    entity_number: int = 1,
) -> str:
    """Return a 15-char GSTIN like '27AAPFU0939F1ZV'.

    state_code    : 2-digit state code (see catalog.STATES)
    entity_number : 1-9 or A-Z (usually 1)
    """
    pan = synth_pan(rng, entity_type)
    ent = str(entity_number) if entity_number <= 9 else "A"
    payload14 = f"{state_code}{pan}{ent}Z"
    check = _gstin_checksum(payload14)
    return payload14 + check


def synth_irn(rng: random.Random) -> str:
    """64-char hex-ish IRN with a distinctive prefix for readability."""
    return "IRN-" + "".join(rng.choices(string.hexdigits.upper()[:16], k=60))[:14]


def synth_ewb(rng: random.Random, seq: int) -> str:
    """12-digit EWB number, e.g. 'EWB-020000123456'."""
    return f"EWB-{seq:012d}"


def synth_challan(rng: random.Random, ts_yyyymm: str, seq: int) -> str:
    """CPIN-style challan number, e.g. 'CPIN-202411-000123'."""
    return f"CPIN-{ts_yyyymm}-{seq:06d}"


_VEHICLE_STATE_PREFIXES = [
    "MH", "KA", "DL", "TN", "UP", "GJ", "WB", "AP", "TS", "KL",
    "PB", "HR", "RJ", "MP", "OR", "BR",
]


def synth_vehicle(rng: random.Random) -> str:
    """e.g. 'KA01AB1234'."""
    state = rng.choice(_VEHICLE_STATE_PREFIXES)
    return f"{state}{rng.randint(1, 99):02d}{_rand_letters(rng, 2)}{rng.randint(0, 9999):04d}"


def synth_utr(rng: random.Random, bank_short: str = "HDFC") -> str:
    return f"{bank_short}{_rand_digits(rng, 12)}"


def synth_return_id(kind: str, gstin: str, period: str) -> str:
    """kind ∈ {'GSTR1','GSTR3B','GSTR2B'}; period 'YYYY-MM'."""
    return f"{kind}-{gstin[:7]}-{period.replace('-','')}"


def synth_director_id(rng: random.Random, seq: int) -> str:
    """Human-ish name + sequence; enough to be a stable key in the graph."""
    first = rng.choice(["Ravi", "Priya", "Anil", "Seema", "Vikram", "Neha",
                         "Rahul", "Kavya", "Ajay", "Meera", "Sanjay", "Divya"])
    last = rng.choice(["Kumar", "Sharma", "Verma", "Reddy", "Iyer", "Rao",
                        "Patel", "Nair", "Mehta", "Gupta", "Singh", "Khan"])
    return f"DIR-{seq:06d}-{first}-{last}"


def synth_pincode(rng: random.Random, state_code: str) -> str:
    """First digit of Indian PIN roughly maps to zone. Good enough for demo."""
    zone_map = {
        "07": 1, "06": 1, "09": 2, "10": 2, "24": 3, "27": 4,
        "29": 5, "32": 6, "33": 6, "36": 5, "37": 5, "19": 7,
    }
    zone = zone_map.get(state_code, rng.randint(1, 8))
    return f"{zone}{_rand_digits(rng, 5)}"
