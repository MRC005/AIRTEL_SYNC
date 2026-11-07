# Walkthrough: how OneSitting works (read this before any presentation)

## The flow in one sentence
Owner chats → **advisor** builds a profile → **rules engine** picks and prices a bundle → owner toggles add-ons → **consent** → **Smart KYC** reads 4 photos and checks registries → **order** → **tracker**. A separate **sales view** ranks stalled leads.

```
Phone (web / WhatsApp / voice)
   │
FastAPI  backend/app/main.py
   ├─ advisor.py      Gemini: talk + fill profile (JSON schema)   ──► recommender.py  rules + prices
   ├─ /api/quote      re-check rules on every toggle (catalogue.py)
   ├─ orders.py       consent record, order, tracker stages
   ├─ kyc.py          ocr.py (OpenCV + Tesseract) → registry.py (checksum, lookups) → decision
   └─ propensity.py   logistic regression → call list for partners
```

## Design choices you must be able to defend

**1. Why the AI does not choose products.** LLMs can be talked into things ("give me WhatsApp API, I'll get GST later"). The catalogue has hard rules (requires_gstin, min_employees, min_sites, city tiers, requires_one_of). So Gemini only collects facts and explains; `recommender.py` decides. That's why 15 tricky test scenarios cannot break eligibility.

**2. How the engine picks connectivity** (`pick_connectivity`): dedicated line for factories/ERP, 300 Mbps when more than 5 people share a site, else 100 Mbps; 5G AirFiber when fibre isn't available. If the wanted product isn't eligible it walks a downgrade chain (P06 → P05 → P03 → P02) and records why.

**3. Dependencies.** CCTV, failover, static IP and SIP need an internet line in the same bundle (`requires_one_of`). The engine adds the cheapest eligible one; the quote API rejects a selection that breaks this.

**4. Pricing.** Transparent rule: tier-2 cities pay the catalogue minimum, tier-1 the mid-point. Contract = the longest minimum contract in the bundle (at least 12 months). GST 18% shown separately.

**5. Smart KYC pipeline** (`ocr.py`, `kyc.py`):
- *Blur:* variance of the Laplacian (an edge-sharpness score). Sharp specimens score ~900+, the blurred K04 scores 1. Threshold 150. Same idea as the image-quality gate in TreadCheck.
- *Tilt:* `cv2.minAreaRect` on dark pixels gives the page angle; rotate back if more than 0.5°. K02 was 7° off.
- *Watermark:* keep only pixels darker than 140 in every channel. The pink watermark disappears and the text stays.
- *GSTIN checksum:* official base-36 algorithm with alternating weights 1 and 2. All 3,534 registry GSTINs pass it. If OCR misreads a character (I/T/J, O/0, S/5…), we try one-character swaps and accept only a candidate that passes the checksum **and** exists in the registry (K01, K10).
- *Registry checks:* GSTIN status (Cancelled/Suspended → cannot sell GST-only products), legal and trade name match, PIN code match, Udyam number and name.
- *Cross-document checks:* bill under 90 days old (README's "today" = 2026-07-15), bill in the business's name, signatory is the proprietor (proprietorships) or needs an authorisation letter (LLP / company), ID not expired.
- *Name matching:* text similarity ≥ 0.93 after removing punctuation, plus the business name inside "(Prop. …)" must match. Low enough to absorb OCR noise, high enough to catch one changed word (K07: "Shri" vs "Neelgiri").
- *Decision:* GSTIN not active → re-quote without GST products (keep the sale). Owner-fixable problems → ACTION_NEEDED. Anything suspicious → MANUAL_REVIEW. Otherwise APPROVED.

**6. Things we deliberately did NOT flag.** Udyam "date of registration" and "major activity" differ from the registry on almost every certificate, so they're noise in the synthetic data. Flagging them would send good customers to manual review.

**7. Lead scoring** (`propensity.py`): logistic regression with one-hot categories + scaled numbers. Only lead-time features (no stage dates, no outcome), to avoid **leakage**. 5-fold cross-validated AUC 0.71. The top 20% of scored leads contain 41% of activations, 2× random. Logistic regression was picked so a sales manager can see the drivers: referral +, WhatsApp campaign −, micro −, GSTIN +, Tamil/Kannada − (the regional-language gap the advisor targets).

**8. Privacy** (see `privacy_note.md`): consent ID required by the upload API; images deleted in a `finally` block; IDs masked; Gemini never sees documents.

## Numbers in the deck and where they come from
Run `python3 analysis/insights.py`. Key ones: 7.4% activation; 17.6 days; ₹15,053 CAC; churn 6% → 28% with status chases; segment payback (CAC ÷ MRR); impact model +291 activations (recover 40/60/50/30% of visit/quote/paperwork/install drops × today's downstream rates).

## Likely judge questions
- *What if the owner lies about GST?* KYC verifies the GSTIN against the registry; if it isn't active, GST-only products are removed and the quote is re-run.
- *What if OCR is wrong?* Checksum + registry confirmation for GSTIN; fuzzy matching for names; unclear cases go to a human, never an auto-reject.
- *Why not let field sales do micro?* CAC ₹20,007 against ₹2,505/month MRR with 22.7% churn: an 8-month payback before churn. Digital-only is the only profitable way.
- *Channel conflict?* Partners get a commission on digital sales in their pin codes, plus the ranked call list.
- *Production readiness?* Swap mocks for GSTN/Udyam APIs and DigiLocker; persistent DB; WhatsApp Business API front end; monitoring of advisor conversations.
