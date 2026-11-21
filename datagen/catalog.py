"""Reference tables — states, HSN codes, GST rates, sectors.

These are hand-curated for realism, not scraped from a live source. They
are sufficient to drive statistically plausible distributions without
implying any legal tax opinion (see README disclaimer). The rate values
reflect common textbook GST slabs; do not treat this file as a tax code.
"""
from __future__ import annotations

# ── Indian GST state codes (first two digits of a GSTIN) ─────────────────
# Weight = rough share of GST-registered businesses. Not census-accurate;
# tuned to produce visually diverse demo networks.
STATES: dict[str, dict] = {
    "01": {"name": "Jammu & Kashmir", "weight": 0.5},
    "02": {"name": "Himachal Pradesh", "weight": 0.6},
    "03": {"name": "Punjab", "weight": 1.5},
    "04": {"name": "Chandigarh", "weight": 0.3},
    "05": {"name": "Uttarakhand", "weight": 0.6},
    "06": {"name": "Haryana", "weight": 2.0},
    "07": {"name": "Delhi", "weight": 3.0},
    "08": {"name": "Rajasthan", "weight": 2.5},
    "09": {"name": "Uttar Pradesh", "weight": 5.0},
    "10": {"name": "Bihar", "weight": 1.8},
    "19": {"name": "West Bengal", "weight": 3.0},
    "20": {"name": "Jharkhand", "weight": 1.0},
    "21": {"name": "Odisha", "weight": 1.2},
    "22": {"name": "Chhattisgarh", "weight": 0.9},
    "23": {"name": "Madhya Pradesh", "weight": 2.2},
    "24": {"name": "Gujarat", "weight": 4.0},
    "27": {"name": "Maharashtra", "weight": 6.5},
    "29": {"name": "Karnataka", "weight": 4.5},
    "32": {"name": "Kerala", "weight": 2.0},
    "33": {"name": "Tamil Nadu", "weight": 4.0},
    "36": {"name": "Telangana", "weight": 2.5},
    "37": {"name": "Andhra Pradesh", "weight": 2.5},
}

# ── HSN → GST rate slab (compact selection covering all four slabs) ─────
# rate is expressed as a fraction (0.05, 0.12, 0.18, 0.28). Only rate is
# used for tax math. `label` and `sector` drive plausible descriptions.
HSN_CATALOG: dict[str, dict] = {
    # 5 % — essentials
    "0910": {"rate": 0.05, "label": "Spices",              "sector": "Food"},
    "1006": {"rate": 0.05, "label": "Rice",                "sector": "Food"},
    "5208": {"rate": 0.05, "label": "Cotton fabrics",      "sector": "Textiles"},
    # 12 %
    "2901": {"rate": 0.12, "label": "Industrial chemicals","sector": "Chemicals"},
    "3401": {"rate": 0.18, "label": "Soaps",               "sector": "Personal care"},
    "4820": {"rate": 0.12, "label": "Notebooks & registers","sector": "Stationery"},
    # 18 %
    "8471": {"rate": 0.18, "label": "Computers & laptops", "sector": "Electronics"},
    "8517": {"rate": 0.18, "label": "Mobile phones",       "sector": "Electronics"},
    "7208": {"rate": 0.18, "label": "Hot-rolled steel",    "sector": "Metals"},
    "7213": {"rate": 0.18, "label": "Steel bars",          "sector": "Metals"},
    "8426": {"rate": 0.18, "label": "Industrial machinery","sector": "Machinery"},
    "9401": {"rate": 0.18, "label": "Office furniture",    "sector": "Furniture"},
    # 28 %
    "8703": {"rate": 0.28, "label": "Passenger vehicles",  "sector": "Automotive"},
    "2202": {"rate": 0.28, "label": "Aerated drinks",      "sector": "Beverages"},
    "2402": {"rate": 0.28, "label": "Cigars & cigarettes", "sector": "Tobacco"},
}

# ── Sector -> HSN whitelist. Used to pick coherent invoices for a given
#    GSTIN. A steel supplier issues steel invoices, not soap invoices.
SECTOR_TO_HSN: dict[str, list[str]] = {}
for _hsn, _info in HSN_CATALOG.items():
    SECTOR_TO_HSN.setdefault(_info["sector"], []).append(_hsn)


SECTOR_WEIGHTS: dict[str, float] = {
    "Metals": 1.0,
    "Electronics": 1.2,
    "Chemicals": 0.8,
    "Textiles": 1.0,
    "Food": 1.3,
    "Machinery": 0.7,
    "Automotive": 0.5,
    "Furniture": 0.6,
    "Personal care": 0.6,
    "Stationery": 0.5,
    "Beverages": 0.4,
    "Tobacco": 0.2,
}


# ── PAN entity-type letter — 4th char in a PAN ───────────────────────────
# P = Person, F = Firm, C = Company, H = HUF, A = Association, T = Trust,
# G = Government, L = Local Authority, J = Artificial Juridical Person.
PAN_ENTITY_TYPES = ["P", "F", "C", "H", "A", "T"]
PAN_ENTITY_WEIGHTS = [0.35, 0.25, 0.20, 0.05, 0.10, 0.05]


# ── Bank list (for TaxPayment.bank) ──────────────────────────────────────
BANKS = [
    "HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank",
    "Kotak Mahindra Bank", "Punjab National Bank", "Bank of Baroda",
    "IndusInd Bank", "Yes Bank", "Canara Bank",
]


# ── Transporter list (for EWayBill.transporter) ─────────────────────────
TRANSPORTERS = [
    "FastCargo Ltd", "SpeedEx Logistics", "BharatShip", "QuickMove",
    "LocalHaul", "GreenLine Freight", "NorthStar Movers", "Delta Express",
]
