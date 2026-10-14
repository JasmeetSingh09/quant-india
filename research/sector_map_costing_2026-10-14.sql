-- sector_map_costing_2026-10-14.sql — the read-only queries behind
-- docs/PROPOSAL_V161_SECTOR_MAP_2026-10-14.md. Run against production Supabase
-- (SELECT only). Cycle 2026-10-14. The value formula is the methodology's
-- (docs/PHASE0_V1_METHODOLOGY_2026-09-14.md):
--   z = (x - peer mean) / max(peer pop. std, floor)   floors 1 (P/E), 0.5 (P/B)
--   fewer than 2 peers with the multiple -> 22 +/- 8 (P/E), 3.2 +/- 1.5 (P/B)
--   a missing own multiple sits at the mean; value = tanh((-0.6 zPE - 0.4 zPB)/2)
--   alpha after = stored alpha + 15 x (value after - value before)
--
-- Peer multiples. "Before" uses each stock's OWN stored peer rows, which
-- reproduces every stored value exactly (KEYFINSERV included: the earlier 0.008
-- gap came from reading a peer's multiples off another stock's rows; DLF,
-- GODREJPROP and OBEROIRLTY were each read with two P/Es during the night).
-- "After" uses each new peer's own stored multiples (factor_inputs), where a
-- non-positive multiple had already been dropped; the live code reads peers
-- raw (audit D-06), so a peer with a negative P/B would differ.

-- 1. Exact reconciliation, one stock from its own peer rows.
WITH own AS (SELECT max(value_num) FILTER (WHERE input_name='pe_ratio') pe,
                    max(value_num) FILTER (WHERE input_name='pb_ratio') pb
             FROM factor_inputs WHERE cycle_id='2026-10-14' AND factor='value' AND ticker='KEYFINSERV.NS'),
p AS (SELECT count(*) FILTER (WHERE peer_pe IS NOT NULL AND peer_pe<>0) npe, avg(peer_pe) FILTER (WHERE peer_pe<>0) mpe,
             stddev_pop(peer_pe) FILTER (WHERE peer_pe<>0) spe,
             count(*) FILTER (WHERE peer_pb IS NOT NULL AND peer_pb<>0) npb, avg(peer_pb) FILTER (WHERE peer_pb<>0) mpb,
             stddev_pop(peer_pb) FILTER (WHERE peer_pb<>0) spb
      FROM factor_input_peers WHERE cycle_id='2026-10-14' AND ticker='KEYFINSERV.NS')
SELECT round(tanh((-0.6*((coalesce(own.pe, CASE WHEN npe<2 THEN 22 ELSE mpe END) - CASE WHEN npe<2 THEN 22 ELSE mpe END)
                         / CASE WHEN npe<2 THEN 8 ELSE greatest(spe,1) END)
                   -0.4*((coalesce(own.pb, CASE WHEN npb<2 THEN 3.2 ELSE mpb END) - CASE WHEN npb<2 THEN 3.2 ELSE mpb END)
                         / CASE WHEN npb<2 THEN 1.5 ELSE greatest(spb,0.5) END))/2)::numeric, 4) AS recomputed  -- 0.8700
FROM own, p;

-- 2. Who every scored stock is valued against today (peer-set census).
WITH p AS (SELECT ticker, string_agg(replace(peer_ticker,'.NS',''), ',' ORDER BY peer_ticker) peers
           FROM factor_input_peers WHERE cycle_id='2026-10-14' GROUP BY ticker)
SELECT coalesce(p.peers,'(no peers: market averages)') peers, count(*) n
FROM alpha_scan2 a LEFT JOIN p ON p.ticker=a.ticker
WHERE a.cycle='2026-10-14' AND a.error IS NULL GROUP BY 1 ORDER BY 2 DESC;

