import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from 'recharts'
import { compareStocks } from '../api'
import Spinner from '../components/Spinner'
import { EvidenceBadge } from '../components/Evidence'
import { signalLabel, SIGNAL_TITLE, rankBadgeClass, scoreTextClass } from '../signalLabel'

/**
 * Compare — 2 to 6 stocks side by side: growth of Rs 100, drawdowns, value,
 * quality, risk and the model's view. Spec: docs/PROPOSAL_PRODUCT_ADDITIONS_2026-09-23.md (#2).
 *
 * No row names a winner. Higher is not better for volatility, P/E or a
 * drawdown, so each row only marks its highest and lowest value.
 */
const COLOURS = ['#38bdf8', '#f59e0b', '#a78bfa', '#34d399', '#f472b6', '#e5e7eb']
const PERIODS = [['6m', '6 months'], ['1y', '1 year'], ['3y', '3 years'], ['5y', '5 years']]
const NA = 'not available'

const pct = (v, d = 1) => (v == null ? NA : `${Number(v).toFixed(d)}%`)
const frac = (v, d = 1) => (v == null ? NA : `${(Number(v) * 100).toFixed(d)}%`)
const num = (v, d = 2) => (v == null ? NA : Number(v).toFixed(d))
const crore = v => (v == null ? NA : `Rs ${(Number(v) / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 0 })} cr`)
const short = t => t.replace('.NS', '')

// [label, getter, formatter, tooltip]
const RISK_ROWS = [
  ['Return over the period', r => r.total_return_pct, v => pct(v)],
  ['Volatility (annualised)', r => r.volatility_pct, v => pct(v)],
  ['Largest drop from a peak', r => r.max_drawdown_pct, v => pct(v)],
  ['Worst month', r => r.worst_month_pct, v => pct(v)],
  ['Average of the worst 5% of days (CVaR)', r => r.cvar95_daily_pct, v => pct(v, 2)],
  ['Beta against the Nifty 50', r => r.beta_vs_nifty, v => num(v)],
  ['Sharpe ratio', r => r.sharpe, v => num(v)],
  ['Sortino ratio', r => r.sortino, v => num(v)],
]
const VALUE_ROWS = [
  ['P/E', v => v.pe_ratio, x => num(x, 1)],
  ['Forward P/E', v => v.forward_pe, x => num(x, 1)],
  ['Price to book', v => v.price_to_book, x => num(x, 2)],
  ['Price to sales', v => v.price_to_sales, x => num(x, 2)],
  ['EV / EBITDA', v => v.ev_ebitda, x => num(x, 1)],
  ['Dividend yield', v => v.dividend_yield, x => pct(x, 2)],
  ['Market cap', v => v.market_cap, crore],
]
const QUALITY_ROWS = [
  ['Return on equity', q => q.roe, x => frac(x)],
  ['Return on assets', q => q.roa, x => frac(x)],
  ['Operating margin', q => q.operating_margin, x => frac(x)],
  ['Profit margin', q => q.profit_margin, x => frac(x)],
  ['Revenue growth', q => q.revenue_growth, x => frac(x)],
  ['Earnings growth', q => q.earnings_growth, x => frac(x)],
  ['Debt to equity', q => q.debt_to_equity, x => num(x, 2)],
  ['Current ratio', q => q.current_ratio, x => num(x, 2)],
  ['Free cash flow', q => q.free_cashflow, crore],
]

function parseTickers(s) {
  return (s || '').split(/[\s,]+/).map(t => t.trim().toUpperCase()).filter(Boolean)
}

