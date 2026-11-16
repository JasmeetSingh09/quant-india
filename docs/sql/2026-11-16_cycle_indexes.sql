-- Proposed 2026-11-16, NOT applied: indexes so per-cycle reads stop scanning whole tables.
--
-- Why: /scan/cycle-audit times out. Each table below is keyed (ticker, cycle_id, ...), so a
-- query "WHERE cycle_id = ?" cannot use the key: the column it filters on is second. Measured
-- on production 2026-11-16:
--     SELECT COUNT(*) FROM factor_inputs WHERE cycle_id = '2026-11-11'
--     -> 63.6 s, 61,076 pages read from disk, to count 62,835 rows.
-- The audit runs this kind of query on factor_inputs (three times), factor_input_articles,
-- factor_input_peers, factor_history and alpha_scan2, so it needs several minutes and times out.
--
-- What this changes: only how fast those reads are. No data, no column and no result changes.
-- CONCURRENTLY builds each index without blocking the nightly scan's writes. Run each statement
-- on its own (CONCURRENTLY cannot run inside a transaction), outside 00:02-03:30 UTC.
-- Approximate extra disk: under 200 MB in total.
--
-- Undo: DROP INDEX CONCURRENTLY <name>;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_factor_inputs_cycle    ON factor_inputs (cycle_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_factor_articles_cycle  ON factor_input_articles (cycle_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_factor_peers_cycle     ON factor_input_peers (cycle_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_factor_history_cycle   ON factor_history (cycle_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alpha_scan2_cycle      ON alpha_scan2 (cycle);

-- Check afterwards (should be well under a second):
-- EXPLAIN ANALYZE SELECT COUNT(*) FROM factor_inputs WHERE cycle_id = '2026-11-11';
