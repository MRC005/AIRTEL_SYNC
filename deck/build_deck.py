"""Build the 7-slide submission deck on Airtel's SYNC template.

python3 deck/build_deck.py
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).parent
ROOT = HERE.parent
SHOTS = HERE / "shots"
TEAM, CAMPUS = "FullBars", "VIT"
MEMBERS = "Machum Roy Choudhury  ·  Cheralathan M"
OUT = HERE / f"{TEAM}_{CAMPUS}.pptx"

RED = RGBColor(0xE4, 0x00, 0x00)
DARK = RGBColor(0x1D, 0x1B, 0x22)
GREY = RGBColor(0x5F, 0x5B, 0x66)
LIGHT = RGBColor(0xFD, 0xEC, 0xEC)
LINE = RGBColor(0xE6, 0xE1, 0xE8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x17, 0x82, 0x4A)
AMBER = RGBColor(0xA8, 0x5D, 0x00)
FONT = "Arial"

prs = Presentation(ROOT / "docs" / "Submission Template_Sync.pptx")
title_slide, content_tpl = prs.slides[0], prs.slides[1]
content_layout = content_tpl.slide_layout
bg_content = HERE / "_bg_content.jpg"
# The template's content background image, reused on every new slide.
for shape in content_tpl.shapes:
    if shape.shape_type == 13:
        bg_content.write_bytes(shape.image.blob)


def new_slide():
    s = prs.slides.add_slide(content_layout)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    s.shapes.add_picture(str(bg_content), 0, 0, prs.slide_width, prs.slide_height)
    return s


def text(slide, x, y, w, h, runs, size=11, color=DARK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         spacing=None):
    """runs: str, or list of paragraphs; each paragraph a str or list of (text, {style}) tuples."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        parts = para if isinstance(para, list) else [(para, {})]
        for t, st in parts:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = FONT
            f.size = Pt(st.get("size", size))
            f.bold = st.get("bold", bold)
            f.color.rgb = st.get("color", color)
    return tb


def box(slide, x, y, w, h, fill=WHITE, line=LINE, radius=True):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                 Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        shp.adjustments[0] = 0.08
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.75)
    shp.shadow.inherit = False
    return shp


def header(slide, title, message):
    text(slide, 0.45, 0.66, 9.1, 0.42, title, size=20, bold=True)
    text(slide, 0.45, 1.06, 9.1, 0.3, message, size=11, color=GREY)


def table(slide, x, y, col_w, rows, row_h=0.3, header_fill=DARK, size=9, first_bold=True, fills=None):
    """Simple table built from boxes so it renders identically everywhere."""
    for r, row in enumerate(rows):
        cx = x
        for c, (val, w) in enumerate(zip(row, col_w)):
            is_head = r == 0
            fill = header_fill if is_head else (fills[r] if fills and fills.get(r) else (WHITE if r % 2 else RGBColor(0xF8, 0xF6, 0xF9)))
            b = box(slide, cx, y + r * row_h, w, row_h, fill=fill, line=LINE, radius=False)
            tf = b.text_frame
            tf.margin_left = tf.margin_right = Inches(0.05)
            tf.margin_top = tf.margin_bottom = Inches(0.01)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            parts = val if isinstance(val, list) else [(str(val), {})]
            for t, st in parts:
                run = p.add_run()
                run.text = t
                run.font.name = FONT
                run.font.size = Pt(st.get("size", size))
                run.font.bold = st.get("bold", is_head or (first_bold and c == 0))
                run.font.color.rgb = st.get("color", WHITE if is_head else DARK)
            cx += w


def phone(slide, img, x, y, h, caption=None):
    pic = slide.shapes.add_picture(str(img), Inches(x), Inches(y), height=Inches(h))
    pic.line.color.rgb = LINE
    pic.line.width = Pt(0.75)
    if caption:
        text(slide, x - 0.05, y + h + 0.03, Emu(pic.width).inches + 0.1, 0.5, caption, size=8, color=GREY,
             align=PP_ALIGN.CENTER)
    return pic


