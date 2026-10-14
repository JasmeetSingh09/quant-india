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

-- 4. Census by peer source (decision document, section 2). The IN list is
--    every ticker in data_fetcher.NSE_SECTORS at commit 65c3fc9.
WITH grp(sector, first3, yahoo) AS (VALUES ('Banking','HDFCBANK,ICICIBANK,SBIN','Financial Services'),('NBFC','BAJAJFINSV,BAJFINANCE,MUTHOOTFIN',''),('IT','INFY,TCS,WIPRO','Technology'),('Oil_Gas','BPCL,ONGC,RELIANCE','Energy'),('Pharma','CIPLA,DRREDDY,SUNPHARMA','Healthcare'),('Auto','M&M,MARUTI,TMPV','Consumer Cyclical'),('FMCG','HINDUNILVR,ITC,NESTLEIND','Consumer Defensive'),('Cement','ACC,AMBUJACEM,ULTRACEMCO',''),('Steel_Metal','JSWSTEEL,SAIL,TATASTEEL','Basic Materials'),('Telecom','BHARTIARTL,IDEA,TATACOMM','Communication Services'),('Real_Estate','DLF,GODREJPROP,OBEROIRLTY','Real Estate'),('Power','NTPC,POWERGRID,TATAPOWER','Utilities'),('Capital_Goods','BHEL,LT,SIEMENS','Industrials')),
p AS (SELECT ticker, string_agg(replace(peer_ticker,'.NS',''), ',' ORDER BY peer_ticker) peers FROM factor_input_peers WHERE cycle_id='2026-10-14' GROUP BY ticker),
s AS (SELECT a.ticker, a.ticker IN ('AARTIIND.NS','ABB.NS','ABBOTINDIA.NS','ABFRL.NS','ACC.NS','ADANIENT.NS','ADANIGREEN.NS','ADANIPORTS.NS','ADANIPOWER.NS','AEGISLOG.NS','AIAENG.NS','AJANTPHARM.NS','ALKEM.NS','ALKYLAMINE.NS','AMBUJACEM.NS','APOLLOHOSP.NS','APOLLOTYRE.NS','ARE&M.NS','ASHOKLEY.NS','ASIANPAINT.NS','AUBANK.NS','AUROPHARMA.NS','AXISBANK.NS','BAJAJ-AUTO.NS','BAJAJCON.NS','BAJAJELEC.NS','BAJAJFINSV.NS','BAJAJHLDNG.NS','BAJFINANCE.NS','BALKRISIND.NS','BANDHANBNK.NS','BANKBARODA.NS','BANKINDIA.NS','BATAINDIA.NS','BERGEPAINT.NS','BHARATFORG.NS','BHARTIARTL.NS','BHEL.NS','BIOCON.NS','BIRLACORPN.NS','BLUESTARCO.NS','BOSCHLTD.NS','BPCL.NS','BRIGADE.NS','BRITANNIA.NS','CANBK.NS','CANFINHOME.NS','CASTROLIND.NS','CEATLTD.NS','CESC.NS','CGPOWER.NS','CHOLAFIN.NS','CIPLA.NS','CLEAN.NS','COALINDIA.NS','COFORGE.NS','COLPAL.NS','CROMPTON.NS','CYIENT.NS','DABUR.NS','DALBHARAT.NS','DCBBANK.NS','DEEPAKNTR.NS','DEVYANI.NS','DIVISLAB.NS','DLF.NS','DMART.NS','DRREDDY.NS','EDELWEISS.NS','EICHERMOT.NS','EMAMILTD.NS','ERIS.NS','ESCORTS.NS','ETERNAL.NS','EXIDEIND.NS','FEDERALBNK.NS','GAIL.NS','GALAXYSURF.NS','GICRE.NS','GLAXO.NS','GLENMARK.NS','GODREJCP.NS','GODREJIND.NS','GODREJPROP.NS','GPPL.NS','GRANULES.NS','GRINDWELL.NS','GUJGASLTD.NS','GULFOILLUB.NS','HAPPSTMNDS.NS','HATSUN.NS','HAVELLS.NS','HCLTECH.NS','HDFCBANK.NS','HDFCLIFE.NS','HEIDELBERG.NS','HEROMOTOCO.NS','HEXT.NS','HFCL.NS','HINDALCO.NS','HINDPETRO.NS','HINDUNILVR.NS','HUDCO.NS','ICICIBANK.NS','ICICIGI.NS','ICICIPRULI.NS','IDEA.NS','IDFCFIRSTB.NS','IGL.NS','INDIAMART.NS','INDIGO.NS','INDUSINDBK.NS','INFY.NS','IOC.NS','IPCALAB.NS','IRB.NS','IRFC.NS','ITC.NS','JBCHEPHARM.NS','JKCEMENT.NS','JSWENERGY.NS','JSWHL.NS','JSWSTEEL.NS','JUBLFOOD.NS','KALYANKJIL.NS','KANSAINER.NS','KARURVYSYA.NS','KEYFINSERV.NS','KNRCON.NS','KOTAKBANK.NS','KPITTECH.NS','LAURUSLABS.NS','LICHSGFIN.NS','LICI.NS','LT.NS','LTF.NS','LTTS.NS','LUPIN.NS','M&M.NS','MAHLIFE.NS','MANAPPURAM.NS','MANYAVAR.NS','MARICO.NS','MARUTI.NS','MASTEK.NS','MGL.NS','MOIL.NS','MOTHERSON.NS','MPHASIS.NS','MRF.NS','MUTHOOTFIN.NS','NATCOPHARM.NS','NATIONALUM.NS','NAVINFLUOR.NS','NESTLEIND.NS','NHPC.NS','NIACL.NS','NMDC.NS','NOCIL.NS','NTPC.NS','NYKAA.NS','OBEROIRLTY.NS','OFSS.NS','OIL.NS','ONGC.NS','ORIENTCEM.NS','ORIENTELEC.NS','PAYTM.NS','PCJEWELLER.NS','PERSISTENT.NS','PETRONET.NS','PFC.NS','PFIZER.NS','PHOENIXLTD.NS','PIDILITIND.NS','PNB.NS','POLICYBZR.NS','POONAWALLA.NS','POWERGRID.NS','PRESTIGE.NS','RADICO.NS','RAMCOCEM.NS','RATEGAIN.NS','RATNAMANI.NS','RBLBANK.NS','RECLTD.NS','RELAXO.NS','RELIANCE.NS','RPOWER.NS','SAIL.NS','SANOFI.NS','SBILIFE.NS','SBIN.NS','SENCO.NS','SHOPERSTOP.NS','SHREECEM.NS','SIEMENS.NS','SJVN.NS','SOBHA.NS','SONATSOFTW.NS','STAR.NS','STARHEALTH.NS','STLTECH.NS','SUNPHARMA.NS','SUNTECK.NS','SYMPHONY.NS','TATACOMM.NS','TATACONSUM.NS','TATAELXSI.NS','TATAINVEST.NS','TATAPOWER.NS','TATASTEEL.NS','TCS.NS','TECHM.NS','TEJASNET.NS','THERMAX.NS','TITAN.NS','TMPV.NS','TORNTPHARM.NS','TORNTPOWER.NS','TRENT.NS','TVSMOTOR.NS','ULTRACEMCO.NS','UNIONBANK.NS','UNITDSPR.NS','VBL.NS','VEDL.NS','VINATIORGA.NS','VIPIND.NS','VMART.NS','VOLTAS.NS','WHIRLPOOL.NS','WIPRO.NS','YESBANK.NS','ZENSARTECH.NS','ZYDUSLIFE.NS') mapped, p.peers FROM alpha_scan2 a LEFT JOIN p ON p.ticker=a.ticker WHERE a.cycle='2026-10-14' AND a.error IS NULL)
SELECT CASE WHEN mapped THEN '1 mapped (hand-written NSE_SECTORS)' WHEN peers IS NULL THEN '3 unmapped, no peers (market averages)' ELSE '2 unmapped, Yahoo fallback' END kind,
 coalesce(CASE WHEN NOT mapped THEN g.yahoo || ' -> ' || g.sector END, CASE WHEN NOT mapped AND peers IS NOT NULL THEN 'unrecognised peer set: '||peers END, '') grp,
 count(*) n
