"""Product catalogue and the eligibility rules from product_catalogue.csv."""
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache
def products() -> dict[str, dict]:
    df = pd.read_csv(DATA / "product_catalogue.csv", dtype=str).fillna("")
    out = {}
    for r in df.to_dict("records"):
        out[r["product_id"]] = {
            **r,
            "price_min": int(r["price_min_inr_per_month"]),
            "price_max": int(r["price_max_inr_per_month"]),
            "setup": int(r["one_time_setup_inr"]),
            "min_contract": int(r["min_contract_months"]),
            "tiers": {int(t) for t in r["available_city_tiers"].split(";")},
            "min_employees": int(r["min_employees"]),
            "min_sites": int(r["min_sites"]),
            "requires_gstin": r["requires_gstin"] == "Y",
            "requires_one_of": [p for p in r["requires_one_of"].split("|") if p],
            "install_days": int(r["typical_install_days"]),
        }
    return out


def eligibility(pid: str, profile: dict) -> tuple[bool, str]:
    """Can this business buy this product? Returns (ok, reason if not)."""
    p = products()[pid]
    if profile["city_tier"] not in p["tiers"]:
        return False, f"{p['product_name']} is only sold in tier {', '.join(map(str, sorted(p['tiers'])))} cities"
    if profile["employees"] < p["min_employees"]:
        return False, f"{p['product_name']} needs at least {p['min_employees']} employees"
    if profile["sites"] < p["min_sites"]:
        return False, f"{p['product_name']} needs at least {p['min_sites']} sites"
    if p["requires_gstin"] and not profile.get("gstin_active"):
        return False, f"{p['product_name']} needs an active GSTIN"
    return True, ""


def unit_price(pid: str, profile: dict) -> int:
    """Transparent pricing: entry price in tier-2 cities, mid-range in tier-1."""
    p = products()[pid]
    if profile["city_tier"] == 2:
        return p["price_min"]
    return int(round((p["price_min"] + p["price_max"]) / 2, -1))