-- 3. A sector re-costed: members ordered by stored market cap, each member's
--    peers = the first 3 OTHER members (the code's rule). Members below are
--    the 49 scored stocks Yahoo labels industry = "Capital Markets"
--    (docs/audit/capital_markets_candidates_yahoo_2026-10-14.json).
WITH mem(t) AS (SELECT unnest(ARRAY['5PAISA','AFSL','AIIL','AKCAPIT','ALGOQUANT','ALMONDZ','ANGELONE','APOORVA',
  'ARIHANTCAP','ARYAMAN','AVONMORE','CDSL','CONSOFINVT','DAMCAPITAL','DBSTOCKBRO','DHUNINV','EMKAY','GEOJITFSL',
  'GROWW','HBPOR','HBSL','HYBRIDFIN','IEX','IIFLCAPS','INDOTHAI','INVENTURE','JMFINANCIL','KEYFINSERV','KHANDSE',
  'KJMCFIN','MASKINVEST','MASTERTR','MONARCH','MOTILALOFS','MUKESHB','NAHARCAP','ONELIFECAP','PIONRINV',
  'PRIMESECU','SGFIN','SHARDUL','SHAREINDIA','SMCGLOBAL','STEELCITY','SUMMITSEC','THEINVEST','VGCL','WEALTH',
  'WELINV']) || '.NS'),
ranked AS (SELECT m.t, a.alpha_score, a.signal, a.value,
                  row_number() OVER (ORDER BY a.market_cap DESC NULLS LAST, m.t) rk
           FROM mem m JOIN alpha_scan2 a ON a.ticker=m.t AND a.cycle='2026-10-14' AND a.error IS NULL),
own AS (SELECT ticker, max(value_num) FILTER (WHERE input_name='pe_ratio') pe,
               max(value_num) FILTER (WHERE input_name='pb_ratio') pb,
               max(value_num) FILTER (WHERE input_name='legs_used') legs
        FROM factor_inputs WHERE cycle_id='2026-10-14' AND factor='value' GROUP BY ticker),
ap AS (SELECT r.t, p.t peer FROM ranked r
       JOIN LATERAL (SELECT r2.t FROM ranked r2 WHERE r2.t<>r.t ORDER BY r2.rk LIMIT 3) p ON true),
st AS (SELECT ap.t,
         count(*) FILTER (WHERE o.pe IS NOT NULL AND o.pe<>0) npe, avg(o.pe) FILTER (WHERE o.pe<>0) mpe,
         stddev_pop(o.pe) FILTER (WHERE o.pe<>0) spe,
         count(*) FILTER (WHERE o.pb IS NOT NULL AND o.pb<>0) npb, avg(o.pb) FILTER (WHERE o.pb<>0) mpb,
         stddev_pop(o.pb) FILTER (WHERE o.pb<>0) spb
       FROM ap LEFT JOIN own o ON o.ticker=ap.peer GROUP BY ap.t),
c AS (SELECT r.*, o.pe, o.pb, o.legs,
        CASE WHEN st.npe<2 THEN 22.0 ELSE st.mpe END me, CASE WHEN st.npe<2 THEN 8.0 ELSE greatest(st.spe,1) END se,
        CASE WHEN st.npb<2 THEN 3.2 ELSE st.mpb END mb, CASE WHEN st.npb<2 THEN 1.5 ELSE greatest(st.spb,0.5) END sb
      FROM ranked r JOIN st ON st.t=r.t LEFT JOIN own o ON o.ticker=r.t)
SELECT t, rk, signal, alpha_score, round(value::numeric,4) value_today,
       round((CASE WHEN legs=0 THEN -0.5 WHEN legs IS NULL THEN 0
                   ELSE tanh((-0.6*((coalesce(pe,me)-me)/se) - 0.4*((coalesce(pb,mb)-mb)/sb))/2) END)::numeric,4) value_after,
       round((alpha_score + 15*((CASE WHEN legs=0 THEN -0.5 WHEN legs IS NULL THEN 0
                   ELSE tanh((-0.6*((coalesce(pe,me)-me)/se) - 0.4*((coalesce(pb,mb)-mb)/sb))/2) END) - value))::numeric,2) alpha_after
FROM c ORDER BY rk;

-- Options A and B of the proposal use the same calculation with explicit peer
-- lists per stock (see the proposal's tables); replace `ap` with a VALUES list
-- of (ticker, peer) pairs to reproduce them.
