"""
finbert_pin_test.py — the sentiment model is pinned, the pin is the same everywhere,
and the spec records it (owner-approved 2026-10-14).

FinBERT was loaded as "ProsusAI/finbert" with no revision, so every Docker
build fetched whatever upstream main was; upstream changed on 2026-10-12. This
checks, without loading the model (CI is offline):
  - model_config pins an immutable 40-character revision;
  - sentiment.py loads that constant (read as source: importing it loads FinBERT);
  - the Dockerfile pre-downloads the same revision, so the image and the
    runtime cannot disagree;
  - current_spec() captures the model, revision and reading rules, and the
    environment block records the transformers / torch / tokenizers versions;
  - changing the revision moves the spec hash.
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "..", "modules")
sys.path.insert(0, MOD)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("QUANT_DATA_DIR", os.environ.get("TEMP", "/tmp"))
os.environ.pop("DATABASE_URL", None)

import model_config as MC       # noqa: E402
import strategy_version as SV   # noqa: E402

PASS, FAIL = [], []


def ok(cond, label, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


print("\n1. ONE IMMUTABLE PIN")
ok(MC.FINBERT_MODEL == "ProsusAI/finbert", "the model repository is named")
ok(bool(re.fullmatch(r"[0-9a-f]{40}", MC.FINBERT_REVISION)), "the revision is a full commit hash, not a branch",
   MC.FINBERT_REVISION)
ok(MC.FINBERT_REVISION == "4556d13015211d73dccd3fdd39d39232506f3e43",
   "it is the revision production was built on (main until 2026-10-12)")

print("\n2. EVERY LOADER USES IT")
src = open(os.path.join(MOD, "sentiment.py"), encoding="utf-8").read()
tree = ast.parse(src)
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
         and getattr(n.func, "id", getattr(n.func, "attr", "")) == "hf_pipeline"]
kw = {k.arg: k.value for k in calls[0].keywords} if calls else {}
ok(len(calls) == 1, "sentiment.py builds exactly one pipeline")
ok(isinstance(kw.get("model"), ast.Name) and kw["model"].id == "FINBERT_MODEL", "it loads FINBERT_MODEL")
ok(isinstance(kw.get("revision"), ast.Name) and kw["revision"].id == "FINBERT_REVISION", "it passes FINBERT_REVISION")
ok("text[:512]" not in src and "t[:512]" not in src and src.count("FINBERT_MAX_CHARS") >= 3,
   "the character cut is the named constant, not a literal")
docker = open(os.path.join(HERE, "..", "Dockerfile"), encoding="utf-8").read()
ok(f"revision='{MC.FINBERT_REVISION}'" in docker and f"model='{MC.FINBERT_MODEL}'" in docker,
   "the Dockerfile pre-downloads the same model and revision")

print("\n3. THE SPEC RECORDS IT")
spec = SV.current_spec()
sm = spec.get("sentiment_model") or {}
ok(sm.get("repo") == MC.FINBERT_MODEL and sm.get("revision") == MC.FINBERT_REVISION
   and sm.get("max_chars") == MC.FINBERT_MAX_CHARS, "sentiment_model holds repo, revision and character cut",
   (spec.get("_capture_failures") or {}).get("sentiment_model", ""))
ok(sm.get("label_rule") and sm.get("failure_policy"), "the reading rule and the failure policy are written down")
env = SV._environment()
ok(all(f"{lib}_version" in env for lib in ("transformers", "torch", "tokenizers")),
   "the environment records transformers, torch and tokenizers versions",
   {k: env.get(k) for k in ("transformers_version", "torch_version", "tokenizers_version")})
base = SV._hash(spec)
real = MC.FINBERT_REVISION
try:
    MC.FINBERT_REVISION = "0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031"
    ok(SV._hash(SV.current_spec()) != base, "a different revision moves the spec hash")
finally:
    MC.FINBERT_REVISION = real
ok(SV._hash(SV.current_spec()) == base, "restored, the hash returns")

print("\n" + "=" * 60)
print(f"passed {len(PASS)}, failed {len(FAIL)}")
for x in FAIL:
    print(f"  FAILED: {x}")
sys.exit(1 if FAIL else 0)
