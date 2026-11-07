"""Conversational advisor.

Gemini talks to the owner in their language and fills in a business profile. As soon as
the profile is complete, the deterministic engine (recommender.py) picks the bundle and
prices it. Gemini then explains that bundle in plain language. Gemini never chooses
products or prices, so it cannot recommend something the business is not eligible for.

Without a Gemini key the same flow runs on a scripted set of questions.
"""
import json
import os
import re
import time
import uuid

import httpx

from .recommender import NEED_TO_PRODUCT, recommend

TIER1 = {"ahmedabad", "pune", "mumbai", "hyderabad", "delhi", "new delhi", "kolkata", "chennai", "bengaluru",
         "bangalore", "gurugram", "gurgaon", "noida"}
# Owners often type the city in their own script.
CITY_ALIASES = {"पुणे": "pune", "मुंबई": "mumbai", "दिल्ली": "delhi", "बेंगलुरु": "bengaluru", "बैंगलोर": "bengaluru",
                "चेन्नई": "chennai", "कोलकाता": "kolkata", "हैदराबाद": "hyderabad", "अहमदाबाद": "ahmedabad",
                "சென்னை": "chennai", "ಬೆಂಗಳೂರು": "bengaluru", "মুম্বাই": "mumbai", "কলকাতা": "kolkata", "पुणे शहर": "pune"}
NEEDS = ["internet", "fast_internet", "dedicated_internet", "backup_internet"] + list(NEED_TO_PRODUCT)
SESSIONS: dict[str, dict] = {}

