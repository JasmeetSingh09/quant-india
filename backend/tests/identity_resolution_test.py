"""
identity_resolution_test.py — the four ways a security can change identity.

Each case here corresponds to something the exchange actually does, and to a
specific wrong answer the backtest gave before. They run on synthetic pairs
rather than the database so the expected answer is known rather than observed.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))

from security_identity import _resolve_pairs, LINK_MAX_GAP_DAYS  # noqa: E402

PASS, FAIL = [], []


def check(name, got, want):
    (PASS if got == want else FAIL).append((name, got, want))
    mark = "ok  " if got == want else "FAIL"
    print(f"  [{mark}] {name}: got {got}, want {want}")


def comps(rows):
    canonical, components, links, ambiguous = _resolve_pairs(rows)
    return canonical, components, links, ambiguous


print("\n1. Rename: one ISIN, two tickers (ZOMATO -> ETERNAL)")
# The original bug. One ISIN throughout, so identity was never in doubt once
# the ISIN was present — this confirms the rename does not split the company.
rows = [
    ("INE758T01015", "ZOMATO.NS", "2024-01-01", "2025-05-20", 340),
    ("INE758T01015", "ETERNAL.NS", "2025-05-21", "2026-08-28", 320),
]
_, components, links, amb = comps(rows)
check("one company", len(components), 1)
check("no ISIN links needed", len(links), 0)

print("\n2. Restructure: one ticker, ISIN replaced in sequence")
# The mirror bug, and the larger of the two in this window. Keyed on ISIN the
# old identifier vanishes and the position is booked at -100%.
rows = [
    ("INE000A01011", "ACME.NS", "2024-01-01", "2025-06-30", 370),
    ("INE000A01029", "ACME.NS", "2025-07-01", "2026-08-28", 290),
]
_, components, links, amb = comps(rows)
check("one company", len(components), 1)
check("one link recorded", len(links), 1)
check("nothing ambiguous", len(amb), 0)

print("\n3. Ticker reuse after a long gap: two different companies")
# Merging these would erase a real delisting, so they must stay apart.
rows = [
    ("INE111A01011", "OLDCO.NS", "2024-01-01", "2024-03-15", 50),
    ("INE222B01011", "OLDCO.NS", "2026-01-05", "2026-08-28", 150),
]
_, components, links, amb = comps(rows)
check("two companies", len(components), 2)
check("no link made", len(links), 0)
check("flagged ambiguous", len(amb), 1)

print("\n4. Two ISINs trading under one ticker at once: not one security")
rows = [
    ("INE333C01011", "DUAL.NS", "2024-01-01", "2026-08-28", 600),
    ("INE444D01011", "DUAL.NS", "2024-02-01", "2026-08-28", 590),
]
_, components, links, amb = comps(rows)
check("two companies", len(components), 2)
check("flagged ambiguous", len(amb), 1)

print("\n5. Chain: A -> B under one ticker, B -> C under another")
rows = [
    ("INE555E01011", "FIRST.NS", "2024-01-01", "2024-12-31", 250),
    ("INE666F01011", "FIRST.NS", "2025-01-01", "2025-06-30", 120),
    ("INE666F01011", "SECOND.NS", "2025-07-01", "2025-12-31", 125),
    ("INE777G01011", "SECOND.NS", "2026-01-01", "2026-08-28", 160),
]
_, components, links, amb = comps(rows)
check("all one company", len(components), 1)
check("two links", len(links), 2)

print("\n6. Canonical id is stable regardless of row order")
import random  # noqa: E402
shuffled = rows[:]
random.seed(7)
random.shuffle(shuffled)
c1, _, _, _ = comps(rows)
c2, _, _, _ = comps(shuffled)
check("same mapping", c1, c2)

print("\n7. A gap just inside the window links, just outside does not")
from datetime import date, timedelta  # noqa: E402
base = date(2025, 1, 1)


def gap_case(gap_days):
    end = base + timedelta(days=200)
    return [
        ("INE888H01011", "EDGE.NS", base.isoformat(), end.isoformat(), 150),
        ("INE999I01011", "EDGE.NS", (end + timedelta(days=gap_days)).isoformat(),
         (end + timedelta(days=gap_days + 100)).isoformat(), 70),
    ]


_, c_in, _, _ = comps(gap_case(LINK_MAX_GAP_DAYS))
_, c_out, _, _ = comps(gap_case(LINK_MAX_GAP_DAYS + 1))
check(f"gap of {LINK_MAX_GAP_DAYS} days merges", len(c_in), 1)
check(f"gap of {LINK_MAX_GAP_DAYS + 1} days does not", len(c_out), 2)

print("\n8. A security that never changes anything is untouched")
rows = [("INEAAA01011", "STABLE.NS", "2024-01-01", "2026-08-28", 650)]
_, components, links, amb = comps(rows)
check("one company", len(components), 1)
check("no links", len(links), 0)
check("no ambiguity", len(amb), 0)

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
if FAIL:
    for n, got, want in FAIL:
        print(f"  FAILED {n}: got {got}, want {want}")
sys.exit(1 if FAIL else 0)
