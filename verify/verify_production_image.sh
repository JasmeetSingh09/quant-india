#!/bin/sh
# Runs INSIDE the verification image (verify/Dockerfile.production-2026-10-06), with the full
# repository checkout mounted read-only at /repo (the test suites read frontend/ and research/,
# which the image's backend-only copy does not contain).
#   docker run --rm -v "$PWD:/repo:ro" qi-verify sh /repo/verify/verify_production_image.sh
# Every check prints PASS or FAIL; the script exits non-zero if any fails. Its output is the report.
# Expected results are those of the code under test, commit d9b474a (see verify/README.md).
set -u
FAILS=0
step() { echo; echo "=== $1"; }
ok()   { echo "PASS: $1"; }
bad()  { echo "FAIL: $1"; FAILS=$((FAILS + 1)); }

step "1. Runtime"
python -c "import platform,sys; print(platform.python_version(), platform.machine(), sys.platform)"
[ "$(python -c 'import platform;print(platform.python_version())')" = "3.12.15" ] \
  && ok "Python 3.12.15" || bad "Python is not 3.12.15"

step "2. Installed packages equal the 2026-10-06 manifest (93), hashes enforced at build"
pip freeze > /tmp/freeze.txt
python - <<'EOF' && ok "pip freeze matches all 93 manifest packages" || bad "pip freeze differs from the manifest"
import json, re, sys
norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()
man = json.load(open("/repo/docs/audit/production_dependency_manifest_2026-10-06.json", encoding="utf-8"))["packages"]
got = {}
for line in open("/tmp/freeze.txt"):
    if "==" in line:
        n, v = line.strip().split("==", 1); got[norm(n)] = v
diff = {k: (v["version"], got.get(k)) for k, v in man.items() if got.get(k) != v["version"]}
extra = sorted(set(got) - set(man))
print("differences:", diff or "none", "| installed but not in manifest:", extra or "none")
sys.exit(1 if diff else 0)
EOF
pip check && ok "pip check: no broken requirements" || bad "pip check failed"

step "3. Full offline regression suite on the mounted checkout (expected: d9b474a's results)"
rm -rf /tmp/repo && cp -r /repo /tmp/repo && cd /tmp/repo/backend
python tests/run_ci.py > /tmp/ci.txt 2>&1; RC=$?
grep -E "\[FAIL\]|suites passed" /tmp/ci.txt | tail -6
[ $RC -eq 0 ] && ok "run_ci: all suites pass (67 expected)" || bad "run_ci exit $RC"
python tests/behavioural_fixtures.py > /tmp/fx.txt 2>&1 && grep -q "IDENTICAL" /tmp/fx.txt \
  && ok "339 behavioural snapshots identical" || { tail -5 /tmp/fx.txt; bad "behavioural snapshots"; }
python tests/four_factor_oracle_test.py > /tmp/oracle.txt 2>&1; grep -E "^passed|FAILED" /tmp/oracle.txt
grep -q "^passed 181, failed 7" /tmp/oracle.txt \
  && ok "oracle suite 181/7, exactly d9b474a's documented open defects" || bad "oracle suite result differs from d9b474a's"

step "4. FinBERT baseline (pinned revision, hub offline)"
HF_HUB_OFFLINE=1 python /repo/verify/finbert_baseline_check.py /repo/verify/finbert_baseline_2026-10-14.json \
  && ok "FinBERT reproduces the recorded baseline on Python 3.12, Linux, numpy 1.26.4" || bad "FinBERT baseline differs"

step "5. Startup and read-only endpoints (image code at /app)"
cd /app
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 > /tmp/server.txt 2>&1 &
PID=$!
UP=0
for i in $(seq 1 150); do
  curl -sf http://127.0.0.1:8000/ > /dev/null && { UP=1; break; }; sleep 2
done
[ $UP -eq 1 ] && ok "the app starts and answers / (as the HEALTHCHECK does)" || { tail -30 /tmp/server.txt; bad "the app did not start"; }
for path in /openapi.json /alpha/universe/status /stock/universe/stats; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000$path")
  [ "$code" = "200" ] && ok "GET $path -> 200" || bad "GET $path -> $code"
done
kill $PID 2>/dev/null

echo
echo "=== RESULT: $FAILS failure(s)"
exit $FAILS
