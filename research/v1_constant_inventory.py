"""
v1_constant_inventory.py — every numeric literal inside V1's quality, value and
sentiment functions, with its line and the source text around it.

Audit scope expansion approved 2026-10-14: version_provenance_audit's literal
scan (CRITICAL_FUNCS) covers only momentum, the composite and V2, so these
three functions' numbers are not protected by the frozen spec hash. This lists
them so each can be classified as a model parameter or an implementation
literal before anything is promoted. It reads source only; it changes nothing.

Run:  python research/v1_constant_inventory.py [--json out.json]
"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "backend", "modules")
TARGETS = {
    "alpha_model.py": ["_compute_sentiment_factor", "_compute_quality_factor",
                       "_compute_value_factor", "_interest_coverage"],
    "metrics.py": ["piotroski_score"],
    "data_fetcher.py": ["get_sector_peers"],
}


def literals(path, funcs):
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines()
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in funcs:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, (int, float)) \
                        and not isinstance(sub.value, bool):
                    text = lines[sub.lineno - 1].strip()
                    # Negative literals parse as UnaryOp(USub, Constant).
                    out.append({"file": os.path.basename(path), "function": node.name,
                                "line": sub.lineno, "value": sub.value, "source": text[:140]})
    return sorted(out, key=lambda r: (r["file"], r["line"], r["value"]))


rows = []
for f, funcs in TARGETS.items():
    rows += literals(os.path.join(SRC, f), funcs)

for r in rows:
    print(f"{r['file']:16s} {r['function']:28s} L{r['line']:<5d} {r['value']!r:>8}   {r['source']}")
print(f"\n{len(rows)} numeric literals in {sum(len(v) for v in TARGETS.values())} functions")
if "--json" in sys.argv:
    json.dump(rows, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
