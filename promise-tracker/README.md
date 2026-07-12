# Promise Tracker (Wave 1)

Tracks the promises Indian company management makes on earnings calls and grades
whether they were kept. See [CLAUDE.md](CLAUDE.md) for the full spec and the
positioning decisions.

## Status

- [x] **Step 1** — scaffold + `companies.json` (20 Wave 1 companies)
- [ ] **Step 2** — `pipeline.py`: extract / verify / render (+ backfill / monitor)
- [ ] **Step 3** — `site/index.html` dashboard
- [ ] **Step 4** — end-to-end on first transcript; tighten prompt to ≥95% pass rate

## Setup

```bash
cd promise-tracker
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...                      # set your key (never commit it)
```

## Companies

20 names: 10 large-cap, 10 mid-cap. Defined in `companies.json`.

> ⚠️ `bse_code` values are best-known and **must be verified against BSE** before
> wiring up the automated announcement fetcher. NSE symbols are current as of
> the scaffold (note: Zomato now trades as **ETERNAL**).

## Layout

`companies.json` is static config. `data/coverage_state.json` holds mutable
ingestion state (backfill progress + coverage-gap flags), written by the pipeline.
Source PDFs live in `data/transcripts/<TICKER>/`; extracted JSON in
`data/promises/`; rendered Markdown in `data/output/`.
