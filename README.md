# OneSitting: small business, fully digital in one sitting

Prototype for **Airtel Sync 2026, Digital Track: Project Udyam Digital** (fictional operator *Accel Business*, synthetic data).

A small business owner chats with an AI advisor in their own language, gets one transparent monthly price for a bundle that fits their business, completes KYC by photographing four documents, and tracks activation without calling support. A sales/partner view ranks stalled leads by how likely they are to convert.

## Run it

```bash
cd backend
python3 -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000 (use the browser's phone view for the intended layout).

The AI advisor needs a free Gemini API key. Put it in `.env` at the project root (copy `.env.example`). Without a key, the advisor runs a guided question flow and everything else works the same.

Requirements: Python 3.11+, `fastapi uvicorn python-multipart python-dotenv httpx pandas scikit-learn opencv-python`, and the Tesseract OCR binary (`brew install tesseract`).

## What is in the box

| Part | File | What it does |
|---|---|---|
| Advisor | `backend/app/advisor.py` | Gemini asks up to 6 questions in the owner's language and fills a business profile. Scripted fallback when no key is set. |
| Bundle engine | `backend/app/recommender.py`, `catalogue.py` | Picks products and prices with plain rules from `product_catalogue.csv`: city tier, minimum staff and sites, GSTIN-only products, dependencies. Swaps in the closest eligible product and explains why. |
| Quote | `main.py /api/quote` | Re-prices the owner's toggles on the server and re-checks every rule. |
| Smart KYC | `backend/app/ocr.py`, `kyc.py`, `registry.py` | Image quality gate (blur, auto-straighten), OCR, GSTIN checksum with OCR auto-repair, mock GSTIN/Udyam registry lookups, cross-document checks, and a decision: approved / owner fixes / manual review / re-quote without GST products. |
| Tracker | `backend/app/orders.py` | Order stages with expected dates per product, plus WhatsApp-style updates. |
| Sales view | `backend/app/propensity.py` | Logistic regression on lead-time features only (no leakage). AUC 0.71; the top 20% of scored leads hold 41% of activations. |
| Privacy | `orders.py`, `kyc.py`, `main.py` | Consent before upload, images deleted after reading, identifiers masked. See `docs/privacy_note.md`. |

## Smart KYC on the 12 specimen applicants

| Applicant | Found | Decision |
|---|---|---|
| K01 | GSTIN cancelled; Udyam number missing | Re-quote without GST-only products |
| K02 | Photo tilted 7°, straightened automatically | Approved |
| K03, K08, K09, K12 | All checks pass | Approved |
| K04 | GST certificate too blurry | Owner retakes photo |
| K05 | Udyam certificate missing; LLP signatory needs authorisation | Owner uploads |
| K06 | GSTIN on certificate fails checksum (digit changed) | Manual review |
| K07 | Legal name on certificate differs from registry | Manual review |
| K10 | OCR misread one GSTIN letter, auto-repaired; LLP signatory authorisation | Owner uploads |
| K11 | Utility bill 257 days old | Owner uploads a recent bill |

## Data insights used in the deck

Run `python3 analysis/insights.py` to reproduce every number in the deck from `smb_leads.csv`.

## Rebuild the deck

`python3 deck/build_deck.py` (needs Airtel's `Submission Template_Sync.pptx` in `docs/`, which is not included in this repo). `deck/capture.py` re-takes the app screenshots with the app running.

Team **FullBars** (VIT): Machum Roy Choudhury, Cheralathan M.
