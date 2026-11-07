# Data privacy and security note (DPDP Act, 2023)

**Scope.** OneSitting collects business KYC documents (GST certificate, Udyam certificate, address proof, authorised signatory ID) and a short business profile from the advisor chat. All data in this prototype is synthetic, but it is handled as if it were real.

**1. Consent before collection.** The KYC screen shows a plain-language notice before any upload: why we need the documents, what we collect, how it is used, how long it is kept, and the owner's rights. Uploads are refused by the API unless a consent record (`consent_id`) exists, with a timestamp and purpose stored against the session.

**2. Purpose limitation.** KYC data is used only to verify the business and activate services. It is not used for marketing or model training. The advisor chat profile is used to recommend a bundle; lead scoring in the sales view uses only lead-time business attributes, never KYC documents.

**3. Data minimisation.**
- Document images are written to a temporary folder, read, and deleted in the same request (`finally: rmtree`). Only the extracted fields and check results are returned.
- Identifiers (GSTIN, Udyam number, ID number, consumer number) are masked in the UI and API responses: only the last 4 characters are shown.
- We ask for 4 documents because the case requires them; with DigiLocker and registry APIs in production, the address proof and Udyam upload can be dropped for most owners.

**4. Accuracy and fairness.** A blurry or tilted photo is never guessed at: blur is detected and the owner is asked to retake it, tilt is corrected automatically. A GSTIN that fails its checksum is only auto-corrected if the corrected number exists in the registry. Anything inconsistent goes to a human (manual review), not an automatic rejection.

**5. Retention.** Images: not retained. Verified KYC fields: kept for the contract term plus the period telecom KYC rules require, then deleted. Advisor chats from owners who did not buy: deleted after 90 days.

**6. Owner rights.** From the app the owner can see what we hold, correct it, and withdraw consent (which stops processing and triggers deletion, subject to legal retention).

**7. Security.** In production: TLS everywhere; KYC fields encrypted at rest; role-based access so channel partners see only leads in their own pin codes and never KYC documents; audit log of every access; the Gemini API receives only the chat text, never documents or identifiers.

**8. GenAI safety.** The language model never chooses products or prices. A deterministic rules engine does, so eligibility rules (GSTIN-only products, minimum size, city tier, dependencies) cannot be bypassed by a persuasive conversation.