FROM s LEFT JOIN grp g ON g.first3 = s.peers AND NOT s.mapped
GROUP BY 1,2 ORDER BY 1, 3 DESC;

-- 5. Source-independent alternatives (decision document, section 5).
--    alt2: value not measured unless peers come from a classified group
--          (the 64 distress judgements, which use no peers, are kept)
--          (distress judgements, which use no peers, are kept)
--          (i.e. the Yahoo fallback is removed). alt3: value not measured when
--          no multiple has >=2 valid peers. A not-measured factor contributes 0
--          (methodology: weights are not rescaled); coverage drops by
--          0.15 x the value confidence; tiers keep the 0.3 coverage floor.
WITH p AS (SELECT ticker, count(*) FILTER (WHERE peer_pe IS NOT NULL AND peer_pe<>0) npe, count(*) FILTER (WHERE peer_pb IS NOT NULL AND peer_pb<>0) npb FROM factor_input_peers WHERE cycle_id='2026-10-14' GROUP BY ticker),
lg AS (SELECT ticker, max(value_num) FILTER (WHERE input_name='legs_used') legs FROM factor_inputs WHERE cycle_id='2026-10-14' AND factor='value' GROUP BY ticker),
b AS (SELECT a.ticker, a.alpha_score, a.signal, a.confidence, a.market_cap, a.value, a.ticker IN ('AARTIIND.NS','ABB.NS','ABBOTINDIA.NS','ABFRL.NS','ACC.NS','ADANIENT.NS','ADANIGREEN.NS','ADANIPORTS.NS','ADANIPOWER.NS','AEGISLOG.NS','AIAENG.NS','AJANTPHARM.NS','ALKEM.NS','ALKYLAMINE.NS','AMBUJACEM.NS','APOLLOHOSP.NS','APOLLOTYRE.NS','ARE&M.NS','ASHOKLEY.NS','ASIANPAINT.NS','AUBANK.NS','AUROPHARMA.NS','AXISBANK.NS','BAJAJ-AUTO.NS','BAJAJCON.NS','BAJAJELEC.NS','BAJAJFINSV.NS','BAJAJHLDNG.NS','BAJFINANCE.NS','BALKRISIND.NS','BANDHANBNK.NS','BANKBARODA.NS','BANKINDIA.NS','BATAINDIA.NS','BERGEPAINT.NS','BHARATFORG.NS','BHARTIARTL.NS','BHEL.NS','BIOCON.NS','BIRLACORPN.NS','BLUESTARCO.NS','BOSCHLTD.NS','BPCL.NS','BRIGADE.NS','BRITANNIA.NS','CANBK.NS','CANFINHOME.NS','CASTROLIND.NS','CEATLTD.NS','CESC.NS','CGPOWER.NS','CHOLAFIN.NS','CIPLA.NS','CLEAN.NS','COALINDIA.NS','COFORGE.NS','COLPAL.NS','CROMPTON.NS','CYIENT.NS','DABUR.NS','DALBHARAT.NS','DCBBANK.NS','DEEPAKNTR.NS','DEVYANI.NS','DIVISLAB.NS','DLF.NS','DMART.NS','DRREDDY.NS','EDELWEISS.NS','EICHERMOT.NS','EMAMILTD.NS','ERIS.NS','ESCORTS.NS','ETERNAL.NS','EXIDEIND.NS','FEDERALBNK.NS','GAIL.NS','GALAXYSURF.NS','GICRE.NS','GLAXO.NS','GLENMARK.NS','GODREJCP.NS','GODREJIND.NS','GODREJPROP.NS','GPPL.NS','GRANULES.NS','GRINDWELL.NS','GUJGASLTD.NS','GULFOILLUB.NS','HAPPSTMNDS.NS','HATSUN.NS','HAVELLS.NS','HCLTECH.NS','HDFCBANK.NS','HDFCLIFE.NS','HEIDELBERG.NS','HEROMOTOCO.NS','HEXT.NS','HFCL.NS','HINDALCO.NS','HINDPETRO.NS','HINDUNILVR.NS','HUDCO.NS','ICICIBANK.NS','ICICIGI.NS','ICICIPRULI.NS','IDEA.NS','IDFCFIRSTB.NS','IGL.NS','INDIAMART.NS','INDIGO.NS','INDUSINDBK.NS','INFY.NS','IOC.NS','IPCALAB.NS','IRB.NS','IRFC.NS','ITC.NS','JBCHEPHARM.NS','JKCEMENT.NS','JSWENERGY.NS','JSWHL.NS','JSWSTEEL.NS','JUBLFOOD.NS','KALYANKJIL.NS','KANSAINER.NS','KARURVYSYA.NS','KEYFINSERV.NS','KNRCON.NS','KOTAKBANK.NS','KPITTECH.NS','LAURUSLABS.NS','LICHSGFIN.NS','LICI.NS','LT.NS','LTF.NS','LTTS.NS','LUPIN.NS','M&M.NS','MAHLIFE.NS','MANAPPURAM.NS','MANYAVAR.NS','MARICO.NS','MARUTI.NS','MASTEK.NS','MGL.NS','MOIL.NS','MOTHERSON.NS','MPHASIS.NS','MRF.NS','MUTHOOTFIN.NS','NATCOPHARM.NS','NATIONALUM.NS','NAVINFLUOR.NS','NESTLEIND.NS','NHPC.NS','NIACL.NS','NMDC.NS','NOCIL.NS','NTPC.NS','NYKAA.NS','OBEROIRLTY.NS','OFSS.NS','OIL.NS','ONGC.NS','ORIENTCEM.NS','ORIENTELEC.NS','PAYTM.NS','PCJEWELLER.NS','PERSISTENT.NS','PETRONET.NS','PFC.NS','PFIZER.NS','PHOENIXLTD.NS','PIDILITIND.NS','PNB.NS','POLICYBZR.NS','POONAWALLA.NS','POWERGRID.NS','PRESTIGE.NS','RADICO.NS','RAMCOCEM.NS','RATEGAIN.NS','RATNAMANI.NS','RBLBANK.NS','RECLTD.NS','RELAXO.NS','RELIANCE.NS','RPOWER.NS','SAIL.NS','SANOFI.NS','SBILIFE.NS','SBIN.NS','SENCO.NS','SHOPERSTOP.NS','SHREECEM.NS','SIEMENS.NS','SJVN.NS','SOBHA.NS','SONATSOFTW.NS','STAR.NS','STARHEALTH.NS','STLTECH.NS','SUNPHARMA.NS','SUNTECK.NS','SYMPHONY.NS','TATACOMM.NS','TATACONSUM.NS','TATAELXSI.NS','TATAINVEST.NS','TATAPOWER.NS','TATASTEEL.NS','TCS.NS','TECHM.NS','TEJASNET.NS','THERMAX.NS','TITAN.NS','TMPV.NS','TORNTPHARM.NS','TORNTPOWER.NS','TRENT.NS','TVSMOTOR.NS','ULTRACEMCO.NS','UNIONBANK.NS','UNITDSPR.NS','VBL.NS','VEDL.NS','VINATIORGA.NS','VIPIND.NS','VMART.NS','VOLTAS.NS','WHIRLPOOL.NS','WIPRO.NS','YESBANK.NS','ZENSARTECH.NS','ZYDUSLIFE.NS') mapped,
        coalesce(p.npe,0) npe, coalesce(p.npb,0) npb, lg.legs,
        CASE WHEN lg.legs IS NULL THEN 0 WHEN lg.legs=0 THEN 0.6 ELSE least(1.0, 0.5+0.1*coalesce(p.npe,0)) * CASE WHEN lg.legs<2 THEN 0.5 ELSE 1 END END vconf
      FROM alpha_scan2 a LEFT JOIN p ON p.ticker=a.ticker LEFT JOIN lg ON lg.ticker=a.ticker
      WHERE a.cycle='2026-10-14' AND a.error IS NULL),
