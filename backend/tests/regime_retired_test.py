"""
regime_retired_test.py — the failed regime models stay retired (2026-10-05).

The Bull/Bear HMM failed its pre-registered test (labels follow single days) and a
Markov-switching replacement was not shipped. This guards that nothing re-weights the
model by those labels, that no trading advice is attached to them, and that the
frontend no longer calls them. Offline: reads source files only.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


main = read("backend", "main.py")
tree = ast.parse(main)
routes = {}
for f in tree.body:
    if isinstance(f, ast.FunctionDef):
        for d in f.decorator_list:
            if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "get" and d.args:
                routes[d.args[0].value] = f


def raises_410(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
            for kw in n.exc.keywords:
                if kw.arg == "status_code" and getattr(kw.value, "value", None) == 410:
                    return True
    return False


print("\n1. The routes that re-weighted factors by a failed label are retired")
for path in ("/regime/weights", "/alpha/regime-adjusted"):
    ok(path in routes and raises_410(routes[path]), f"{path} answers 410 Gone")
ok("regime_conditioned_alpha" not in main, "main.py no longer calls the regime-adjusted alpha")
ok("/market-risk" in main and "REGIME_RETIRED" in main, "the retirement message points to /market-risk")

print("\n2. No trading advice rides on the failed label")
det = read("backend", "modules", "regime_detector.py")
for phrase in ("Increase position sizes", "Weight quality and sentiment signals more heavily",
               "Range-trading and mean-reversion strategies work better"):
    ok(phrase not in det, f"advice removed: '{phrase[:40]}'")
ok("research record only" in det.lower(), "the detector's output says it is a research record only")

print("\n3. The frontend no longer calls the old regime routes")
api = read("frontend", "src", "api.js")
ok("/regime/weights" not in api and "regime-adjusted" not in api and "api.get('/regime')" not in api,
   "api.js has no old regime calls")
ok(not os.path.exists(os.path.join(ROOT, "frontend", "src", "components", "RegimeBadge.jsx")),
   "the unused RegimeBadge component is gone")
dash = read("frontend", "src", "pages", "Dashboard.jsx")
ok("Market regime" in dash and "Markov-switching" in dash, "the Dashboard's regime card is the tested market-risk reading")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
