"""Accel Business OneSitting - API for the digital SMB onboarding journey.

Run from the backend folder:  uvicorn app.main:app --reload --port 8000
"""
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

from . import advisor, orders, propensity  # noqa: E402  (after .env is loaded)
from .catalogue import eligibility, products  # noqa: E402
from .kyc import verify_applicant  # noqa: E402
from .recommender import normalise, price, recommend  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
app = FastAPI(title="Accel Business OneSitting")


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = ""


class Selected(BaseModel):
    product_id: str
    qty: int


class QuoteIn(BaseModel):
    session_id: str
    selected: list[Selected]


class ConsentIn(BaseModel):
    session_id: str
    accepted: bool


class OrderIn(BaseModel):
    session_id: str
    selected: list[Selected]
    kyc_decision: str


def session(sid: str) -> dict:
    s = advisor.SESSIONS.get(sid)
    if not s or "recommendation" not in s:
        raise HTTPException(404, "Start with the advisor first.")
    return s


def priced_selection(s: dict, selected: list[Selected]) -> dict:
    """Re-price the owner's selection, re-checking every rule on the server."""
    p = normalise(s["recommendation"]["profile"])
    chosen = [x for x in selected if x.qty > 0]
    ids = {x.product_id for x in chosen}
    for x in chosen:
        if x.product_id not in products():
            raise HTTPException(400, f"Unknown product {x.product_id}")
        ok, why = eligibility(x.product_id, p)
        if not ok:
            raise HTTPException(400, why)
        req = products()[x.product_id]["requires_one_of"]
        if req and not ids.intersection(req):
            raise HTTPException(400, f"{products()[x.product_id]['product_name']} needs an internet line in the bundle")
    return price([{"product_id": x.product_id, "qty": x.qty, "reason": ""} for x in chosen], p)


@app.get("/api/health")
def health():
    return {"ok": True, "gemini": bool(advisor.gemini_key()), "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash")}


@app.post("/api/advisor/chat")
def chat(body: ChatIn):
    return advisor.chat(body.session_id, body.message)


@app.post("/api/quote")
def quote(body: QuoteIn):
    return priced_selection(session(body.session_id), body.selected)


@app.get("/api/consent/notice")
def consent_notice():
    return orders.CONSENT_NOTICE


@app.post("/api/consent")
def consent(body: ConsentIn):
    return orders.record_consent(body.session_id, body.accepted)


def kyc_response(sid: str, files: list[Path]) -> dict:
    result = verify_applicant(files)
    s = advisor.SESSIONS.get(sid)
    # If the GSTIN turns out cancelled, re-quote without GST-only products instead of failing the sale.
    if s and "recommendation" in s and result["decision"] == "REJECTED":
        prof = dict(s["recommendation"]["profile"], gstin_active=False)
        s["recommendation"] = recommend(prof) | {"explanation": "Your GSTIN is not active, so we removed products "
                                                 "that need GST and kept everything else."}
        result["revised_recommendation"] = s["recommendation"]
    return result


def require_consent(consent_id: str):
    c = orders.CONSENTS.get(consent_id)
    if not c or not c["accepted"]:
        raise HTTPException(403, "Please accept the consent notice before uploading documents.")


@app.post("/api/kyc/verify")
async def kyc_verify(session_id: str = Form(...), consent_id: str = Form(...), files: list[UploadFile] = File(...)):
    require_consent(consent_id)
    tmp = Path(tempfile.mkdtemp(prefix="kyc_"))
    try:
        paths = []
        for f in files:
            name = Path(f.filename or "doc.png").name
            dest = tmp / name
            dest.write_bytes(await f.read())
            paths.append(dest)
        return kyc_response(session_id, paths)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # data minimisation: images are never stored


@app.post("/api/kyc/sample")
def kyc_sample(session_id: str = Form(...), consent_id: str = Form(...), applicant: str = Form(...)):
    require_consent(consent_id)
    files = sorted((DATA / "kyc_documents").glob(f"{applicant}_*.png"))
    if not files:
        raise HTTPException(404, "Unknown sample applicant")
    return kyc_response(session_id, files)


@app.post("/api/orders")
def create_order(body: OrderIn):
    s = session(body.session_id)
    q = priced_selection(s, body.selected)
    s["status"] = "ordered"
    return orders.create_order(body.session_id, s["recommendation"], q["items"], body.kyc_decision)


@app.get("/api/orders/{oid}")
def get_order(oid: str):
    o = orders.get_order(oid)
    if not o:
        raise HTTPException(404, "Order not found")
    return o


@app.post("/api/orders/{oid}/advance")
def advance(oid: str, days: int = 1):
    return orders.advance(oid, days)


@app.get("/api/backoffice")
def backoffice():
    t = propensity.trained()
    stuck = [{"session_id": sid, "status": s["status"], "business_type": s["profile"].get("business_type"),
              "city": s["profile"].get("city"), "language": s.get("language")}
             for sid, s in advisor.SESSIONS.items() if s["status"] != "ordered"]
    return {"model": {k: t[k] for k in ("auc", "top20_capture", "top20_rate", "base_rate")},
            "drivers": propensity.top_drivers(8), "call_list": propensity.call_list(20), "advisor_unclosed": stuck}


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
