# What the CI gate runs, and what it leaves out

`python tests/run_ci.py` is the gate. `.github/workflows/ci.yml` runs it on
every push, after `run_ci_selftest.py` proves the gate can still fail.

A suite is in the gate only if it passes **in a clean checkout, with the network
blocked, in its own temp and data directories**. Its floor is the check count it
reported under those conditions on 2026-09-11. The list and floors live in
`SUITES` at the top of `run_ci.py`.

A suite fails the gate if it exits non-zero, runs past its time limit, prints a
failure count above zero, prints fewer checks than its floor (or no count), or
tries to reach the network. The network block covers Python sockets, DNS, and
`curl_cffi`, the C library yfinance downloads through.

## In the gate: 43 suites

Everything in `SUITES`. The two large property suites (81,215 and 87,173 checks)
plus 41 focused suites, 169,817 checks in all.

`bhavcopy_history_test.py` joined on 2026-09-11. It used to download a real
2015 file from NSE on every run; it now parses a sample in the 2015 layout, and
only `NSE_LIVE_TEST=1` makes it fetch from NSE. The sample catches a parser
change that breaks the 2015 columns; it cannot show that NSE still serves that
layout, which only the live run can.

## Not in the gate

### They reach the network

Each was run with the network blocked. Passing online is not the same as being
offline, and a slow day at Yahoo must not block a deploy.

| File | What happens offline |
|---|---|
| `test_modules_integration.py` | Passes (1,613) but makes two network calls |
| `bad_input_test.py` | Passes (29) but makes a network call |
| `sanity_test.py` | 23 checks offline, 24 online |
| `stress_new_modules.py` | Stops early; needs live prices (554–559 checks online) |
| `leak_test.py` | Result changes (online CLEAN=5 KNOWN=4; offline CLEAN=2 KNOWN=3) |
| `consistency_test.py` | Compares live quotes; offline it reports a false BUG |
| `verify_claims.py` | Exits 1 offline |
| `optimizer_audit.py` | Fetches returns |
| `data_failure_audit.py`, `factor_audit.py`, `full_audit.py`, `independent_recompute.py`, `stock_matrix_audit.py`, `test_alpha_audit.py` | Audits over live data |
| `momentum_scrutiny.py`, `study_distress_flags.py` | Studies over live data; print no count |

### Not tests

- `audit_record.py`: a command-line helper that needs arguments.
- `behavioural_fixtures.py`: fixtures imported by other suites.
- `production_e2e.py`: tests the live site.
- `nightly_production_check.py`: checks production after each night's scan.
  `.github/workflows/nightly.yml` runs it at 03:30 UTC. Its judging logic is
  tested offline by `nightly_production_check_test.py`, which is in the gate.

### Needs the local price archive

`version_provenance_audit.py` passes in a working copy (31 checks, 0 gaps) but
not in a clean checkout: its environment record reads the local price archive,
which a checkout does not have, and reports `archive: None` as a gap. Its
constant inventory is the part a CI run would most want, so this is worth
splitting out; it has not been yet.

## Found by the gate on its first clean-checkout run

- `data_integrity_test.py` passed only on a laptop whose database held the NSE
  equity list: company names were read from it through `stock_universe`, which
  the suite's `db` stub did not reach. 8 checks failed in a clean checkout. The
  suite now supplies the names itself.
- A new SQLite database never got `simulations.cash`, so the first deposit
  raised. `simulator_fresh_db_test.py` covers it. Production (Postgres) was
  not affected.
- `universe_scan.UNSCOREABLE_ATTEMPTS` and `UNSCOREABLE_RECHECK_DAYS` were added
  without being registered in the provenance inventory, so the specification
  audit reported itself incomplete.
- The first network block missed yfinance entirely: it downloads through
  `curl_cffi`, which never calls Python's socket module.

## Adding a suite

Run it in a clean checkout with the network blocked (`run_ci.py --manifest`
with a one-line JSON list does this). If it passes, add it to `SUITES` with the
count it printed as its floor. Raising a floor needs no reason; lowering one
means accepting that fewer things are checked, so say why in the commit.
