# Step 4 — UI / user testing

2026-09-09. Public surface of https://quant-india.vercel.app, plus verification
of the claims that surface makes. No production data written; V1.4 untouched.

## Scope, and what is NOT covered

The app requires sign-in for everything past the landing page. **Creating an
account or entering credentials is not something I will do**, so the
authenticated experience — Stock Explorer, Portfolio Lab, watchlist, alerts,
simulator — is **untested here and needs a human**. `/stocks` redirects to the
landing page when unauthenticated.

What that leaves is still worth doing, because the landing page is the app's
most-read surface and it makes hard numerical claims. Step 3's discipline
applies unchanged: check whether the app says things the evidence supports.

## Runtime health — clean

| check | result |
|---|---|
| console errors | **none** |
| network requests | all 200; no failures |
| mobile 375x812 | **no horizontal overflow** (scrollWidth == clientWidth == 375) |
| mobile layout | intact; controls reachable |

## The claims, checked one by one

### "168,389 test assertions passing" — nearly true, and reproducible

`VALIDATION.md` invites the reader to re-run three commands, and states the
suite is deterministic: "repeated runs produce an identical check count and
result, which is what makes the numbers above checkable rather than asserted."

Measured:

| suite | assertions | failures |
|---|---|---|
| `test_core_properties.py` | **81,215** | 0 |
| `test_new_algorithms_stress.py` | **87,173** | 0 |
| subtotal | **168,388** | 0 |
| `test_modules_integration.py` | see below | **FAILED** |

**Determinism holds** for the two that complete: `test_core_properties.py`
returned 81,215 on three independent runs.

The landing page's 168,389 is one more than the two suites produce; the third
suite supplies the remainder, so the figure is honest in origin. Very few
products publish a number a reader can reproduce to four significant figures.

### "…passing" — false, and the reason matters

**`test_modules_integration.py` fails**, with five `alpha_combine_wrong`
assertions. `VALIDATION.md` presents all three as currently passing.

The cause is **a regression I introduced earlier in this project.**
`compute_alpha_score` memoises per ticker (`_SCORE_CACHE`, 512 entries, 15-min
TTL). That cache is correct in production — factors do not change for a ticker
within fifteen minutes. It is fatal to this test, which patches the four factor
functions and calls `compute_alpha_score("Z.NS")` 41 times expecting 41
different answers:

    patched factors=-1.00  ->  alpha_score=-100.0  expected=-100.0
    patched factors=+0.00  ->  alpha_score=-100.0  expected=  +0.0
    patched factors=+0.50  ->  alpha_score=-100.0  expected= +50.0
    patched factors=+1.00  ->  alpha_score=-100.0  expected=+100.0

The first iteration's answer is returned for all 41.

**The model is fine.** With `_SCORE_CACHE.clear()` between iterations: 41
checks, **0 failures**. The combination logic, the weights and the scaling are
all correct.

**The test was the casualty, and worse than failing — it had stopped testing.**
Forty of forty-one iterations asserted nothing while still counting themselves.
A test that reports a number rather than a result is precisely the failure this
project exists to catch, and it survived because nobody ran the third command.

Fixed by clearing the cache in the test, with the reason written at the call
site. Production is unchanged.

### "all network calls are monkeypatched, so the suite is deterministic" — false

The integration suite contains **no patching at all**. The single grep hit is a
print label reading "patched factors". Its run log is full of live calls:

    HTTP Error 404: Quote not found for symbol: B0.NS
    HTTP Error 404: Quote not found for symbol: B1.NS

Those are synthetic test tickers being looked up against **Yahoo, over the
network**. Consequences:

- The suite takes **over fifteen minutes**, and it is not imports: all 90
  modules import in **9.2 seconds** total, of which `sentiment` is 7.5.
- It is **not deterministic** and **not offline-safe**. Results depend on
  Yahoo's availability and rate limiting.

A reader following `VALIDATION.md` would run command three and sit watching
404s scroll past.

### "2,401 NSE stocks scored daily" — wrong

[Landing.jsx:69](../frontend/src/pages/Landing.jsx) hardcodes this; it is not
fetched, so it cannot self-correct. Production's last cycle (2026-09-09):

    2,895 attempted · 2,704 scored · 188 failed

The true figure is **2,704**. More important than the 303 understatement:
**188 securities fail to score every day and the site says nothing about it.**
The same stale number is repeated in a comment at
[api.js:108](../frontend/src/api.js).

The hero line — "on **all** 2,400 NSE stocks" — is the stronger overclaim. With
188 daily failures it is not "all", and "all" is the word doing the work.

### Claims that hold

- **"4 factors per alpha score"** — confirmed: momentum, quality, sentiment,
  value, all present in the 2026-09-09 cycle.
- **Black-Scholes "10.4506 versus 10.45"** — verified exactly. S=100, K=100,
  T=1, r=5%, vol=20% returns **10.4506**.
- **"9 portfolio optimisers"** — 7 public entry points, but Markowitz exposes
  three objectives (max-Sharpe, min-variance, max-return), which totals 9.
  Loose, not false.
- **"Momentum backtested point-in-time: 23%/yr collapsed to 11.7%, t 3.78 to
  1.50"** — the app publishing a negative result about itself. Momentum is
  price-only, so a point-in-time claim is legitimate for it, consistent with
  Step 3's finding that only the price and corporate-action layer is PIT.
- **Footer "Data via NSE & NewsAPI"** — an attribution of source, not a claim
  of ongoing collection. Stored data genuinely is from NSE. Not misleading
  while collection is paused.

## Findings, by severity

1. **`VALIDATION.md` overstates.** Two of its three commands pass and reproduce
   their advertised counts exactly. The third fails and makes live network
   calls, contradicting both "currently passing" and "all network calls are
   monkeypatched".
2. **A validation test had stopped validating** for forty of forty-one cases,
   from a caching change I made. Fixed.
3. **"2,401 NSE stocks scored daily" is wrong** (2,704), and "all 2,400" is
   contradicted by 188 daily scoring failures. Both hardcoded.
4. **188 daily scoring failures are invisible** to users anywhere on the public
   site.

## Not done

- The entire authenticated experience.
- Accessibility, keyboard navigation, screen-reader behaviour.
- Cross-browser beyond the one engine tested.
- Any change to landing-page copy: the numbers above are reported for a
  decision, not edited unilaterally.
