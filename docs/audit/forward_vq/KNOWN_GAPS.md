# Forward tests: known gaps in the nightly record

Nights with no stored cycle, and why. A gap is recorded here, never backfilled: the forward
tests rely on data captured on the night itself, so a cycle rebuilt later would not be the same
evidence. Each monthly seal (`research/sealed_export.py`) shows the same gaps as missing cycles.

## 2026-10-30 to 2026-11-11: hosting suspended (13 cycles)

- **Cause:** Render suspended the backend for an unpaid invoice (September, due 2026-10-01) at
  2026-10-29 08:13 UTC. The owner paid and Render resumed the service at 2026-11-11 07:16 UTC.
- **Last complete cycle before:** 2026-10-29 (2,510 rows in factor_history, written before the
  suspension).
- **Missing cycles:** 2026-10-30, 10-31, 11-01 ... 11-11 (13 nights). The 11-11 cycle was due at
  about 00:02 UTC, before the resume.
- **First cycle after:** expected 2026-11-12. Confirm it in factor_history before relying on it.
- **Detection:** the nightly production check failed every run from 2026-10-29 to 2026-11-10,
  and its emails reached the owner, but a failure email looks the same whatever the cause, so
  an outage read like the routine data warnings.
- **Effect on the tests:** these nights carry no observations, and nothing is interpolated.
  Formation dates and holding periods that touch these nights still need checking against each
  pre-registration's missing-data rule before any result is computed.
