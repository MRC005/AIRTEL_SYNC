"""Smart KYC: OCR every document, verify against the mock registries, cross-check documents.

Each check returns pass / warn / fail with a plain-language message the owner can act on.
The final decision is one of:
  APPROVED       - all hard checks pass, activation can start immediately
  ACTION_NEEDED  - the owner can fix it in the app (re-upload, missing document)
  MANUAL_REVIEW  - something looks inconsistent; a back-office agent checks it
  REJECTED       - GSTIN cancelled/suspended, so GST-only products cannot be sold
"""
import re
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from . import registry
from .ocr import extract

TODAY = date(2026, 7, 15)  # "today" fixed by the case README
ADDRESS_PROOF_MAX_AGE_DAYS = 90
REQUIRED_DOCS = ["gst_certificate", "udyam_certificate", "address_proof", "signatory_id"]
DOC_LABELS = {
    "gst_certificate": "GST certificate",
    "udyam_certificate": "Udyam certificate",
    "address_proof": "Address proof (utility bill)",
    "signatory_id": "Authorised signatory ID",
}


def similar(a: str, b: str) -> float:
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


NAME_MATCH = 0.93  # high enough to catch a changed word, low enough to absorb OCR noise


def names_match(a: str, b: str) -> bool:
    """Whole name must match, and so must the business inside '(Prop. ...)' if present."""
    if similar(a, b) < NAME_MATCH:
        return False
    biz = lambda s: (re.search(r"\(Prop\.?\s*([^)]*)\)", s or "") or [None, ""])[1]
    return similar(biz(a), biz(b)) >= NAME_MATCH if biz(a) or biz(b) else True


def pin_of(address: str) -> str | None:
    m = re.search(r"(\d{6})\s*$", (address or "").strip())
    return m.group(1) if m else None