alt AS (SELECT 'alt2: no value unless peers come from a classified group' alt, b.*, (NOT mapped AND legs IS NOT NULL AND legs>0) hit FROM b
        UNION ALL
        SELECT 'alt3: no value when no multiple has >=2 valid peers', b.*, (legs IS NOT NULL AND legs>0 AND npe<2 AND npb<2) FROM b),
r AS (SELECT alt, ticker, market_cap, signal, hit, alpha_score a0, confidence c0,
        CASE WHEN hit THEN round((alpha_score - 15*value)::numeric,2) ELSE alpha_score END a1,
        CASE WHEN hit THEN confidence - 0.15*vconf ELSE confidence END c1 FROM alt),
lab AS (SELECT r.*, CASE WHEN a1>40 THEN 'STRONG BUY' WHEN a1>15 THEN 'BUY' WHEN a1< -40 THEN 'STRONG SELL' WHEN a1< -15 THEN 'SELL' ELSE 'NEUTRAL' END s1 FROM r),
tier0 AS (SELECT alt, ticker, a0 a, CASE WHEN rk<=100 THEN 'large' WHEN rk<=250 THEN 'mid' ELSE 'small' END t FROM (SELECT *, row_number() OVER (PARTITION BY alt ORDER BY market_cap DESC) rk FROM lab WHERE c0>=0.3 AND market_cap IS NOT NULL) z),
tier1 AS (SELECT alt, ticker, a1 a, CASE WHEN rk<=100 THEN 'large' WHEN rk<=250 THEN 'mid' ELSE 'small' END t FROM (SELECT *, row_number() OVER (PARTITION BY alt ORDER BY market_cap DESC) rk FROM lab WHERE c1>=0.3 AND market_cap IS NOT NULL) z),
top0 AS (SELECT alt, t, ticker FROM (SELECT *, row_number() OVER (PARTITION BY alt, t ORDER BY a DESC) k FROM tier0) z WHERE k<=10),
top1 AS (SELECT alt, t, ticker FROM (SELECT *, row_number() OVER (PARTITION BY alt, t ORDER BY a DESC) k FROM tier1) z WHERE k<=10)
SELECT l.alt,
  count(*) FILTER (WHERE hit) stocks_affected,
  round(avg(abs(a1-a0)) FILTER (WHERE hit)::numeric,2) mean_abs_alpha_change,
  count(*) FILTER (WHERE s1<>signal) label_flips,
  count(*) FILTER (WHERE s1<>signal AND signal IN ('BUY','STRONG BUY')) flips_from_buy,
  count(*) FILTER (WHERE s1<>signal AND s1 IN ('BUY','STRONG BUY')) flips_to_buy,
  count(*) FILTER (WHERE c0>=0.3 AND c1<0.3) newly_below_conf_floor,
  (SELECT count(*) FROM top0 x WHERE x.alt=l.alt AND NOT EXISTS (SELECT 1 FROM top1 y WHERE y.alt=x.alt AND y.t=x.t AND y.ticker=x.ticker)) top10_buy_slots_changed_of_30
