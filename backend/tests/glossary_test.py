"""
glossary_test.py: the site's definitions exist, match the app, and admit limits.

frontend/src/glossary.js feeds every tooltip. Until 2026-09-23 several entries
contradicted the app: the p-value was "the chance the result is just luck",
pairs trading "profits even if the market falls", Sharpe "above 2 is
excellent", and confidence "how sure the model is". This pins the corrected
wording, requires a "can't tell you" line for every term, and checks every
tooltip key used in the frontend exists. No network; reads source files only.
"""

import glob
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src")
PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}  {'' if cond else detail}")


src = open(os.path.join(ROOT, "glossary.js"), encoding="utf-8").read()


def block(name):
    m = re.search(r"export const " + name + r" = \{(.*?)\n\}", src, re.S)
    return dict(re.findall(r'^\s+(\w+):\s*"((?:[^"\\]|\\.)*)"', m.group(1), re.M)) if m else {}


G, L = block("GLOSSARY"), block("LIMITS")

print("\n1. Every term has a definition and a limit")
ok(len(G) >= 60, f"glossary parsed ({len(G)} terms)")
ok(set(G) == set(L), "GLOSSARY and LIMITS have exactly the same terms",
   f"missing limits {sorted(set(G) - set(L))}, stray {sorted(set(L) - set(G))}")
ok(all(len(v) > 15 for v in L.values()), "every limit says something")

print("\n2. Definitions match how the app computes them")
ok("risk-free" in G.get("sharpe", "") and "swing" in G.get("sharpe", ""),
   "Sharpe: excess over the risk-free rate over the swing (risk_metrics.sharpe)")
ok("below the risk-free rate" in G.get("sortino", "") and "all periods" in G.get("sortino", ""),
   "Sortino: shortfall below the risk-free rate across all periods (risk_metrics.sortino)")
ok("skipping the latest month" in G.get("momentum", ""),
   "momentum: the stock's own 12-1 return (alpha_model)")
ok(G.get("confidence", "").startswith("Data coverage"), "confidence is data coverage")
ok("not a predicted return" in G.get("alpha_score", ""), "alpha score is not a predicted return")
ok("not been tested" in L.get("alpha_score", ""), "its limit says the combined score is untested")
ok("not among the largest" in L.get("momentum", ""), "momentum's limit carries the large-stock caveat")
ok("If there were no real effect" in G.get("pvalue", ""), "p-value defined conditionally, not as 'the chance it is luck'")

print("\n3. The old wrong wording is gone, and nothing promises a return")
banned = ["excellent", "real skill", "profits even", "just luck", "more trustworthy",
          "better value"]
text = " ".join(list(G.values()) + list(L.values())).lower()
for b in banned:
    ok(b not in text, f"no '{b}'")
for v in list(G.values()) + list(L.values()):
    for m in re.finditer(r"\bguarantee", v.lower()):
        ok(re.search(r"\bnot\b", v.lower()[max(0, m.start() - 20):m.start()]) is not None,
           f"'guarantee' only in a negation: {v[:50]}")
ok(not re.search(r"\bwill (rise|fall|outperform|beat|grow)\b", text), "no promise of a future move")

print("\n4. Every tooltip used in the frontend exists")
used = set()
for f in glob.glob(os.path.join(ROOT, "**", "*.jsx"), recursive=True):
    s = open(f, encoding="utf-8").read()
    used |= set(re.findall(r'<(?:InfoTip|Term)\s+k="(\w+)"', s))
    used |= set(re.findall(r'\btip="(\w+)"', s))
    # Tables built from lists like ['Sharpe', value, 'sharpe'] pass the key as
    # the last element, in files that render <InfoTip k={tip}>.
    if "k={tip}" in s:
        used |= set(re.findall(r"\[\s*'[^'\n]+',[^\[\]\n]*?,\s*'([a-z_0-9]+)'\s*\]", s))
missing = sorted(k for k in used if k not in G)
ok(len(used) >= 20, f"found the tooltip keys in use ({len(used)})")
ok(not missing, "every tooltip key has a definition", f"{missing}")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