# ---------------- 1. Title ----------------
s = title_slide
text(s, 0.55, 2.75, 5.0, 0.6, "OneSitting", size=34, bold=True, color=WHITE)
text(s, 0.55, 3.3, 5.0, 0.4, "A small business goes fully digital in one sitting", size=14, color=WHITE)
text(s, 0.55, 3.75, 5.0, 0.6, [
    "Project Udyam Digital  ·  Airtel Sync 2026 · Digital Track",
    "AI advisor in the owner's language · transparent bundle quote · registry-checked KYC · live order tracker",
], size=9.5, color=RGBColor(0xF2, 0xD6, 0xD6), spacing=3)
text(s, 0.55, 4.5, 5.0, 0.7, [[("Team " + TEAM + "  ·  " + CAMPUS, {"bold": True})], MEMBERS,
                               [("Code: github.com/MRC005/AIRTEL_SYNC", {"size": 9, "color": RGBColor(0xF2, 0xD6, 0xD6)})]],
     size=10, color=WHITE)

# ---------------- 2. Problem in the data ----------------
s = new_slide()
header(s, "Leads are lost to process friction, not to lack of demand",
       "Only 368 of 5,000 leads (7.4%) activate. 1,636 of the drops are visits, quotes, paperwork and install waits a digital journey can remove.")
stages = [("Leads", 5000), ("Contacted", 3406), ("Needs assessed", 1974), ("Quote accepted", 861), ("KYC complete", 588),
          ("Activated", 368)]
leaks = {1: ("827 waited for a visit that never came", RED), 2: ("385 lost to slow or confusing quotes", RED),
         3: ("273 gave up on paperwork", RED), 4: ("151 cancelled during a 10–14 day install", RED)}
y0, bar_max = 1.55, 2.3
for i, (name, n) in enumerate(stages):
    y = y0 + i * 0.5
    text(s, 0.45, y + 0.04, 1.25, 0.3, name, size=9, color=GREY, align=PP_ALIGN.RIGHT)
    w = bar_max * n / 5000
    box(s, 1.8, y, w, 0.32, fill=RED if name == "Activated" else RGBColor(0xC9, 0xC4, 0xCC), line=None, radius=False)
    text(s, 1.85 + w, y + 0.04, 0.8, 0.3, f"{n:,}", size=9, bold=True)
    if i in leaks:  # the drop happens between this stage and the next
        text(s, 4.35, y + 0.27, 2.05, 0.3, "↓ " + leaks[i][0], size=8, color=RED, bold=True)
text(s, 0.45, 4.6, 4.9, 0.4, "Drop reasons at each stage, smb_leads.csv (synthetic), Apr–Jun 2026. "
     "The other 2,385 drops are no-answer, not interested or price: the advisor still helps, but we do not count them.",
     size=7.5, color=GREY)

cards = [
    ("17.6 days", "from lead to activation; every activated customer chased status 3 times"),
    ("6% → 28%", "6-month churn rises with every status chase (1 call vs 5 calls). Waiting hurts loyalty, not just conversion"),
    ("₹15,053", "acquisition cost per activation, against a median bundle of ₹6,900/month"),
    ("9.6% vs 2.0%", "activation with vs without a GSTIN. A ₹41,700 CAC for no-GSTIN leads: needs a different, cheaper path"),
]
for i, (big, small) in enumerate(cards):
    y = 1.5 + i * 0.86
    box(s, 6.55, y, 3.0, 0.76, fill=LIGHT, line=None)
    text(s, 6.66, y + 0.06, 2.85, 0.32, big, size=15, bold=True, color=RED)
    text(s, 6.66, y + 0.37, 2.85, 0.4, small, size=8, color=DARK)

# ---------------- 3. Segments & bundles (Q1) ----------------
s = new_slide()
header(s, "Win offices first; serve micro shops with zero visits",
       "Payback = acquisition cost ÷ monthly bundle value. Micro retail is 54% of leads but takes 8 months to pay back and churns 23% in 6 months.")
