"""Consent records, orders and the self-service order tracker (in memory for the prototype)."""
import uuid
from datetime import datetime, timedelta

CONSENTS: dict[str, dict] = {}
ORDERS: dict[str, dict] = {}

CONSENT_NOTICE = {
    "purpose": "Verify your business identity (KYC) to activate Accel Business services, as required by telecom rules.",
    "data_collected": ["GST certificate", "Udyam certificate", "Address proof", "Authorised signatory ID"],
    "how_used": "Read automatically, checked against government registries (GSTIN, Udyam). Not used for marketing.",
    "retention": "Document images are deleted as soon as the fields are read. Verified details are kept for the "
                 "duration of your contract plus the period telecom regulations require.",
    "your_rights": "You can withdraw consent, see what we hold, or ask for correction from the app at any time.",
    "law": "Digital Personal Data Protection Act, 2023",
}


def record_consent(session_id: str, accepted: bool) -> dict:
    cid = "C-" + uuid.uuid4().hex[:8].upper()
    CONSENTS[cid] = {"consent_id": cid, "session_id": session_id, "accepted": accepted,
                     "purpose": "kyc_verification", "at": datetime.now().isoformat(timespec="seconds")}
    return CONSENTS[cid]


def stages(order: dict) -> list[dict]:
    t0 = datetime.fromisoformat(order["created_at"])
    install = order["activation_days"]
    kyc_ok = order["kyc_decision"] == "APPROVED"
    plan = [
        ("Order placed", 0, "We have your order and first payment."),
        ("KYC verified", 0 if kyc_ok else 1, "Documents checked against GST and Udyam registries."),
        ("Installation scheduled", 1, "Engineer slot booked. You will get a WhatsApp message the day before."),
        ("Engineer visit", max(2, install - 1), "Fibre/router installation at your site."),
        ("Services live", install, "Everything active. One bill, one support number."),
    ]
    elapsed = order["simulated_days"]
    out = []
    for name, day, desc in plan:
        when = t0 + timedelta(days=day)
        out.append({"stage": name, "description": desc, "expected": when.strftime("%d %b"),
                    "done": elapsed >= day, "day": day})
    current = next((s for s in out if not s["done"]), None)
    for s in out:
        s["current"] = s is current
    return out


def create_order(session_id: str, recommendation: dict, items: list[dict], kyc_decision: str) -> dict:
    oid = "ACB-" + uuid.uuid4().hex[:6].upper()
    ORDERS[oid] = {
        "order_id": oid, "session_id": session_id, "created_at": datetime.now().isoformat(timespec="seconds"),
        "items": items, "monthly_total": sum(i["monthly"] for i in items),
        "setup_total": sum(i["setup"] for i in items),
        "activation_days": max([1] + [i["install_days"] for i in items]),
        "kyc_decision": kyc_decision, "simulated_days": 0, "segment": recommendation.get("segment_name"),
    }
    return get_order(oid)


def get_order(oid: str) -> dict | None:
    o = ORDERS.get(oid)
    if not o:
        return None
    per_item = [{"name": i["name"], "qty": i["qty"],
                 "live_by": (datetime.fromisoformat(o["created_at"]) + timedelta(days=i["install_days"])).strftime("%d %b"),
                 "live": o["simulated_days"] >= i["install_days"]} for i in o["items"]]
    return {**o, "stages": stages(o), "products": per_item}


def advance(oid: str, days: int = 1) -> dict | None:
    """Demo helper: move the clock forward to show the tracker updating."""
    if oid in ORDERS:
        ORDERS[oid]["simulated_days"] += days
    return get_order(oid)
