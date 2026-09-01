"""
shadowed_import_test.py — a local import that breaks the lines above it.

The universe scan was dead for nine days because of this:

    import threading                    # module level, line 25

    def _scan_loop():
        clock = threading.Lock()        # line 426  -> UnboundLocalError
        ...
        import threading                # line 504

An `import X` anywhere in a function makes X a LOCAL name for the WHOLE
function, including every line above it. So a redundant import near the bottom
silently broke a use near the top, the thread died on its first statement, and
from outside it looked like a scan that had started and was working.

Nothing about this is exotic and nothing catches it: the module imports cleanly,
the function parses, and only running that exact line reveals it. So it gets a
test.

Two findings, with different force:

  BROKEN   the name is used earlier in the function than the local import.
           This raises at runtime, every time. It is a bug, not a style note.

  RISKY    the module already imports the name at the top and a function
           imports it again. It is not broken today, and it becomes broken the
           moment someone uses the name earlier in that function.
"""

import ast
import os
import sys

MODDIR = os.path.join(os.path.dirname(__file__), "..", "modules")

PASS, FAIL = [], []


def ok(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}")


def bound_names(node):
    """Names an import statement binds into its scope."""
    out = []
    for a in node.names:
        if a.asname:
            out.append(a.asname)
        elif isinstance(node, ast.Import):
            out.append(a.name.split(".")[0])
        else:
            out.append(a.name)
    return [n for n in out if n != "*"]


def scan_source(src, path="<src>"):
    tree = ast.parse(src)

    module_imports = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            module_imports.update(bound_names(n))

    broken, risky = [], []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Local imports directly inside THIS function, not inside a nested one.
        nested = {n for f in ast.walk(fn)
                  if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f is not fn
                  for n in ast.walk(f)}
        locals_ = {}
        for n in ast.walk(fn):
            if n in nested:
                continue
            if isinstance(n, (ast.Import, ast.ImportFrom)) and n is not fn:
                for name in bound_names(n):
                    # The EARLIEST local import of the name, not whichever one
                    # ast.walk happens to reach first — it walks breadth-first,
                    # so a second import in a later block can be seen before the
                    # first. Recording that one flagged a correct function that
                    # imports scipy in two branches, using the second import's
                    # line to judge a use that sits safely after the first.
                    prev = locals_.get(name)
                    locals_[name] = n.lineno if prev is None else min(prev, n.lineno)

        if not locals_:
            continue
        for n in ast.walk(fn):
            if n in nested:
                continue
            if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                    and n.id in locals_ and n.lineno < locals_[n.id]):
                broken.append({"function": fn.name, "name": n.id,
                               "used_at": n.lineno,
                               "imported_at": locals_[n.id], "path": path})
        for name, line in locals_.items():
            if name in module_imports:
                risky.append({"function": fn.name, "name": name,
                              "local_import_at": line, "path": path})
    return broken, risky


print("\n1. The checker finds the bug it was written for")
FIXTURE = """
import threading

def loop():
    clock = threading.Lock()
    try:
        import threading
    except Exception:
        pass
"""
b, r = scan_source(FIXTURE, "fixture")
ok(len(b) == 1 and b[0]["name"] == "threading",
   f"detects a name used above its own local import ({b})")
ok(len(r) == 1, "and flags the redundant local import as risky")

print("\n2. It does not cry wolf")
CLEAN = """
import os

def fine():
    import json
    return json.dumps({"a": os.sep})

def also_fine():
    from math import pi
    return pi

def nested_is_not_confused():
    def inner():
        import csv
        return csv
    return inner
"""
b2, r2 = scan_source(CLEAN, "clean")
ok(not b2, f"no false positives on correct local imports ({b2})")
ok(not r2, f"and none flagged risky ({r2})")

LATER_USE = """
def fine():
    import json
    return json.dumps({})
"""
b3, _ = scan_source(LATER_USE, "later")
ok(not b3, "a name used AFTER its local import is fine")

TWICE = """
def two_branches(t):
    if t:
        from scipy import stats as _st
        a = _st.t.sf(t)
    else:
        a = 0
    try:
        from scipy import stats as _st
        b = _st.t.ppf(0.975)
    except Exception:
        b = 1.96
    return a, b
"""
b4, _ = scan_source(TWICE, "twice")
ok(not b4,
   f"two local imports of one name: the EARLIEST is what a use is judged "
   f"against ({b4})")

print("\n3. The real codebase")
all_broken, all_risky = [], []
for f in sorted(os.listdir(MODDIR)):
    if not f.endswith(".py"):
        continue
    try:
        src = open(os.path.join(MODDIR, f), encoding="utf-8").read()
    except Exception:
        continue
    try:
        b, r = scan_source(src, f)
    except SyntaxError:
        continue
    all_broken += b
    all_risky += r

for x in all_broken:
    print(f"         BROKEN {x['path']}:{x['used_at']} {x['function']}() uses "
          f"'{x['name']}' before its local import at line {x['imported_at']}")
ok(not all_broken,
   f"no function uses a name above its own local import ({len(all_broken)} found)")

print(f"\n  {len(all_risky)} redundant local import(s) of a module-level name:")
for x in all_risky[:12]:
    print(f"    {x['path']}:{x['local_import_at']} {x['function']}() re-imports "
          f"'{x['name']}'")
if len(all_risky) > 12:
    print(f"    ... and {len(all_risky) - 12} more")
# Reported, not failed: these are not broken today. The one that WAS broken is
# what the check above is for.
print("  (reported, not failed — none of these is broken as written)")

print("\n" + "=" * 68)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