FROM lab l GROUP BY l.alt ORDER BY 1;

-- 6. Fingerprints of the inputs every query above reads (cycle 2026-10-14).
--    Expected: alpha_scan2 2491 df7c3957b6155540cc8cbeec9f611763;
--    factor_inputs(value) 22162 a062761bb3e64f77af3aa9ad79d626e5;
--    factor_input_peers 7152 c0ee393d7c70cf549836386697ac7e44.
SELECT 'alpha_scan2' tbl, count(*) n, md5(string_agg(concat_ws('|', ticker, alpha_score, signal, confidence, market_cap, momentum, quality, value, sentiment, error), E'\n' ORDER BY ticker)) fp FROM alpha_scan2 WHERE cycle='2026-10-14'
UNION ALL SELECT 'factor_inputs(value)', count(*), md5(string_agg(concat_ws('|', ticker, input_name, value_num, value_text, missing), E'\n' ORDER BY ticker, input_name)) FROM factor_inputs WHERE cycle_id='2026-10-14' AND factor='value'
UNION ALL SELECT 'factor_input_peers', count(*), md5(string_agg(concat_ws('|', ticker, peer_ticker, peer_pe, peer_pb), E'\n' ORDER BY ticker, peer_ticker)) FROM factor_input_peers WHERE cycle_id='2026-10-14';
