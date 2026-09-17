"""
french_quality_value_check.py: the pre-registered check in
docs/PREREG_FRENCH_QUALITY_VALUE_2026-09-17.md.

Profitability (RMW) and value (HML) premiums on Kenneth French's emerging
markets (includes India) and US five-factor files. Reuses the Newey-West mean
test and the descriptive stats from iima_factor_check.py, unchanged.

    python research/french_quality_value_check.py <data_dir> [out.json]

Data: Kenneth R. French Data Library, Tuck School of Business, Dartmouth.
"""

import csv
import hashlib
import io
import json
import os
import sys
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from iima_factor_check import describe, newey_west_mean  # noqa: E402

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"emerging": "Emerging_5_Factors_CSV.zip",
         "us": "F-F_Research_Data_5_Factors_2x3_CSV.zip"}
MISSING = -99.99
ALPHA_EACH = 0.05 / 2
OOS_START = {"us": "2014-01", "emerging": "2016-01"}


def fetch(data_dir, name):
    path = os.path.join(data_dir, name)
    if not os.path.exists(path):
        urllib.request.urlretrieve(BASE + name, path)
    with open(path, "rb") as f:
        blob = f.read()
    return blob, hashlib.sha256(blob).hexdigest()


def monthly(blob):
    """{YYYY-MM: {col: float | None}} from the monthly block only."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    rows, header = {}, None
    for rec in csv.reader(io.StringIO(text)):
        cells = [c.strip() for c in rec]
        if not any(cells):
            if header and rows:
                break                      # blank line after the monthly block
            continue
        if cells[0] == "" and "RMW" in cells:
            header = cells
            continue
        if header and len(cells[0]) == 6 and cells[0].isdigit():
            vals = {}
            for col, v in zip(header[1:], cells[1:]):
                x = float(v)
                vals[col] = None if abs(x - MISSING) < 1e-9 else x
            rows[f"{cells[0][:4]}-{cells[0][4:]}"] = vals
        elif header and rows:
            break                          # "Annual Factors" or any other block
    return rows


def pairs(rows, col, start=None):
    return [(m, v[col]) for m, v in sorted(rows.items())
            if v.get(col) is not None and (start is None or m >= start)]


def main():
    data_dir = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    os.makedirs(data_dir, exist_ok=True)
    data, hashes = {}, {}
    for region, name in FILES.items():
        blob, hashes[name] = fetch(data_dir, name)
        data[region] = monthly(blob)

    primary = {}
    for label, region in (("Q1_emerging_RMW", "emerging"), ("Q2_us_RMW", "us")):
        p = pairs(data[region], "RMW")
        res = newey_west_mean([v for _, v in p])
        res["first_month"], res["last_month"] = p[0][0], p[-1][0]
        res["passes"] = (res["mean_pct_per_month"] > 0
                         and res["p_two_sided"] is not None
                         and res["p_two_sided"] < ALPHA_EACH)
        primary[label] = res

    secondary = {"out_of_sample": {}, "hml_full": {}, "descriptive": {}}
    for region in ("us", "emerging"):
        for col in ("RMW", "HML"):
            p = pairs(data[region], col, OOS_START[region])
            secondary["out_of_sample"][f"{region}_{col}"] = {
                **newey_west_mean([v for _, v in p]),
                "first_month": p[0][0], "last_month": p[-1][0]}
        p = pairs(data[region], "HML")
        secondary["hml_full"][region] = {
            **newey_west_mean([v for _, v in p]),
            "first_month": p[0][0], "last_month": p[-1][0]}
        secondary["descriptive"][f"{region}_RMW"] = describe(pairs(data[region], "RMW"))

    out = {
        "preregistration": "docs/PREREG_FRENCH_QUALITY_VALUE_2026-09-17.md",
        "source": "Kenneth R. French Data Library, Tuck School of Business, Dartmouth",
        "files": hashes,
        "alpha_each": ALPHA_EACH,
        "months_read": {r: len(v) for r, v in data.items()},
        "primary": primary,
        "secondary": secondary,
        "limits": [
            "Emerging markets are 24 countries including India; India's share is not published.",
            "RMW is operating profitability, not Quant India's quality score.",
            "US months to 2013 and emerging months to 2015 were in the samples "
            "that defined these factors; the out-of-sample rows are the honest test.",
        ],
    }
    text = json.dumps(out, indent=2)
    if out_path:
        with open(out_path, "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
