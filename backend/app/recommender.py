"""Deterministic bundle engine.

The AI advisor only collects the business profile and explains the result in the owner's
language. Which products go in the bundle, their eligibility and their prices are decided
here, in plain code, so the advisor can never quote a product the business cannot buy.
"""
import math

from .catalogue import eligibility, products, unit_price

SEGMENT_NAMES = {
    "micro": "Micro retail & services",
    "prof": "Professional office",
    "multi": "Small multi-site business",
    "mfg": "Small manufacturer",
}

PROF_WORDS = ["clinic", "dental", "physio", "doctor", "hospital", "ca ", "chartered", "account", "law", "legal",
              "advocate", "coaching", "tuition", "consult", "insurance", "architect", "agency", "office", "diagnostic"]
MFG_WORDS = ["manufactur", "factory", "unit", "textile", "auto-parts", "auto parts", "fabrication", "plant",
             "workshop", "printing", "packaging", "garment", "woodcraft", "furniture"]

# What each segment usually needs, learnt from what activated customers bought (smb_leads.csv).
SEGMENT_DEFAULT_NEEDS = {
    "micro": ["internet", "mobile_lines", "whatsapp"],
    "prof": ["fast_internet", "email", "device_security", "cloud_backup", "mobile_lines"],
    "multi": ["fast_internet", "mobile_lines", "backup_internet", "central_management", "pos", "cctv"],
    "mfg": ["dedicated_internet", "mobile_lines", "email", "device_security", "firewall"],
}

# need -> (product, how many) ; connectivity needs are resolved separately.
NEED_TO_PRODUCT = {
    "mobile_lines": "P07", "premium_lines": "P08", "backup_internet": "P09", "central_management": "P10",
    "static_ip": "P11", "business_phone": "P12", "toll_free": "P13", "sms": "P14", "whatsapp": "P15",
    "email": "P16", "cloud_backup": "P17", "website": "P18", "pos": "P19", "device_security": "P20",
    "firewall": "P21", "guest_wifi": "P22", "cctv": "P23", "machine_iot": "P24", "fleet": "P25",
}

# If a product is not allowed, offer the closest thing that is.
ALTERNATIVES = {
    "P15": ["P18"], "P14": ["P18"], "P12": ["P08"], "P13": ["P08"], "P10": ["P09"],
    "P21": ["P20"], "P06": ["P05", "P03", "P02"], "P05": ["P03", "P02"], "P03": ["P02"],
}

WHY = {
    "P01": "Reliable fibre so UPI, card machine and billing never stop.",
    "P02": "300 Mbps fibre with room for video calls, cloud apps and several users at once.",
    "P03": "1 Gbps fibre with priority support for a busy office.",
    "P04": "Plug-and-play 5G broadband, installed in 2 days where fibre is not available.",
    "P05": "Dedicated 1:1 internet with a 99.5% uptime guarantee for machines and ERP.",
    "P06": "100 Mbps dedicated line with a 99.9% uptime guarantee.",
    "P07": "Business mobile line with 50 GB data and unlimited calls.",
    "P08": "Business mobile line with 150 GB, roaming and priority care for staff on the move.",
    "P09": "Backup router that switches to 4G/5G automatically if the main line goes down.",
    "P10": "Manage the internet at every branch from one screen.",
    "P11": "Fixed IP so you can view cameras or reach your server remotely.",
    "P12": "Business phone lines over the internet, with IVR and call recording.",
    "P13": "A 1800 number customers can call for free.",
    "P14": "10,000 SMS a month for reminders and offers.",
    "P15": "Verified WhatsApp Business channel with a product catalogue for customer chats and orders.",
    "P16": "Email on your own domain plus documents and video meetings, per user.",
    "P17": "Automatic 1 TB backup of your PCs and phones.",
    "P18": "Your own website and domain so customers can find you on Google.",
    "P19": "GST-ready billing and inventory on a tablet, with UPI and card acceptance.",
    "P20": "Antivirus and ransomware protection for every PC and phone.",
    "P21": "Managed next-generation firewall, monitored by our security team.",
    "P22": "Managed Wi-Fi with a separate network for customers.",
    "P23": "HD camera with 30 days of cloud recording, viewable on your phone.",
    "P24": "Sensors that track machine uptime and power use.",
    "P25": "Live GPS tracking for your vehicles.",
}

CONNECTIVITY = ["P01", "P02", "P03", "P04", "P05", "P06"]


def infer_segment(profile: dict) -> str:
    if profile.get("segment") in SEGMENT_NAMES:
        return profile["segment"]
    bt = (profile.get("business_type") or "").lower() + " "
    if profile["sites"] >= 3:
        return "multi"
    if any(w in bt for w in MFG_WORDS):
        return "mfg"
    if any(w in bt for w in PROF_WORDS):
        return "prof"
    return "micro" if profile["employees"] <= 10 else "prof"


def default_qty(need: str, seg: str, p: dict) -> int:
    e, s = p["employees"], p["sites"]
    counts = p.get("counts") or {}
    q = {
        "mobile_lines": {"micro": 1, "prof": min(e, 3), "multi": s, "mfg": 3}[seg],
        "premium_lines": 2,
        "email": min(e, 50) if seg != "mfg" else min(e, 15),
        "device_security": min(e, 50) if seg != "mfg" else min(e, 15),
        "cctv": {"micro": 2, "prof": 2, "multi": 2 * s, "mfg": 4}[seg],
        "pos": s, "guest_wifi": s, "backup_internet": s, "central_management": s, "firewall": 1,
        "machine_iot": 5, "fleet": 3, "business_phone": max(2, math.ceil(e / 10)),
    }.get(need, 1)
    return int(counts.get(need, q))


