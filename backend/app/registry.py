"""Mock GSTIN / Udyam lookup APIs backed by the case CSVs, plus format validators."""
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")

STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "32": "Kerala", "33": "Tamil Nadu", "36": "Telangana",
    "37": "Andhra Pradesh",
}


def gstin_check_char(first14: str) -> str:
    """Official GSTIN checksum: base-36, alternating weights 1 and 2."""
    total = 0
    for i, ch in enumerate(first14):
        product = B36.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return B36[(36 - total % 36) % 36]


def validate_gstin_format(g: str) -> dict:
    g = (g or "").strip().upper()
    if not GSTIN_RE.match(g):
        return {"valid": False, "reason": "Not a 15-character GSTIN pattern"}
    if g[:2] not in STATE_CODES:
        return {"valid": False, "reason": f"Unknown state code {g[:2]}"}
    if gstin_check_char(g[:14]) != g[14]:
        return {"valid": False, "reason": "Checksum digit does not match"}
    return {"valid": True, "state": STATE_CODES[g[:2]], "pan": g[2:12]}


# Groups of characters OCR commonly confuses; tried when the checksum fails.
CONFUSION_GROUPS = ["IJTL1", "O0QD", "S5", "B8", "Z2", "G6"]


def repair_gstin(g: str) -> str | None:
    """Return the GSTIN one OCR-confusion away from `g` that passes the checksum.

    If several candidates pass, prefer the one that exists in the registry; if that is
    still ambiguous, give up and ask the customer to type the GSTIN.
    """
    g = (g or "").upper()
    if len(g) != 15:
        return None
    candidates = set()
    for i, ch in enumerate(g):
        for group in CONFUSION_GROUPS:
            if ch in group:
                for alt in group.replace(ch, ""):
                    cand = g[:i] + alt + g[i + 1:]
                    if validate_gstin_format(cand)["valid"]:
                        candidates.add(cand)
    # Only accept a repair that the registry confirms; otherwise ask the customer.
    candidates = {c for c in candidates if c in _gst().index}
    return candidates.pop() if len(candidates) == 1 else None


def validate_udyam_format(u: str) -> dict:
    u = (u or "").strip().upper()
    if not UDYAM_RE.match(u):
        return {"valid": False, "reason": "Expected format UDYAM-XX-00-0000000"}
    return {"valid": True}


@lru_cache
def _gst() -> pd.DataFrame:
    return pd.read_csv(DATA / "mock_gstin_registry.csv", dtype=str).set_index("gstin")


@lru_cache
def _udyam() -> pd.DataFrame:
    return pd.read_csv(DATA / "mock_udyam_registry.csv", dtype=str).set_index("udyam_number")


def lookup_gstin(g: str) -> dict | None:
    g = (g or "").upper()
    if g in _gst().index:
        return {"gstin": g, **_gst().loc[g].to_dict()}
    return None


def lookup_udyam(u: str) -> dict | None:
    u = (u or "").upper()
    if u in _udyam().index:
        return {"udyam_number": u, **_udyam().loc[u].to_dict()}
    return None


def find_udyam_by_name(name: str) -> dict | None:
    df = _udyam()
    hit = df[df.enterprise_name.str.lower() == (name or "").lower()]
    return {"udyam_number": hit.index[0], **hit.iloc[0].to_dict()} if len(hit) else None


def mask(identifier: str, keep: int = 4) -> str:
    """Show only the last few characters in UI and logs (DPDP data minimisation)."""
    s = identifier or ""
    return "•" * max(0, len(s) - keep) + s[-keep:]