rows = [
    ["Priority · segment", "Share of leads", "Activation", "CAC / activation", "Avg monthly value", "Payback", "6-mo churn",
     "Bundle we lead with (tier-2 entry price)"],
    [[("1  Professional offices", {"bold": True})], "25%", "11.1%", "₹10,695", "₹6,796", "1.6 mo", "13.8%",
     "Pro Office: fibre 300 + email & antivirus per user + cloud backup + 3 SIMs · ₹5,583/mo (12 staff) · 12 mo"],
    ["2  Small multi-site", "15%", "11.0%", "₹15,614", "₹31,233", "0.5 mo", "10.8%",
     "Branch Connect: fibre + failover + SD-WAN per site, POS, CCTV · ₹28,970/mo (5 sites) · 24 mo"],
    ["3  Small manufacturers", "6%", "12.8%", "₹15,324", "₹19,980", "0.8 mo", "8.1%",
     "Factory Secure: leased line + firewall + machine IoT + email · ₹14,312/mo · 24 mo"],
    ["4  Micro retail & services", "54%", "4.1%", "₹20,007", "₹2,505", "8.0 mo", "22.7%",
     "Dukaan Starter: fibre 100 + 1 SIM + website · ₹1,597/mo; with GSTIN, WhatsApp API instead of website · ₹2,297/mo"],
]
table(s, 0.45, 1.5, [1.55, 0.62, 0.68, 0.82, 0.86, 0.6, 0.62, 3.35], rows, row_h=0.47, size=8,
      fills={1: LIGHT})
how = [
    ("Digital-first", "Professional offices: one owner decides, single site, high GSTIN share (86%). The advisor can close them without a visit."),
    ("Assisted", "Multi-site & manufacturers: highest value, need a site survey. Advisor qualifies and quotes; partner or field closes."),
    ("Digital-only", "Micro: never send a salesperson (CAC ₹20k vs ₹2.5k/month). Self-serve starter, AirFiber where no fibre, upsell after 3 months."),
]
for i, (t, d) in enumerate(how):
    x = 0.45 + i * 3.05
    box(s, x, 3.95, 2.95, 0.98, fill=WHITE, line=LINE)
    text(s, x + 0.1, 4.0, 2.75, 0.3, t, size=10, bold=True, color=RED)
    text(s, x + 0.1, 4.27, 2.75, 0.7, d, size=8)

# ---------------- 4. Journey & prototype (Q2) ----------------
s = new_slide()
header(s, "One sitting, on the phone, in the owner's language",
       "Working prototype. The AI advisor talks; a rules engine picks products and prices, so it never quotes something the business cannot buy.")
shots = [("1_advisor.png", "1 · Advisor asks ≤6 questions\nchat or voice, 10 languages"),
         ("2_quote.png", "2 · One monthly price\ntoggle add-ons, see GST & setup"),
         ("4_kyc.png", "3 · Smart KYC in seconds\nregistry checks, plain-language fixes"),
         ("5_tracker.png", "4 · Order tracker\nWhatsApp updates instead of calls")]
for i, (img, cap) in enumerate(shots):
    phone(s, SHOTS / img, 0.5 + i * 1.62, 1.45, 2.85, cap)
box(s, 7.05, 1.45, 2.5, 3.45, fill=LIGHT, line=None)
text(s, 7.17, 1.52, 2.3, 3.35, [
    [("How the advisor decides", {"bold": True, "size": 10, "color": RED})],
    "Gemini converses in Hindi, Tamil, Kannada, Marathi, Bengali and more, and fills a business profile (type, staff, sites, city, GSTIN, needs).",
    "A deterministic engine applies every catalogue rule: city tier, minimum staff and sites, GSTIN-only products and product dependencies. It swaps in the closest eligible product and says why.",
    [("Tested cases: ", {"bold": True}), ("no GSTIN → website instead of WhatsApp API; no fibre → 5G AirFiber; 5 staff asking for a leased line → fibre 300 + failover.", {})],
    [("Why it matters: ", {"bold": True}), ("Tamil- and Kannada-preferring leads activate at 4–5% vs 8% for Hindi/English. A vernacular advisor targets that gap directly.", {})],
], size=8, spacing=5)

# ---------------- 5. Smart KYC, architecture, privacy (Q3) ----------------
s = new_slide()
header(s, "Smart KYC: seconds, not days, and private by design",
       "OCR + registry checks replace physical document collection. Problems the owner can fix are returned to them; only real doubts reach a human.")
steps = ["Consent screen\n(DPDP notice)", "Image quality gate\nblur · auto-straighten", "OCR\nOpenCV + Tesseract",
         "GSTIN checksum\n+ OCR auto-repair", "GST & Udyam\nregistry lookup", "Cross-document\nrules → decision"]