SYSTEM = f"""You are the Accel Business advisor. You help small business owners in India (kirana stores,
clinics, CA firms, coaching centres, restaurants, small factories) choose business connectivity and
digital tools on their phone, without a salesperson.

Rules:
- Reply in the language AND script the owner writes in (Hindi, Hinglish, English, Tamil, Telugu, Kannada, Marathi,
  Bengali, Gujarati, Malayalam or Punjabi). If they write Hindi in Devanagari, reply in Devanagari, not Roman letters.
  Keep replies to 1-2 short sentences. Use simple words, no jargon.
- Ask ONE question at a time. You need: type of business, number of staff, number of branches/sites,
  city, whether they have GST registration (GSTIN), and what they need help with (internet, staff phones,
  WhatsApp for customers, billing machine, CCTV, email, website, backup if internet fails, etc.).
  Infer what you can from earlier answers instead of asking again. Ask at most 6 questions in total.
- NEVER mention product names, prices or plans yourself. The system will calculate the bundle.
- Map what they need to these tags in profile.needs: {", ".join(NEEDS)}.
  internet = basic broadband; fast_internet = several users/video calls; dedicated_internet = factory/ERP/guaranteed uptime;
  mobile_lines = business SIMs; whatsapp = WhatsApp Business channel; pos = billing/UPI machine;
  email = business email/documents; device_security = antivirus; cloud_backup = data backup;
  backup_internet = keeps working if main internet fails; central_management = manage many branches;
  guest_wifi = Wi-Fi for customers; business_phone = office phone lines/IVR; static_ip = remote CCTV/server access.
  Put anything they say they do NOT want in profile.not_needed.
- Set ready=true only when business_type, employees, sites, city and gstin are known and at least one need.
"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "reply": {"type": "STRING"},
        "language": {"type": "STRING"},
        "ready": {"type": "BOOLEAN"},
        "profile": {
            "type": "OBJECT",
            "properties": {
                "business_type": {"type": "STRING"},
                "employees": {"type": "INTEGER", "description": "number of staff including owner, e.g. 12"},
                "sites": {"type": "INTEGER", "description": "number of shops/branches/sites, e.g. 1"},
                "city": {"type": "STRING", "description": "city name in English letters, e.g. Pune"},
                "has_gstin": {"type": "STRING", "enum": ["yes", "no", "unknown"]},
                "fibre_available": {"type": "BOOLEAN"},
                "needs": {"type": "ARRAY", "items": {"type": "STRING", "enum": NEEDS}},
                "not_needed": {"type": "ARRAY", "items": {"type": "STRING", "enum": NEEDS}},
            },
        },
    },
    "required": ["reply", "language", "ready", "profile"],
}


def gemini_key() -> str | None:
    return (os.getenv("GEMINI_API_KEY") or "").strip() or None


# Lite models have the largest free-tier daily quota; the full model is a last resort.
FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash"]


def call_gemini(system: str, contents: list[dict], schema: dict | None = None, parse=None):
    """Call Gemini; on a free-tier rate limit (429) or server error, wait briefly and try a
    lighter model with its own quota before giving up."""
    body = {"system_instruction": {"parts": [{"text": system}]}, "contents": contents,
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048}}
    if schema:
        body["generationConfig"].update({"responseMimeType": "application/json", "responseSchema": schema})
    models = [os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")] + FALLBACK_MODELS
    last_error = None
    plan = [models[0], models[0]] + models[1:]  # the primary model gets one retry
    for attempt, model in enumerate(plan):
        try:
            r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                           headers={"x-goog-api-key": gemini_key()}, json=body, timeout=25)
        except httpx.HTTPError as e:  # slow or dropped connection: try the next model
            last_error = f"{model}: {type(e).__name__}"
            continue
        if r.status_code == 200:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            if parse is None:
                return text
            try:
                return parse(text)
            except ValueError as e:  # malformed JSON from a small model: ask the next one
                last_error = f"{model}: bad JSON ({str(e)[:60]})"
                continue
        last_error = f"{model}: HTTP {r.status_code}"
        if r.status_code in (429, 500, 503):
            m = re.search(r'"retryDelay":\s*"(\d+)', r.text)
            time.sleep(min(int(m.group(1)) if m else 2, 8) if attempt == 0 else 1)
            continue
        break
    raise RuntimeError(last_error)


DONE = {
    "Hindi": "धन्यवाद! आपके लिए सबसे सही बंडल यह रहा।",
    "Tamil": "நன்றி! உங்களுக்கு ஏற்ற திட்டம் இதோ.",
    "English": "Thanks! Here is the bundle I recommend.",
}


def lang_key(language: str) -> str:
    l = (language or "").lower()
    return "Hindi" if "hin" in l else "Tamil" if "tamil" in l else "English"


BUSY = {
    "Hindi": "माफ़ कीजिए, अभी थोड़ी भीड़ है। कृपया अपना जवाब एक बार फिर भेजें।",
    "Tamil": "மன்னிக்கவும், இப்போது சற்று நெரிசல். உங்கள் பதிலை மீண்டும் அனுப்புங்கள்.",
    "English": "Sorry, we're a little busy right now. Please send that once more.",
}


def parse_reply(text: str) -> dict:
    """Parse Gemini's JSON safely: small models occasionally emit absurdly long numbers."""
    out = json.loads(text, parse_int=lambda d: int(d) if len(d) <= 7 else 0)
    p = out.get("profile") or {}
    for key, hi in (("employees", 5000), ("sites", 500)):
        if not isinstance(p.get(key), int) or not 0 < p[key] <= hi:
            p.pop(key, None)
    out["profile"] = p
    return out


KNOWN_CITIES = sorted(TIER1 | {"indore", "jaipur", "kochi", "vadodara", "lucknow", "ludhiana", "bhopal", "mysuru",
                               "nagpur", "nashik", "patna", "surat", "coimbatore", "visakhapatnam", "guwahati",
                               "chandigarh", "kanpur", "madurai", "thiruvananthapuram", "bhubaneswar"}, key=len, reverse=True)


def city_in(message: str) -> str | None:
    """Backup for the model: pick up a city name the owner typed."""
    m = message.lower()
    return next((c.title() for c in KNOWN_CITIES if re.search(rf"\b{re.escape(c)}\b", m)), None)


