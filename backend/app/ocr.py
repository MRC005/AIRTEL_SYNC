"""OCR for KYC documents.

The specimen documents carry a light-pink diagonal watermark. We remove it by keeping
only dark pixels before running Tesseract, then parse the "Label   Value" layout into
a dict of fields.
"""
import re
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

# Labels as printed on each document type -> our field names.
LABELS = {
    "gst_certificate": {
        "GSTIN": "gstin",
        "Legal name": "legal_name",
        "Trade name": "trade_name",
        "Constitution": "constitution",
        "Address of principal": "address",
        "Date of liability": "liability_date",
        "Type of registration": "registration_type",
    },
    "udyam_certificate": {
        "Udyam reg. number": "udyam_number",
        "Enterprise name": "enterprise_name",
        "Major activity": "major_activity",
        "City": "city",
        "State": "state",
        "Date of registration": "registration_date",
    },
    "address_proof": {
        "Consumer no.": "consumer_no",
        "Billed to": "billed_to",
        "Supply address": "address",
        "Bill date": "bill_date",
        "Units consumed": "units",
        "Amount due (INR)": "amount_due",
    },
    "signatory_id": {
        "Name": "name",
        "Designation": "designation",
        "For business": "business",
        "ID no.": "id_no",
        "Valid till": "valid_till",
    },
}


def detect_doc_type(path: Path, text: str) -> str:
    """Use the filename if it says what the document is, otherwise the page title."""
    for t in LABELS:
        if t in path.name:
            return t
    head = text[:200].lower()
    if "gst registration" in head:
        return "gst_certificate"
    if "udyam" in head:
        return "udyam_certificate"
    if "signatory" in head:
        return "signatory_id"
    return "address_proof"


def quality_check(img: np.ndarray) -> dict:
    """Blur score (variance of the Laplacian) and page skew, measured before OCR."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    dark = np.column_stack(np.where(img.max(axis=2) < 100))
    angle = 0.0
    if len(dark) > 500:
        (_, _), (w, h), a = cv2.minAreaRect(dark[:, ::-1].astype(np.float32))
        # minAreaRect reports angles in a 90-degree range; fold into [-45, 45].
        while a < -45:
            a += 90
        while a > 45:
            a -= 90
        angle = a
    return {"blur_score": round(blur, 1), "is_blurry": blur < BLUR_THRESHOLD, "skew_deg": round(angle, 1)}


BLUR_THRESHOLD = 150.0  # calibrated on the specimen set: sharp docs score far above this


def deskew(img: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.5:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def clean_image(path: Path, img: np.ndarray | None = None, angle: float = 0.0) -> np.ndarray:
    """Straighten the page, then drop the pink watermark by keeping only dark pixels."""
    if img is None:
        img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Could not read image: {path.name}")
    img = deskew(img, angle)
    dark = (img.max(axis=2) < 140).astype(np.uint8)
    out = np.where(dark == 1, 0, 255).astype(np.uint8)
    # Upscale small images (ID cards) so Tesseract reads them reliably.
    if out.shape[1] < 1200:
        out = cv2.resize(out, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return out


def run_tesseract(img: np.ndarray) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, img)
        res = subprocess.run(
            ["tesseract", f.name, "-", "--psm", "6"],
            capture_output=True, text=True, timeout=60,
        )
    return res.stdout


def parse_fields(text: str, doc_type: str) -> dict:
    """Map 'Label value' lines to fields. Wrapped address lines are appended."""
    labels = LABELS[doc_type]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    fields: dict = {}
    last = None
    i = 0
    while i < len(lines):
        line = lines[i]
        matched = False
        for label, key in sorted(labels.items(), key=lambda kv: -len(kv[0])):
            if line.lower().startswith(label.lower()):
                value = line[len(label):].strip(" :")
                # ID cards print the value on the next line.
                if not value and i + 1 < len(lines) and not any(
                    lines[i + 1].lower().startswith(l.lower()) for l in labels
                ):
                    value = lines[i + 1].strip()
                    i += 1
                fields[key] = value
                last = key
                matched = True
                break
        if not matched and last == "address" and "place of business" in line.lower():
            fields["address"] += line.lower().split("place of business", 1)[1].strip()
            matched = True
        elif not matched and last == "address" and doc_type == "address_proof" and not line.lower().startswith("bill"):
            fields["address"] += line
            matched = True
        i += 1
    for k in labels.values():
        fields.setdefault(k, "")
    if "gstin" in fields:
        fields["gstin"] = fix_gstin_ocr(fields["gstin"].replace(" ", "").upper())
    if "udyam_number" in fields:
        fields["udyam_number"] = fields["udyam_number"].replace(" ", "").upper()
    return fields


def fix_gstin_ocr(g: str) -> str:
    """GSTIN positions 1-2, 8-11 are digits; 3-7 and 12 letters. Fix common OCR swaps."""
    if len(g) != 15:
        return g
    to_digit = {"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"}
    to_alpha = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"}
    chars = list(g)
    for idx in [0, 1, 7, 8, 9, 10]:
        chars[idx] = to_digit.get(chars[idx], chars[idx])
    for idx in [2, 3, 4, 5, 6, 11]:
        chars[idx] = to_alpha.get(chars[idx], chars[idx])
    return "".join(chars)


def extract(path: Path) -> dict:
    """Quality gate first; a blurry photo is sent back to the customer instead of guessed at."""
    original = cv2.imread(str(path))
    if original is None:
        raise ValueError(f"Could not read image: {path.name}")
    quality = quality_check(original)
    doc_type = detect_doc_type(path, "")
    if quality["is_blurry"]:
        return {"doc_type": doc_type, "quality": quality, "fields": {}, "raw_text": ""}
    text = run_tesseract(clean_image(path, original, quality["skew_deg"]))
    doc_type = detect_doc_type(path, text)
    return {"doc_type": doc_type, "quality": quality, "fields": parse_fields(text, doc_type), "raw_text": text}