// One row: the value for each stock, with the highest and lowest marked.
function Row({ label, tickers, get, fmt }) {
  const vals = tickers.map(t => get(t))
  const nums = vals.filter(v => v != null && Number.isFinite(Number(v))).map(Number)
  const hi = nums.length > 1 ? Math.max(...nums) : null
  const lo = nums.length > 1 ? Math.min(...nums) : null
  return (
    <tr className="border-b border-gray-800 last:border-0">
      <td className="py-1.5 pr-3 text-gray-400 text-xs whitespace-nowrap">{label}</td>
      {vals.map((v, i) => (
        <td key={tickers[i]} className="py-1.5 px-2 text-right font-mono text-xs whitespace-nowrap">
          <span className={v == null ? 'text-gray-600' : 'text-gray-200'}>{fmt(v)}</span>
          {hi !== lo && v != null && Number(v) === hi && <span className="ml-1 text-[9px] text-sky-400/80 uppercase">highest</span>}
          {hi !== lo && v != null && Number(v) === lo && <span className="ml-1 text-[9px] text-slate-500 uppercase">lowest</span>}
        </td>
      ))}
    </tr>
  )
}

function Table({ title, note, tickers, rows, source }) {
  return (
    <div className="card overflow-x-auto">
      <h2 className="font-semibold mb-1">{title}</h2>
      {note && <p className="text-[11px] text-gray-500 mb-2">{note}</p>}
      <table className="w-full min-w-[480px]">
        <thead>
          <tr className="border-b border-gray-700">
            <th className="text-left text-[11px] text-gray-500 font-normal py-1" />
            {tickers.map((t, i) => (
              <th key={t} className="text-right text-xs font-mono py-1 px-2" style={{ color: COLOURS[i] }}>{short(t)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, get, fmt]) => (
            <Row key={label} label={label} tickers={tickers} get={t => { const s = source(t); return s ? get(s) : null }} fmt={fmt} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function mergeSeries(data, key) {
  const rows = new Map()
  for (const t of data.tickers) {
    const s = data.series[t]
    s.dates.forEach((d, i) => { if (!rows.has(d)) rows.set(d, { date: d }); rows.get(d)[t] = s[key][i] })
  }
  if (data.benchmark && key === 'rebased') {
    data.benchmark.dates.forEach((d, i) => { if (rows.has(d)) rows.get(d).NIFTY = data.benchmark.rebased[i] })
  }
  return [...rows.values()].sort((a, b) => (a.date < b.date ? -1 : 1))
}

function Chart({ data, keyName, title, note, unit, zeroLine }) {
  const rows = mergeSeries(data, keyName)
  return (
    <div className="card">
      <h2 className="font-semibold mb-1">{title}</h2>
      <p className="text-[11px] text-gray-500 mb-2">{note}</p>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={rows} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
          <XAxis dataKey="date" stroke="#6b7280" fontSize={10} minTickGap={40} />
          <YAxis stroke="#6b7280" fontSize={10} width={44} unit={unit} domain={['auto', 'auto']} />
          <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 12 }}
                   formatter={(v, n) => [`${Number(v).toFixed(1)}${unit}`, n === 'NIFTY' ? 'Nifty 50' : short(n)]} />
          <Legend formatter={n => (n === 'NIFTY' ? 'Nifty 50 (price index)' : short(n))} wrapperStyle={{ fontSize: 11 }} />
          {zeroLine && <ReferenceLine y={0} stroke="#4b5563" />}
          {data.tickers.map((t, i) => (
            <Line key={t} type="monotone" dataKey={t} stroke={COLOURS[i]} dot={false} strokeWidth={1.6} isAnimationActive={false} />
          ))}
          {keyName === 'rebased' && data.benchmark && (
            <Line type="monotone" dataKey="NIFTY" stroke="#9ca3af" strokeDasharray="5 4" dot={false} strokeWidth={1.2} isAnimationActive={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function ModelView({ data }) {
  const factors = [['momentum', 'Momentum'], ['quality', 'Quality'], ['value', 'Value'], ['sentiment', 'Sentiment']]
  return (
    <div className="card overflow-x-auto">
      <h2 className="font-semibold mb-1">The model's view</h2>
      <p className="text-[11px] text-gray-500 mb-2">{data.notes.model} From the latest nightly scan.</p>
      <table className="w-full min-w-[480px]">
        <thead>
          <tr className="border-b border-gray-700">
            <th />
            {data.tickers.map((t, i) => (
              <th key={t} className="text-right text-xs font-mono py-1 px-2" style={{ color: COLOURS[i] }}>{short(t)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-gray-800">
            <td className="py-1.5 text-gray-400 text-xs">Rank</td>
            {data.tickers.map(t => {
              const m = data.model?.[t]
              return (
                <td key={t} className="py-1.5 px-2 text-right">
                  {m ? <span className={rankBadgeClass(m.signal)} title={SIGNAL_TITLE}>{signalLabel(m.signal)}</span>
                     : <span className="text-xs text-gray-600">not scanned</span>}
                </td>
              )
            })}
          </tr>
          <tr className="border-b border-gray-800">
            <td className="py-1.5 text-gray-400 text-xs">Score (-100 to +100)</td>
            {data.tickers.map(t => {
              const m = data.model?.[t]
              return <td key={t} className={`py-1.5 px-2 text-right font-mono text-xs ${scoreTextClass(m?.alpha_score)}`}>{m?.alpha_score != null ? Number(m.alpha_score).toFixed(0) : NA}</td>
            })}
          </tr>
          <tr className="border-b border-gray-800">
            <td className="py-1.5 text-gray-400 text-xs" title="How much of the model's input data was available, not the chance the rank is right.">Data coverage</td>
            {data.tickers.map(t => {
              const m = data.model?.[t]
              return <td key={t} className="py-1.5 px-2 text-right font-mono text-xs text-gray-300">{m?.data_coverage != null ? `${Math.round(m.data_coverage * 100)}%` : NA}</td>
            })}
          </tr>
          {factors.map(([k, label]) => (
            <tr key={k} className="border-b border-gray-800 last:border-0">
              <td className="py-1.5 text-gray-400 text-xs"><span className="mr-1.5">{label}</span><EvidenceBadge factor={k} /></td>
              {data.tickers.map(t => {
                const v = data.model?.[t]?.factors?.[k]
                return <td key={t} className="py-1.5 px-2 text-right font-mono text-xs text-gray-300">{v != null ? Number(v).toFixed(2) : NA}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Correlation({ data }) {
  const t = data.tickers
  return (
    <div className="card overflow-x-auto">
      <h2 className="font-semibold mb-1">How closely they moved together</h2>
      <p className="text-[11px] text-gray-500 mb-2">Correlation of daily returns over the period: 1 means they moved in step, 0 not at all. Past only.</p>
      <table className="min-w-[360px]">
        <thead>
          <tr><th />{t.map((x, i) => <th key={x} className="px-2 py-1 text-xs font-mono" style={{ color: COLOURS[i] }}>{short(x)}</th>)}</tr>
        </thead>
        <tbody>
          {t.map((a, i) => (
            <tr key={a}>
              <td className="pr-2 py-1 text-xs font-mono" style={{ color: COLOURS[i] }}>{short(a)}</td>
              {t.map(b => {
                const v = data.correlation?.[a]?.[b]
                const shade = a === b ? 'bg-gray-800 text-gray-500' : v >= 0.7 ? 'bg-sky-900/60 text-sky-200' : v >= 0.4 ? 'bg-sky-950/60 text-sky-300' : 'text-gray-300'
                return <td key={b} className={`px-2 py-1 text-center font-mono text-xs rounded ${shade}`}>{v != null ? v.toFixed(2) : NA}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Compare() {
  const [params, setParams] = useSearchParams()
  const [input, setInput] = useState(params.get('tickers') || '')
  const [period, setPeriod] = useState(params.get('period') || '1y')
  const asked = parseTickers(params.get('tickers'))
  const askedPeriod = params.get('period') || '1y'
  const ready = asked.length >= 2 && asked.length <= 6

  const { data, isFetching, error } = useQuery({
    queryKey: ['compare', asked.join(','), askedPeriod],
    queryFn: () => compareStocks(asked, askedPeriod),
    enabled: ready,
    staleTime: 600000,
  })

  const typed = parseTickers(input)
  const submit = e => {
    e.preventDefault()
    if (typed.length < 2 || typed.length > 6) return
    setParams({ tickers: typed.join(','), period })
  }

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Compare stocks</h1>
        <p className="text-gray-400 text-sm mt-0.5">
          Two to six stocks side by side. Each row marks its highest and lowest value; none of them is a verdict.
        </p>
      </div>

      <form onSubmit={submit} className="card flex flex-col sm:flex-row gap-3 sm:items-end">
        <label className="flex-1">
          <span className="text-xs text-gray-500">Tickers, separated by commas</span>
          <input className="input w-full mt-1 font-mono" value={input} onChange={e => setInput(e.target.value)}
                 placeholder="TCS, INFY, WIPRO" aria-label="Tickers to compare" />
        </label>
        <div className="flex gap-1" role="group" aria-label="Period">
          {PERIODS.map(([k, label]) => (
            <button type="button" key={k} onClick={() => setPeriod(k)}
                    className={`px-2.5 py-1.5 rounded text-xs border ${period === k ? 'border-sky-600 text-sky-300 bg-sky-900/30' : 'border-gray-700 text-gray-400'}`}>
              {label}
            </button>
          ))}
        </div>
        <button className="btn-primary text-sm" disabled={typed.length < 2 || typed.length > 6}>Compare</button>
      </form>
      {typed.length > 6 && <p className="text-xs text-amber-400">Up to six stocks at a time.</p>}

      {isFetching && <div className="card flex items-center gap-3"><Spinner /><span className="text-sm text-gray-400">Fetching prices and figures…</span></div>}
      {error && <p className="text-sm text-red-400">{typeof error === 'string' ? error : 'The comparison could not be loaded.'}</p>}
      {!ready && !isFetching && <p className="text-sm text-gray-500">Enter two to six tickers to start.</p>}

      {data && !isFetching && (
        <>
          {Object.keys(data.excluded || {}).length > 0 && (
            <p className="text-xs text-amber-400">
              Left out: {Object.entries(data.excluded).map(([t, why]) => `${short(t)} (${why})`).join('; ')}.
            </p>
          )}
          <p className="text-[11px] text-gray-500">{data.notes.risk} {data.notes.highlights}</p>

          <Chart data={data} keyName="rebased" title="Growth of Rs 100" unit=""
                 note={`Each stock's adjusted price, set to 100 on ${data.from}. The dashed line is the Nifty 50 price index, which leaves out dividends.`} />
          <Chart data={data} keyName="drawdown_pct" title="How far below its own previous peak" unit="%" zeroLine
                 note="0% means at a new high; the lower the line, the deeper the fall from the peak at that time." />

          <Table title="Risk" note={`${data.notes.risk} ${data.notes.beta}`} tickers={data.tickers}
                 rows={RISK_ROWS} source={t => data.risk?.[t]} />
          <Correlation data={data} />
          {data.value && (
            <Table title="Value" note={`${data.notes.fundamentals} As of ${data.fundamentals_as_of}.${data.notes.sectors ? ' ' + data.notes.sectors : ''}`}
                   tickers={data.tickers} rows={VALUE_ROWS} source={t => data.value?.[t]} />
          )}
          {data.quality && (
            <Table title="Quality and business" note={data.notes.fundamentals} tickers={data.tickers}
                   rows={[...QUALITY_ROWS, ['Piotroski F-score (0 to 9)', q => q.piotroski, x => (x == null ? NA : String(x))]]}
                   source={t => data.quality?.[t]} />
          )}
          <ModelView data={data} />
          <p className="text-[11px] text-gray-600">
            Past figures describe what happened, not what comes next. Open a stock on the <Link to="/stock" className="underline">Stocks</Link> page for its full detail.
          </p>
        </>
      )}
    </div>
  )
}