NEED_KEYWORDS = {
    "internet": ["internet", "इंटरनेट", "broadband", "wifi", "इन्टरनेट"], "email": ["email", "ईमेल", "मेल"],
    "backup_internet": ["backup", "बैकअप", "बंद हो"], "whatsapp": ["whatsapp", "व्हाट्सएप", "वॉट्सऐप"],
    "cctv": ["cctv", "camera", "कैमरा", "सीसीटीवी"], "pos": ["billing", "pos", "upi", "बिलिंग"],
    "mobile_lines": ["sim", "phone", "फोन", "सिम", "मोबाइल"], "website": ["website", "वेबसाइट"],
}


def needs_in(message: str) -> list[str]:
    """Backup for the model: recognise needs typed in English or Hindi."""
    m = message.lower()
    return sorted(n for n, words in NEED_KEYWORDS.items() if any(w in m for w in words))


def profile_complete(p: dict) -> bool:
    """Only recommend once the facts the rules engine depends on are actually known.
    Needs are optional: if the owner names none, the engine uses its segment defaults."""
    return bool(p.get("business_type") and p.get("employees") and p.get("city")
                and p.get("has_gstin") in ("yes", "no"))


def to_engine_profile(p: dict) -> dict:
    city = (p.get("city") or "").strip()
    city = CITY_ALIASES.get(city, city)
    return {
        "business_type": p.get("business_type"),
        "employees": p.get("employees") or 1,
        "sites": p.get("sites") or 1,
        "city": city,
        "city_tier": 1 if city.lower() in TIER1 else 2,
        # Assumed active until Smart KYC verifies it; the quote is re-run if KYC finds otherwise.
        "gstin_active": p.get("has_gstin") == "yes",
        "fibre_available": p.get("fibre_available", True),
        "budget_per_month": p.get("budget_per_month") or None,
        "needs": [n for n in p.get("needs") or [] if n in NEEDS],
        "not_needed": p.get("not_needed") or [],
    }


def explain(rec: dict, language: str) -> str:
    """Plain-language summary of the engine's bundle, in the owner's language."""
    items = ", ".join(f"{i['name']} x{i['qty']}" for i in rec["items"])
    fallback = (f"For your {rec['segment_name'].lower()}, I recommend: {items}. "
                f"One monthly bill of ₹{rec['monthly_total']:,} (+GST), live in about {rec['activation_days']} days.")
    if not gemini_key():
        return fallback
    prompt = (f"Write 2-3 short sentences in {language} for a small business owner explaining why this bundle fits "
              f"them. Mention the monthly price exactly as given. Do not add products or change prices.\n"
              f"{json.dumps({k: rec[k] for k in ['segment_name', 'monthly_total', 'activation_days']} | {'items': [{'name': i['name'], 'qty': i['qty'], 'why': i['reason']} for i in rec['items']]}, ensure_ascii=False)}")
    try:
        return call_gemini("You explain telecom bundles simply and honestly.",
                           [{"role": "user", "parts": [{"text": prompt}]}]).strip()
    except Exception:
        return fallback


# ---------- scripted fallback (no API key) ----------
SCRIPT = [
    ("business_type", "What kind of business do you run? (e.g. kirana, clinic, CA firm, restaurant, factory)", []),
    ("employees", "How many people work there, including you?", ["1-3", "4-10", "11-25", "26-100"]),
    ("sites", "How many shops, branches or sites do you have?", ["1", "2", "3-5", "6+"]),
    ("city", "Which city are you in?", ["Delhi", "Mumbai", "Pune", "Jaipur", "Lucknow"]),
    ("has_gstin", "Do you have GST registration (a GSTIN)?", ["Yes", "No"]),
    ("needs", "What do you need help with? Pick all that apply.",
     ["Internet", "Staff phone lines", "WhatsApp for customers", "Billing/UPI machine", "CCTV", "Business email",
      "Backup if internet fails", "Website"]),
]
NEED_WORDS = {"internet": "internet", "phone": "mobile_lines", "whatsapp": "whatsapp", "billing": "pos", "upi": "pos",
              "cctv": "cctv", "camera": "cctv", "email": "email", "backup": "backup_internet", "website": "website",
              "wifi": "guest_wifi", "antivirus": "device_security"}


