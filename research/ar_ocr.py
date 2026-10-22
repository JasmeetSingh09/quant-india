"""
ar_ocr.py — OCR text for annual reports whose text layer is missing or garbled (reader fix 2A).

Plan: docs/AR_READER_FIX_PLAN_2026-10-17.md, phase 2. Pages are OCR'd when either
  - the page has no text layer (fewer than 40 characters), or
  - the whole file's text layer is garbled: under 10% of its words are common English
    words in a sample of pages AND "balance sheet" appears on no page.
OCR: Tesseract 5.4 (owner-approved install 2026-10-05), 300 dpi, page segmentation mode 6
(one block, read row by row, which keeps a statement's line and its numbers together).

Output goes to a SEPARATE cache (default quant_data/ar_cache_ocr) in the reader's own format
{"pages": [...]} plus {"ocr_pages": [...], "engine": "..."} so every OCR'd page stays
identifiable; the original text cache is never modified. Pages not OCR'd keep the reader's
original text (its pdfplumber cache when present).

    python research/ar_ocr.py <reports_dir> <files.json> [--out DIR] [--workers N]
"""
import io
import json
import os
import pickle
import re
import sys
from concurrent.futures import ProcessPoolExecutor

TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
ENGINE = "tesseract 5.4, 300 dpi, psm 6"
COMMON = re.compile(r"\b(the|and|of|to|in|for|company|year|total)\b", re.I)


def cache_key(rel):
    return rel.replace("\\", "_").replace("/", "_").replace(" ", "_")[:-4]


def garbled(doc):
    n = len(doc)
    sample = range(0, n, max(1, n // 25))
    raw = " ".join(doc[i].get_text() for i in sample)
    words = len(re.findall(r"[A-Za-z]{3,}", raw)) or 1
    ratio = len(COMMON.findall(raw)) / words
    bs = any(re.search(r"balance\s*sheet", doc[i].get_text(), re.I) for i in range(n))
    return ratio < 0.10 and not bs, round(ratio, 3)


def complete(path, n_pages):
    """A finished OCR cache file: it unpickles and has one text per page."""
    try:
        d = pickle.load(open(path, "rb"))
        return len(d.get("pages") or []) == n_pages
    except Exception:
        return False


def ocr_file(args):
    root, rel, out, orig_cache = args
    import pymupdf
    target = os.path.join(out, cache_key(rel) + ".pkl")
    n = len(pymupdf.open(os.path.join(root, rel)))
    # Resume: a run stopped part-way (2026-10-20) left finished files that need no redo.
    if os.path.exists(target) and complete(target, n):
        return rel, n, -1, None
    import pytesseract
    from PIL import Image
    pytesseract.pytesseract.tesseract_cmd = TESSERACT
    doc = pymupdf.open(os.path.join(root, rel))
    is_garbled, ratio = garbled(doc)
    base = None
    pk = os.path.join(orig_cache, cache_key(rel) + ".pkl") if orig_cache else None
    if pk and os.path.exists(pk):
        base = pickle.load(open(pk, "rb"))["pages"]
    pages, ocr_pages = [], []
    for i in range(len(doc)):
        layer = doc[i].get_text()
        if is_garbled or len(layer.strip()) < 40:
            img = Image.open(io.BytesIO(doc[i].get_pixmap(dpi=300).tobytes("png")))
            pages.append(pytesseract.image_to_string(img, config="--psm 6"))
            ocr_pages.append(i)
        else:
            pages.append(base[i] if base and i < len(base) else layer)
    # Atomic: write a temporary file and rename it only when complete. The 2026-10-20 run was
    # killed mid-write and left a truncated Coal India FY2012 file that would not unpickle.
    tmp = target + ".partial"
    with open(tmp, "wb") as fh:
        pickle.dump({"pages": pages, "ocr_pages": ocr_pages, "engine": ENGINE, "garbled_text_layer": is_garbled,
                     "english_ratio": ratio}, fh)
    os.replace(tmp, target)
    return rel, len(doc), len(ocr_pages), is_garbled


def main():
    root, files_json = sys.argv[1], sys.argv[2]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(os.path.dirname(root), "ar_cache_ocr")
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    orig = os.path.join(os.path.dirname(root), "ar_cache")
    os.makedirs(out, exist_ok=True)
    files = json.load(open(files_json, encoding="utf-8"))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for rel, n, k, g in ex.map(ocr_file, [(root, f, out, orig) for f in files]):
            print(f"{rel}: {n} pages, " + ("already complete, skipped" if k < 0 else
                  f"{k} OCR'd{' (garbled text layer)' if g else ''}"), flush=True)


if __name__ == "__main__":
    main()