for i, st in enumerate(steps):
    x = 0.45 + i * 1.53
    box(s, x, 1.5, 1.38, 0.62, fill=DARK if i in (0, 5) else WHITE, line=LINE)
    text(s, x + 0.04, 1.53, 1.3, 0.58, st, size=8, bold=True, color=WHITE if i in (0, 5) else DARK,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if i < len(steps) - 1:
        text(s, x + 1.36, 1.64, 0.2, 0.3, "›", size=14, bold=True, color=RED)
kyc_rows = [["Sample", "What our checks found", "Decision"],
            ["K01", "GSTIN cancelled in registry; Udyam no. missing (OCR slip I→T auto-fixed)", [("Re-quote without GST products", {"color": RED, "bold": True})]],
            ["K02", "Certificate photographed 7° tilted → straightened, all checks pass", [("Approved", {"color": GREEN, "bold": True})]],
            ["K04", "GST certificate too blurry to read → ask for a retake", [("Owner fixes", {"color": AMBER, "bold": True})]],
            ["K05", "Udyam certificate missing; LLP signatory needs authorisation", [("Owner fixes", {"color": AMBER, "bold": True})]],
            ["K06", "GSTIN on document fails checksum (1 digit changed)", [("Manual review", {"color": AMBER, "bold": True})]],
            ["K07", "Legal name edited: ‘Shri’ vs registry ‘Neelgiri’ Physio Clinic", [("Manual review", {"color": AMBER, "bold": True})]],
            ["K11", "Utility bill 257 days old (limit 90)", [("Owner fixes", {"color": AMBER, "bold": True})]],
            ["K03 K08 K09 K12", "All checks pass (K10 after GSTIN OCR auto-repair)", [("Approved", {"color": GREEN, "bold": True})]]]
table(s, 0.45, 2.3, [1.0, 3.25, 1.5], kyc_rows, row_h=0.29, size=7.5)
box(s, 6.4, 2.3, 3.15, 2.62, fill=LIGHT, line=None)
text(s, 6.52, 2.36, 2.95, 2.55, [
    [("DPDP Act 2023 choices", {"bold": True, "size": 10, "color": RED})],
    [("Consent first: ", {"bold": True}), ("a plain notice (purpose, data, retention, rights) before any upload; no upload API works without a consent ID.", {})],
    [("Purpose limitation: ", {"bold": True}), ("KYC data is used only to verify and activate, never for marketing.", {})],
    [("Minimisation: ", {"bold": True}), ("images are deleted as soon as fields are read; GSTIN, Udyam and ID numbers are masked in the UI and logs.", {})],
    [("Retention & rights: ", {"bold": True}), ("verified fields kept for the contract plus the regulatory period; view, correct or withdraw from the app.", {})],
    [("Next: ", {"bold": True}), ("DigiLocker pull and Aadhaar e-sign replace uploads entirely for most owners.", {})],
], size=8.5, spacing=5)
text(s, 0.45, 4.93, 9.1, 0.2, "Architecture: phone web app / WhatsApp / voice → FastAPI → advisor (Gemini + rules engine) · quote · Smart KYC · orders & tracker · sales view (propensity model)",
     size=7.5, color=DARK)

# ---------------- 6. Competitive analysis ----------------
s = new_slide()
header(s, "Rivals sell products; nobody sells a finished setup",
       "Based on each player's public SMB positioning (2025–26) and the provider mix in our 5,000 leads.")
comp = [
    ["Player", "Where they win", "Gap OneSitting exploits"],
    ["JioBusiness", "Low entry price: 100 Mbps business broadband from about ₹801/mo with JioMeet and productivity tools",
     "Connectivity-led plans; the owner still has to work out the rest of the stack"],
    ["Vi Business", "'Ready For Next' digital-readiness score; website builder, business email, device management",
     "Assessment gives a score and suggestions, not an instantly priced, KYC-ready bundle"],
    ["Tata Tele Business Services", "SMB-only focus; Smartflo cloud telephony, SIP, managed security and internet",
     "Communication-centric, sales-led buying journey"],
    ["Local ISPs & resellers (21% of our leads)", "Cheapest price, neighbourhood relationship, quick install",
     "No bundle, SLA or single bill. Their customers activate with us at only 5.4%: price objections, not trust"],
    ["Digital-first single-product apps", "Instant online sign-up for one product (WhatsApp API, POS, website)",
     "One product each: separate bills and support numbers for every tool"],
    [[("OneSitting (Accel Business)", {"bold": True, "color": RED})],
     "Whole stack in one sitting: vernacular advisor, rules-safe bundle, registry KYC, tracker, one bill",
     "Right to win: 1,890 leads already use Accel (mobile) and activate at 9.2%, the best of any provider group"],
]
table(s, 0.45, 1.5, [2.0, 3.6, 3.5], comp, row_h=0.46, size=8, fills={6: LIGHT})
text(s, 0.45, 4.8, 9.1, 0.3, "Price is the #1 stated objection (621 drops). Our answer is value at a clear monthly price (Dukaan Starter at ₹1,597 vs ₹900 median current spend for micro), not a price war.",
     size=8, color=GREY)

# ---------------- 7. Impact, metrics, field & partners (Q4, Q5) ----------------
s = new_slide()
header(s, "Impact: nearly double activations from the same leads",
       "Conservative model on the Apr–Jun data: recover only part of each friction drop, then apply today's downstream conversion.")
impact = [("13.2%", "lead → activation\n(from 7.4%)"), ("₹8,400", "CAC per activation\n(from ₹15,053, same spend)"),
          ("+291", "activations per\n5,000 leads"), ("~₹9.6 cr", "extra annual\nrecurring revenue")]
for i, (big, small) in enumerate(impact):
    x = 0.45 + i * 1.18
    box(s, x, 1.5, 1.1, 1.05, fill=LIGHT, line=None)
    text(s, x + 0.04, 1.55, 1.02, 0.38, big, size=14, bold=True, color=RED, align=PP_ALIGN.CENTER)
    text(s, x + 0.04, 1.95, 1.02, 0.55, small, size=7, align=PP_ALIGN.CENTER)
text(s, 0.45, 2.6, 4.7, 0.62, "Assumptions: recover 40% of visit drops, 60% of quote drops, 50% of paperwork drops, 30% of install cancellations. "
     "ARR at the ₹6,900 median bundle; four quarters. Pilot will measure each lever separately.", size=7, color=GREY)
metrics = [["Metric (what we report weekly)", "Today", "12-mo target"],
           ["Lead → activation conversion", "7.4%", "13%"],
           ["Days from lead to activation", "17.6", "≤ 7 (≤ 5 micro)"],
           ["Status chases per customer", "3", "≤ 0.5"],
           ["Acquisition cost per activation", "₹15,053", "≤ ₹8,500"],
           ["6-month churn", "15.2%", "≤ 10%"]]
table(s, 0.45, 3.25, [2.6, 0.9, 1.2], metrics, row_h=0.29, size=8)
box(s, 5.35, 1.5, 4.2, 3.48, fill=WHITE, line=LINE)
text(s, 5.48, 1.56, 4.0, 3.4, [
    [("Field force and partners: the advisor adds to them", {"bold": True, "size": 10, "color": RED})],
    [("Partners own their pin codes: ", {"bold": True}), ("every digital sale in a partner's area pays them a commission, so they push the app instead of fighting it.", {})],
    [("Humans get the right leads: ", {"bold": True}), ("the sales view ranks stalled leads by a propensity model. Calling the top 20% reaches 41% of all activations.", {})],
    [("Field sales where visits add value: ", {"bold": True}), ("site surveys for multi-site and manufacturing; no visits for micro shops.", {})],
    [("Referrals as a channel: ", {"bold": True}), ("referral leads activate at 14.8% at ₹4,100 CAC, the best of any source. Built-in 'refer a business' reward.", {})],
    [("Rollout: ", {"bold": True}), ("M0–2 pilot in Pune (tier 1) and Jaipur (tier 2) for professional offices and GSTIN micro; M3–4 WhatsApp + voice; M5–6 national, multi-site via partners.", {})],
    [("Key risk: ", {"bold": True}), ("GenAI errors. Mitigation: AI never sets products or prices; the rules engine does.", {})],
], size=8.5, spacing=6)

# Drop the template's empty content slide (its background was reused above).
sld_ids = prs.slides._sldIdLst
template_content = list(sld_ids)[1]
prs.part.drop_rel(template_content.rId)
sld_ids.remove(template_content)
prs.save(OUT)
bg_content.unlink(missing_ok=True)
print("saved", OUT, "slides:", len(prs.slides))