def first_int(text: str) -> int | None:
    """'4-10' -> 7 (middle of a range), '12' -> 12."""
    nums = [int(n) for n in re.findall(r"\d+", text)]
    return round(sum(nums) / len(nums)) if nums else None


def scripted_turn(s: dict, message: str) -> dict:
    p = s["profile"]
    if s["step"] > 0 and message:
        key = SCRIPT[s["step"] - 1][0]
        m = message.lower()
        if key in ("employees", "sites"):
            p[key] = 6 if "6+" in m else (first_int(m) or 1)
        elif key == "has_gstin":
            p[key] = "yes" if m.startswith(("y", "haan", "ha")) else "no"
        elif key == "needs":
            p["needs"] = sorted({v for w, v in NEED_WORDS.items() if w in m}) or ["internet"]
        else:
            p[key] = message.strip()
    if s["step"] < len(SCRIPT):
        _, q, chips = SCRIPT[s["step"]]
        s["step"] += 1
        return {"reply": q, "quick_replies": chips, "ready": False, "multi": SCRIPT[s["step"] - 1][0] == "needs"}
    return {"reply": "Thanks! Here is the bundle I recommend.", "quick_replies": [], "ready": True}


def chat(session_id: str | None, message: str) -> dict:
    if not session_id or session_id not in SESSIONS:
        session_id = session_id or uuid.uuid4().hex[:12]
        SESSIONS[session_id] = {"history": [], "profile": {}, "step": 0, "language": "English", "status": "chatting"}
    s = SESSIONS[session_id]
    mode = "gemini" if gemini_key() else "scripted"

    if mode == "gemini":
        if message:
            s["history"].append({"role": "user", "parts": [{"text": message}]})
        contents = s["history"] or [{"role": "user", "parts": [{"text": "Hi"}]}]
        try:
            out = call_gemini(SYSTEM + f"\nProfile so far: {json.dumps(s['profile'])}", contents, SCHEMA, parse_reply)
        except Exception as e:
            s["error"] = str(e)[:200]
            if message:
                s["history"].pop()  # let the owner simply send the same answer again
            started = any(h["role"] == "model" for h in s["history"])
            if started:
                # Never switch language or flow mid-conversation; ask them to resend instead.
                result = {"reply": BUSY[lang_key(s["language"])], "quick_replies": [], "ready": False}
            else:
                mode = "scripted"  # Gemini unreachable from the start: run the guided flow
        else:
            # Treat 0 / "unknown" as "not answered yet" so a guess never overwrites a real answer.
            s["profile"].update({k: v for k, v in (out.get("profile") or {}).items()
                                 if v not in (None, "", [], 0, "unknown")})
            if not s["profile"].get("city") and message and city_in(message):
                s["profile"]["city"] = city_in(message)
            if not s["profile"].get("needs") and message:
                found = needs_in(message)
                if found:
                    s["profile"]["needs"] = found
            s["language"] = out.get("language") or s["language"]
            s["history"].append({"role": "model", "parts": [{"text": out["reply"]}]})
            ready = profile_complete(s["profile"]) and (bool(out.get("ready")) or bool(s["profile"].get("needs")))
            reply = out["reply"]
            if ready:  # the rules engine, not the AI, says what is in the bundle
                reply = DONE[lang_key(s["language"])]
            result = {"reply": reply, "quick_replies": [], "ready": ready}
    if mode == "scripted":
        result = scripted_turn(s, message)

    result.update({"session_id": session_id, "mode": mode, "profile": s["profile"]})
    if result["ready"]:
        engine_profile = to_engine_profile(s["profile"])
        rec = recommend(engine_profile)
        rec["explanation"] = explain(rec, s["language"])
        s["recommendation"] = rec
        s["status"] = "recommended"
        result["recommendation"] = rec
    return result
