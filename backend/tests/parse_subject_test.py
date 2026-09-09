"""
parse_subject_test.py — the parser fix, and the three ways it could go wrong.

A parser that recognises MORE is not automatically better. Three failure modes
matter here, in descending order of damage:

  1. A FALSE POSITIVE. Reading "Bonus Ncrps 46:1" as an equity bonus applies a
     0.021 multiplier and puts a 98% phantom crash into a series that was
     correct. This is worse than the miss it replaces, and it is not
     hypothetical -- an earlier version of the audit's own reader did exactly
     this on five production rows.

  2. A REGRESSION. Any line the shipped parser reads today must be read
     identically tomorrow, or the re-parse silently rewrites history that was
     already right.

  3. A remaining miss. The least harmful of the three, and the only one the
     fix is actually aimed at.

The suite is ordered that way on purpose. Nothing here touches production.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from corporate_actions import parse_subject, price_multiplier  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def kinds(subject):
    return sorted(a["kind"] for a in parse_subject(subject))


def one(subject, kind):
    for a in parse_subject(subject):
        if a["kind"] == kind:
            return a
    return None


print("=" * 74)
print("1. FALSE POSITIVES — THE FAILURE THAT IS WORSE THAN A MISS")
print("=" * 74)

MUST_NOT_BONUS = [
    ("Scheme Of Arrangement - Bonus Ncrps 1:10", "NCRPS is preference shares"),
    ("Bonus Ncrps 46:1", "a 0.021 multiplier if believed -- a 98% phantom crash"),
    ("Bonus Ncrps 1:116", "NCRPS"),
    ("Bonus Ncrps 4:1", "NCRPS"),
    ("Scheme Of Arrangement - Bonus Ncrps 3:1", "NCRPS"),
    ("Scheme Of Arrangement - Bonus Ncd 2:1", "NCD is a debenture"),
    ("Bonus Preference Shares 21:1", "preference shares"),
    ("Scheme Of Arrangement - Bonus Debentures 1:1", "debentures"),
    ("Scheme Of Arrangement - Issue Of Bonus Debentures", "debentures, no ratio"),
    ("Bonus Ccps 1:2", "compulsorily convertible preference shares"),
]
for subject, why in MUST_NOT_BONUS:
    check(f"refuses bonus in: {subject[:50]}", "bonus" not in kinds(subject),
          f"{why} | got {kinds(subject)}")

MUST_NOT_SPLIT = [
    ("Rights 3:4 @ Premium Rs.32/- Per Share",
     "a rights premium is not a face value"),
    ("Rights 2:1 @ Premium Rs.35/- Per Share", "same"),
    ("Dividend - Rs 16.25/- Per Share", "a payout is not a face value"),
    ("Interest Payment", "inert"),
    ("Annual General Meeting", "inert"),
]
for subject, why in MUST_NOT_SPLIT:
    check(f"refuses split in: {subject[:50]}", "split" not in kinds(subject),
          f"{why} | got {kinds(subject)}")

check("a rights line yields nothing at all",
      parse_subject("Rights 3:4 @ Premium Rs.32/- Per Share") == [],
      "rights are not modelled as a single multiplier")

print()
print("=" * 74)
print("2. REGRESSIONS — WHAT PARSED BEFORE MUST PARSE THE SAME")
print("=" * 74)

# Every shape the shipped parser already read correctly, with the exact values
# it produced. The re-parse must not move any of these.
UNCHANGED = [
    ("Face Value Split From Rs 10/- Per Share To Re 1/- Per Share",
     "split", {"num": 10.0, "den": 1.0}),
    ("Face Value Split From Rs 10 To Rs 2", "split", {"num": 10.0, "den": 2.0}),
    ("Bonus Issue 1:1", "bonus", {"num": 1.0, "den": 1.0}),
    ("Bonus 6:11", "bonus", {"num": 6.0, "den": 11.0}),
    ("Bonus 1 : 1250", "bonus", {"num": 1.0, "den": 1250.0}),
    ("Dividend - Rs 16.25/- Per Share", "dividend", {"amount": 16.25}),
    ("Dividend Re 0.20/- Per Share", "dividend", {"amount": 0.20}),
    ("Annual General Meeting/ Dividend - Re 1/- Per Share/ E-Voting",
     "dividend", {"amount": 1.0}),
]
for subject, kind, expect in UNCHANGED:
    got = one(subject, kind)
    ok = got is not None and all(abs(got[k] - v) < 1e-9 for k, v in expect.items())
    check(f"unchanged: {subject[:46]:<46} {kind}", ok,
          "" if ok else f"expected {expect}, got {got}")

# The feed runs words together, and the SHIPPED parser read these correctly
# because its regex had no leading word boundary. Adding one dropped 24 real
# dividends in production -- one of them Rs 850 -- and the dry run caught it
# before anything was written. These are here so it cannot happen twice.
RUN_TOGETHER = [
    ("Annual General Meetingdividend - Rs 7.50 Per Share", 7.5),
    ("Annual General Meetingdividend - Re 0.20 Per Share", 0.20),
    ("Interimdividend - Rs 1.30  Per Share", 1.30),
    ("Specia Ldividend - Rs 850 Per Share", 850.0),
    ("Annual General Me0etingdividend - Rs 1.2 Per Share", 1.2),
    ("Annual General Meetingdividend - Rs  45 Per Share", 45.0),
]
for subject, amt in RUN_TOGETHER:
    got = one(subject, "dividend")
    ok = got is not None and abs(got["amount"] - amt) < 1e-9
    check(f"run-together: {subject[:44]:<44} Rs {amt}", ok,
          "" if ok else f"got {got} -- a word boundary would drop this")

# And the other side of that boundary: "div" MUST stay bounded, or the "Div"
# inside "Sub-Division" turns a face-value split into a cash payout.
for subject in ("Sub-Division From Rs 10/- Per Share To Rs 2/- Per Share",
                "Face Valus Split (Sub-Division) - From Rs 10/- Per To Rs 2/- Per Share"):
    check(f"no phantom dividend in: {subject[:44]}",
          "dividend" not in kinds(subject),
          f"got {kinds(subject)} -- 'Div' inside 'Division' is not a payout")

check("an inert line still yields nothing",
      parse_subject("Annual General Meeting") == [])
check("a board meeting still yields nothing",
      parse_subject("Board Meeting Intimation") == [])
check("an interest payment still yields nothing",
      parse_subject("Interest Payment") == [])

print()
print("=" * 74)
print("3. THE FOUR GAPS THE FIX IS FOR")
print("=" * 74)

RECOVERED = [
    ("Face Value Split Rs.10/- To Rs.2/-", "split", {"num": 10.0, "den": 2.0},
     "the old regex demanded the word 'from'"),
    ("Face Value Split Rs 10 To Rs 5", "split", {"num": 10.0, "den": 5.0},
     "same"),
    ("Face Value Split Rs 10 To Re 1", "split", {"num": 10.0, "den": 1.0},
     "same, with 'Re'"),
    ("Sub-Division From Rs 10/- Per Share To Rs 2/- Per Share", "split",
     {"num": 10.0, "den": 2.0}, "the old parser also demanded the word 'split'"),
    ("Face Valus Split (Sub-Division) - From Rs 10/- Per To Rs 2/- Per Share",
     "split", {"num": 10.0, "den": 2.0}, "the feed's own typo, 'Valus'"),
    ("Bonus - 3:1", "bonus", {"num": 3.0, "den": 1.0},
     "a hyphen blocked the old regex"),
    ("Bonus- 1:2", "bonus", {"num": 1.0, "den": 2.0}, "hyphen, no space"),
    ("Annual Geneeral Meeting/Div.Rs.3/- Per Share", "dividend", {"amount": 3.0},
     "abbreviated 'Div.' behind a feed typo"),
    ("Annual General Meeting/Fin.Div.Rs.2/- Per Share", "dividend",
     {"amount": 2.0}, "'Fin.Div.'"),
    ("Annual General Meeting / Div. Of Rs.10 Per Share", "dividend",
     {"amount": 10.0}, "'Div. Of'"),
    ("Annual General Meeting/Div-Rs.0.60 Per Share", "dividend",
     {"amount": 0.60}, "'Div-Rs.'"),
]
for subject, kind, expect, why in RECOVERED:
    got = one(subject, kind)
    ok = got is not None and all(abs(got[k] - v) < 1e-9 for k, v in expect.items())
    check(f"recovers {kind}: {subject[:44]}", ok,
          why if ok else f"expected {expect}, got {got}")

print()
print("  multi-action lines — one row, two events:")
MULTI = [
    ("Bonus 1:1 And Face Value Split Rs.10/- To Rs.5/- Per Share",
     {"bonus", "split"}, 0.25, "JBMA"),
    ("Bonus 1:2 And Face Value Split Rs.10/- To Rs.5/-",
     {"bonus", "split"}, 0.666667 * 0.5, "INE442H01011"),
    ("Bonus 1 : 1 / Face Value Split From Rs 10/- Each To Rs 2/- Each",
     {"bonus", "split"}, 0.5 * 0.2, "INE288B01011"),
    ("Annual General Meeting / Dividend - Rs 3/- Per Share / Bonus - 1:2",
     {"bonus", "dividend"}, None, "INE775A01035"),
]
for subject, expect, product, who in MULTI:
    got = set(kinds(subject))
    ok = got == expect
    check(f"  {who}: {sorted(expect)}", ok, "" if ok else f"got {sorted(got)}")
    if ok and product is not None:
        m = 1.0
        for a in parse_subject(subject):
            if a["kind"] in ("split", "bonus"):
                m *= price_multiplier(a)
        check(f"    ...combined multiplier {round(m, 6)}",
              abs(m - product) < 1e-6, f"expected {round(product, 6)}")

# JBMA end to end, against the multiplier its prices imply.
m = 1.0
for a in parse_subject("Bonus 1:1 And Face Value Split Rs.10/- To Rs.5/- Per Share"):
    mm = price_multiplier(a)
    if mm:
        m *= mm
check("JBMA now yields 0.25, matching the 0.2399 its prices imply",
      abs(m - 0.25) < 1e-9, f"{m} -- the 4% residual is a genuine move that day")

print()
print("=" * 74)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