def parse_date(s: str) -> date | None:
    m = re.search(r"(\d{4})\D?(\d{2})\D?(\d{2})", (s or "").replace(" ", ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def proprietor_name(legal_name: str) -> str | None:
    """'Neha Kaur (Prop. Vindhya Tours)' -> 'Neha Kaur'."""
    m = re.match(r"\s*([^()]+?)\s*\(Prop", legal_name or "")
    return m.group(1).strip() if m else None


def check(name: str, status: str, message: str, doc: str | None = None) -> dict:
    return {"check": name, "status": status, "message": message, "doc": doc}


def verify_applicant(files: list[Path]) -> dict:
    docs = {}
    for f in files:
        r = extract(f)
        docs[r["doc_type"]] = r
    checks: list[dict] = []

    # 1. Completeness and image quality
    for d in REQUIRED_DOCS:
        if d not in docs:
            checks.append(check("Document uploaded", "fail", f"{DOC_LABELS[d]} is missing. Please upload it.", d))
        elif docs[d]["quality"]["is_blurry"]:
            checks.append(check("Image quality", "fail",
                                f"{DOC_LABELS[d]} is too blurry to read. Please retake the photo in good light.", d))
        elif abs(docs[d]["quality"]["skew_deg"]) >= 1:
            checks.append(check("Image quality", "pass",
                                f"{DOC_LABELS[d]} was tilted {abs(docs[d]['quality']['skew_deg'])}°; straightened automatically.", d))

    readable = {k: v for k, v in docs.items() if not v["quality"]["is_blurry"]}
    gst = readable.get("gst_certificate", {}).get("fields", {})
    udy = readable.get("udyam_certificate", {}).get("fields", {})
    addr = readable.get("address_proof", {}).get("fields", {})
    sid = readable.get("signatory_id", {}).get("fields", {})
    reg_gst = None

    # 2. GSTIN: format, checksum, registry status, names, address
    if gst:
        g = gst.get("gstin", "")
        fmt = registry.validate_gstin_format(g)
        if not fmt["valid"]:
            repaired = registry.repair_gstin(g)
            if repaired:
                checks.append(check("GSTIN format", "pass",
                                    "GSTIN read with a small OCR error; corrected using the checksum and confirmed in the registry.",
                                    "gst_certificate"))
                g = repaired
            else:
                checks.append(check("GSTIN format", "fail",
                                    f"The GSTIN on the certificate fails the checksum ({fmt['reason'].lower()}). "
                                    "It may be mistyped or altered.", "gst_certificate"))
                g = None
        if g:
            reg_gst = registry.lookup_gstin(g)
            if not reg_gst:
                checks.append(check("GSTIN registry lookup", "fail", "GSTIN not found in the GST registry.", "gst_certificate"))
            else:
                st = reg_gst["status"]
                if st != "Active":
                    checks.append(check("GSTIN status", "fail",
                                        f"GSTIN is {st} in the registry. GST-only products (e.g. leased line, SIP, WhatsApp API) cannot be sold.",
                                        "gst_certificate"))
                else:
                    checks.append(check("GSTIN status", "pass", "GSTIN is Active in the registry.", "gst_certificate"))
                for field, reg_field, label in [("legal_name", "legal_name", "Legal name"), ("trade_name", "trade_name", "Trade name")]:
                    if not names_match(gst.get(field), reg_gst[reg_field]):
                        checks.append(check(f"{label} matches registry", "fail",
                                            f"{label} on the certificate ('{gst.get(field)}') does not match the registry "
                                            f"('{reg_gst[reg_field]}'). The document may have been edited.", "gst_certificate"))
                if pin_of(gst.get("address")) and pin_of(gst.get("address")) != pin_of(reg_gst["principal_place_of_business"]):
                    checks.append(check("Address matches registry", "warn",
                                        "PIN code on the certificate differs from the registry.", "gst_certificate"))

    # 3. Udyam
    if udy:
        u = udy.get("udyam_number", "")
        if not u:
            checks.append(check("Udyam number", "fail",
                                "Udyam registration number is missing on the certificate. Please upload the full certificate.",
                                "udyam_certificate"))
        elif not registry.validate_udyam_format(u)["valid"]:
            checks.append(check("Udyam number", "fail", "Udyam number is not in the UDYAM-XX-00-0000000 format.", "udyam_certificate"))
        else:
            reg_u = registry.lookup_udyam(u)
            if not reg_u:
                checks.append(check("Udyam registry lookup", "fail", "Udyam number not found in the registry.", "udyam_certificate"))
            else:
                ok = names_match(udy.get("enterprise_name"), reg_u["enterprise_name"])
                checks.append(check("Udyam registry lookup", "pass" if ok else "fail",
                                    "Udyam number verified in the registry." if ok else
                                    f"Udyam is registered to '{reg_u['enterprise_name']}', not this business.", "udyam_certificate"))

    # 4. Address proof: recent and for this business
    if addr:
        d = parse_date(addr.get("bill_date"))
        if d:
            age = (TODAY - d).days
            if age > ADDRESS_PROOF_MAX_AGE_DAYS:
                checks.append(check("Address proof is recent", "fail",
                                    f"Utility bill is dated {d.isoformat()} ({age} days old). It must be under {ADDRESS_PROOF_MAX_AGE_DAYS} days. Please upload a recent bill.",
                                    "address_proof"))
            else:
                checks.append(check("Address proof is recent", "pass", f"Bill dated {d.isoformat()} ({age} days old).", "address_proof"))
        business = (reg_gst or {}).get("trade_name") or gst.get("trade_name") or udy.get("enterprise_name")
        if business and not names_match(addr.get("billed_to"), business):
            checks.append(check("Address proof is for this business", "warn",
                                f"Bill is in the name of '{addr.get('billed_to')}', not '{business}'.", "address_proof"))
        ref_pin = pin_of((reg_gst or {}).get("principal_place_of_business") or gst.get("address"))
        if ref_pin and pin_of(addr.get("address")) and pin_of(addr.get("address")) != ref_pin:
            checks.append(check("Address proof matches GST address", "warn",
                                "PIN code on the bill differs from the GST principal place of business.", "address_proof"))

    # 5. Signatory: valid ID, and actually authorised to sign for this business
    if sid:
        v = parse_date(sid.get("valid_till"))
        if v and v < TODAY:
            checks.append(check("Signatory ID valid", "fail", f"Signatory ID expired on {v.isoformat()}.", "signatory_id"))
        constitution = (reg_gst or {}).get("constitution") or gst.get("constitution", "")
        legal = (reg_gst or {}).get("legal_name") or gst.get("legal_name", "")
        prop = proprietor_name(legal)
        if "Proprietor" in constitution and prop:
            ok = names_match(sid.get("name"), prop)
            checks.append(check("Signatory is the proprietor", "pass" if ok else "fail",
                                f"{sid.get('name')} is the registered proprietor." if ok else
                                f"Signatory {sid.get('name')} is not the proprietor ({prop}).", "signatory_id"))
        elif constitution:
            checks.append(check("Signatory authority", "warn",
                                f"For a {constitution}, {sid.get('name')} must be a designated partner or director. "
                                "Upload a board resolution or authorisation letter, or verify via DigiLocker / MCA.", "signatory_id"))

    decision = decide(checks)
    return {"decision": decision, "checks": checks, "extracted": mask_fields(docs)}


def decide(checks: list[dict]) -> str:
    fails = [c for c in checks if c["status"] == "fail"]
    if any(c["check"] == "GSTIN status" for c in fails):
        return "REJECTED"
    # Problems the owner can fix in the app themselves (re-upload, add a letter).
    customer_fixable = {"Document uploaded", "Image quality", "Address proof is recent", "Udyam number",
                        "Signatory authority"}
    warns = [c for c in checks if c["status"] == "warn"]
    if any(c["check"] not in customer_fixable for c in fails + warns):
        return "MANUAL_REVIEW"
    if fails or warns:
        return "ACTION_NEEDED"
    return "APPROVED"


def mask_fields(docs: dict) -> dict:
    """Return extracted fields with identifiers masked: the UI never shows full IDs."""
    out = {}
    for t, r in docs.items():
        f = dict(r.get("fields", {}))
        for key in ("gstin", "udyam_number", "consumer_no", "id_no"):
            if f.get(key):
                f[key] = registry.mask(f[key])
        out[t] = {"fields": f, "quality": r["quality"]}
    return out