def normalise(profile: dict) -> dict:
    p = dict(profile)
    p["employees"] = max(1, int(p.get("employees") or 1))
    p["sites"] = max(1, int(p.get("sites") or 1))
    p["city_tier"] = 1 if int(p.get("city_tier") or 2) == 1 else 2
    p["gstin_active"] = bool(p.get("gstin_active"))
    p["fibre_available"] = p.get("fibre_available", True) is not False
    return p


def pick_connectivity(p: dict, needs: set[str], seg: str) -> tuple[str, list[dict]]:
    """Choose the main internet product per site, downgrading when not eligible."""
    notes = []
    per_site = p["employees"] / p["sites"]  # size each branch's line for its own staff
    if "dedicated_internet" in needs:
        wanted = "P06" if per_site >= 25 and "high_bandwidth" in needs else "P05"
    elif "fast_internet" in needs or per_site > 5:  # more than 5 people share the line
        wanted = "P03" if per_site >= 25 else "P02"
    else:
        wanted = "P01"
    if not p["fibre_available"] and wanted in {"P01", "P02", "P03"}:
        notes.append({"product_id": wanted, "reason": "Fibre is not available at this address, so we use 5G AirFiber instead."})
        wanted = "P04"
    chain = [wanted] + ALTERNATIVES.get(wanted, [])
    for pid in chain:
        ok, why = eligibility(pid, p)
        if ok:
            return pid, notes
        notes.append({"product_id": pid, "reason": why})
    return "P04", notes


def recommend(profile: dict, exclude: list[str] | None = None) -> dict:
    p = normalise(profile)
    seg = infer_segment(p)
    stated = set(p.get("needs") or [])
    needs = stated or set(SEGMENT_DEFAULT_NEEDS[seg])
    needs -= set(p.get("not_needed") or [])
    exclude = set(exclude or [])

    items: dict[str, dict] = {}
    excluded: list[dict] = []

    def add(pid: str, qty: int, reason: str, optional: bool = False):
        if pid in exclude:
            return
        if pid in items:
            items[pid]["qty"] = max(items[pid]["qty"], qty)
            return
        items[pid] = {"product_id": pid, "qty": qty, "reason": reason, "optional": optional}

    conn, notes = pick_connectivity(p, needs, seg)
    excluded += notes
    add(conn, p["sites"], WHY[conn])

    for need in sorted(needs):
        pid = NEED_TO_PRODUCT.get(need)
        if not pid:
            continue
        for cand in [pid] + ALTERNATIVES.get(pid, []):
            ok, why = eligibility(cand, p)
            if ok:
                reason = WHY[cand]
                if cand != pid:
                    reason += f" (Instead of {products()[pid]['product_name']}: {excluded[-1]['reason'].lower()}.)"
                add(cand, default_qty(need, seg, p), reason)
                break
            excluded.append({"product_id": cand, "reason": why})

    # Dependencies: e.g. CCTV and static IP need an internet line in the same bundle.
    for pid in list(items):
        req = products()[pid]["requires_one_of"]
        if req and not any(r in items for r in req):
            for r in req:
                if eligibility(r, p)[0]:
                    add(r, p["sites"], f"Needed for {products()[pid]['product_name']}. " + WHY[r])
                    break

    # Add-ons the owner can toggle on: eligible, relevant to the segment, not already in.
    add_ons = []
    for pid, prod in products().items():
        if pid in items or pid in CONNECTIVITY or seg not in prod["target_segments"].split(";"):
            continue
        if eligibility(pid, p)[0] and (not prod["requires_one_of"] or any(r in items for r in prod["requires_one_of"])):
            need = next((n for n, x in NEED_TO_PRODUCT.items() if x == pid), None)
            add_ons.append({"product_id": pid, "qty": default_qty(need, seg, p) if need else 1, "reason": WHY[pid]})

    quote = price(list(items.values()), p)
    budget = p.get("budget_per_month")
    if budget and quote["monthly_total"] > budget:
        quote["budget_note"] = (f"This is above your budget of ₹{budget:,}/month. "
                                "Switch off add-ons below to bring it down.")
    return {
        "segment": seg,
        "segment_name": SEGMENT_NAMES[seg],
        "profile": p,
        **quote,
        "add_ons": [price_line(a, p) for a in add_ons],
        "not_eligible": excluded,
    }


def price_line(item: dict, p: dict) -> dict:
    prod = products()[item["product_id"]]
    unit = unit_price(item["product_id"], p)
    return {
        **item,
        "name": prod["product_name"],
        "category": prod["category"],
        "unit": prod["unit"],
        "unit_price": unit,
        "monthly": unit * item["qty"],
        "setup": prod["setup"] * item["qty"],
        "min_contract": prod["min_contract"],
        "install_days": prod["install_days"],
    }


def price(items: list[dict], p: dict) -> dict:
    p = normalise(p)
    lines = [price_line(i, p) for i in items]
    monthly = sum(l["monthly"] for l in lines)
    return {
        "items": lines,
        "monthly_total": monthly,
        "monthly_total_with_gst": round(monthly * 1.18),
        "setup_total": sum(l["setup"] for l in lines),
        "contract_months": max([12] + [l["min_contract"] for l in lines]),
        "activation_days": max([0] + [l["install_days"] for l in lines]),
    }
