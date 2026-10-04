import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, ComposedChart, BarChart, LineChart, Bar, Line, Area, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from 'recharts'
import { getFundamentalsHistory, getTechnicals } from '../api'
import Spinner from './Spinner'

/**
 * StockAnalysis — a stock's results over the years and its price indicators.
 * Owner request 2026-10-04. Backend: backend/modules/stock_analysis.py.
 *
 * Both halves describe; neither recommends. Statement figures are Yahoo's
 * latest (not point-in-time), and the indicators are untested by this project,
 * which the panels say in plain words. A figure Yahoo lacks is drawn as a gap,
 * never as zero.
 */

const C = {
  revenue: '#38bdf8', profit: '#34d399', operating: '#a78bfa', debt: '#f59e0b',
  ocf: '#38bdf8', capex: '#f87171', fcf: '#34d399', eps: '#e5e7eb',
  up: '#34d399', down: '#f87171', sma20: '#f59e0b', sma50: '#38bdf8', sma200: '#f472b6',
  ema20: '#e5e7eb', band: '#a78bfa', macd: '#38bdf8', signal: '#f59e0b',
}
const GRID = <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
const TIP = { background: '#111827', border: '1px solid #374151', fontSize: 12, borderRadius: 8 }
const AXIS = { stroke: '#6b7280', fontSize: 10 }

const cr = v => (v == null ? 'no figure' : `Rs ${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })} cr`)
const pc = v => (v == null ? 'no figure' : `${Number(v).toFixed(1)}%`)
const nx = (v, d = 2) => (v == null ? 'no figure' : Number(v).toFixed(d))
const errText = e => (typeof e === 'string' ? e : e?.message || 'Could not load this.')

export default function StockAnalysis({ ticker }) {
  const [tab, setTab] = useState('fundamentals')
  const tabs = [['fundamentals', 'Fundamentals over time'], ['technicals', 'Technical analysis']]
  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center gap-2" role="tablist">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              tab === k ? 'bg-green-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'fundamentals' ? <Fundamentals ticker={ticker} /> : <Technicals ticker={ticker} />}
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// FUNDAMENTALS OVER TIME
// ═════════════════════════════════════════════════════════════════════════════

function ChartBox({ title, sub, children, height = 220 }) {
  return (
    <div className="card-sm">
      <p className="text-sm font-medium">{title}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
      <div className="mt-2" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
      </div>
    </div>
  )
}

function Fundamentals({ ticker }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['fund-history', ticker], queryFn: () => getFundamentalsHistory(ticker),
    enabled: !!ticker, staleTime: 6 * 3600 * 1000, retry: 1,
  })
  if (isLoading) return <Spinner size="sm" />
  if (error) return <p className="text-sm text-gray-400">{errText(error)}</p>
  if (!data?.annual?.length) return null

  const a = data.annual
  const q = data.quarterly || []
  // Margins beyond +/-100% (profit or loss larger than revenue) stay in the table but not
  // on the chart, where one such year would flatten every other (owner decision 2026-10-04).
  const inChart = v => (v != null && Math.abs(v) <= 100 ? v : null)
  const marginRows = a.map(r => ({ ...r, net_margin_pct: inChart(r.net_margin_pct), operating_margin_pct: inChart(r.operating_margin_pct) }))
  const noOperating = a.every(r => r.operating_income == null)
  const hasCash = a.some(r => r.operating_cash_flow != null || r.free_cash_flow != null)

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        {a.length} years ({a[0].label} to {a[a.length - 1].label}) from {data.source}, in Rs crore. {data.notes.point_in_time}
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartBox title="Revenue and profit" sub="Each year's revenue and net profit">
          <BarChart data={a} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="label" {...AXIS} />
            <YAxis {...AXIS} width={64} tickFormatter={v => Number(v).toLocaleString('en-IN')} />
            <Tooltip contentStyle={TIP} formatter={(v, n) => [cr(v), n]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="revenue" name="Revenue" fill={C.revenue} isAnimationActive={false} />
            <Bar dataKey="net_income" name="Net profit" fill={C.profit} isAnimationActive={false} />
          </BarChart>
        </ChartBox>

        <ChartBox title="Margins" sub={noOperating ? 'Net margin (no operating income reported for this company)' : 'Operating and net margin, % of revenue'}>
          <LineChart data={marginRows} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="label" {...AXIS} />
            <YAxis {...AXIS} width={44} unit="%" />
            <Tooltip contentStyle={TIP} formatter={(v, n) => [pc(v), n]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {!noOperating && <Line dataKey="operating_margin_pct" name="Operating margin" stroke={C.operating} dot isAnimationActive={false} />}
            <Line dataKey="net_margin_pct" name="Net margin" stroke={C.profit} dot isAnimationActive={false} />
          </LineChart>
        </ChartBox>

        <ChartBox title="Return on equity and debt" sub="ROE = profit / year-end equity (left); debt / equity (right)">
          <ComposedChart data={a} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="label" {...AXIS} />
            <YAxis yAxisId="l" {...AXIS} width={44} unit="%" />
            {/* From 0 and at least up to 1, so a debt/equity of 0.1 looks small rather than filling the chart. */}
            <YAxis yAxisId="r" orientation="right" {...AXIS} width={36} domain={[0, m => Math.max(1, Math.ceil(m * 10) / 10)]} />
            <Tooltip contentStyle={TIP} formatter={(v, n) => [n === 'Debt / equity' ? nx(v) : pc(v), n]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar yAxisId="r" dataKey="debt_to_equity" name="Debt / equity" fill={C.debt} opacity={0.7} isAnimationActive={false} />
            <Line yAxisId="l" dataKey="roe_pct" name="Return on equity" stroke={C.profit} dot isAnimationActive={false} />
          </ComposedChart>
        </ChartBox>

        {hasCash && (
          <ChartBox title="Cash flow" sub="Cash from operations, spending on assets (capex) and what is left (free cash flow)">
            <BarChart data={a} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
              {GRID}
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} width={64} tickFormatter={v => Number(v).toLocaleString('en-IN')} />
              <Tooltip contentStyle={TIP} formatter={(v, n) => [cr(v), n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#4b5563" />
              <Bar dataKey="operating_cash_flow" name="From operations" fill={C.ocf} isAnimationActive={false} />
              <Bar dataKey="capex" name="Capex" fill={C.capex} isAnimationActive={false} />
              <Bar dataKey="free_cash_flow" name="Free cash flow" fill={C.fcf} isAnimationActive={false} />
            </BarChart>
          </ChartBox>
        )}

        <ChartBox title="Earnings per share"
          sub={data.notes.eps_break ? 'Diluted EPS, Rs. Not comparable across all years: see the note below' : 'Diluted EPS, Rs'}>
          <LineChart data={a} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="label" {...AXIS} />
            <YAxis {...AXIS} width={44} />
            <Tooltip contentStyle={TIP} formatter={v => [v == null ? 'no figure' : `Rs ${nx(v)}`, 'EPS']} />
            <Line dataKey="eps_diluted" name="EPS" stroke={C.eps} dot isAnimationActive={false} />
          </LineChart>
        </ChartBox>

        {q.length > 0 && (
          <ChartBox title="Recent quarters" sub={`The ${q.length} quarters Yahoo has; a missing quarter is not shown as zero`}>
            <BarChart data={q} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
              {GRID}
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} width={64} tickFormatter={v => Number(v).toLocaleString('en-IN')} />
              <Tooltip contentStyle={TIP} formatter={(v, n) => [cr(v), n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="revenue" name="Revenue" fill={C.revenue} isAnimationActive={false} />
              <Bar dataKey="net_income" name="Net profit" fill={C.profit} isAnimationActive={false} />
            </BarChart>
          </ChartBox>
        )}
      </div>

      <FiguresTable rows={a} />

      <ul className="text-xs text-gray-500 space-y-1 list-disc pl-4">
        <li>{data.notes.roe}</li>
        {data.notes.gaps && <li>{data.notes.gaps}</li>}
        {data.notes.eps_break && <li className="text-amber-300/90">{data.notes.eps_break}</li>}
        {data.notes.margin_outliers && <li className="text-amber-300/90">{data.notes.margin_outliers}</li>}
        {(noOperating || !hasCash) && <li>{data.notes.banks}</li>}
      </ul>
    </div>
  )
}

const TABLE_ROWS = [
  ['Revenue', 'revenue', cr], ['Revenue growth', 'revenue_growth_pct', pc],
  ['Operating income', 'operating_income', cr], ['Net profit', 'net_income', cr],
  ['Profit growth', 'net_income_growth_pct', pc], ['Operating margin', 'operating_margin_pct', pc],
  ['Net margin', 'net_margin_pct', pc], ['EPS (diluted, Rs)', 'eps_diluted', v => nx(v)],
  ['Total assets', 'total_assets', cr], ['Equity', 'equity', cr], ['Total debt', 'total_debt', cr],
  ['Cash', 'cash', cr], ['Return on equity', 'roe_pct', pc], ['Debt / equity', 'debt_to_equity', v => nx(v)],
  ['Cash from operations', 'operating_cash_flow', cr], ['Capex', 'capex', cr], ['Free cash flow', 'free_cash_flow', cr],
]

function FiguresTable({ rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800">
            <th className="text-left font-medium py-2 pr-4">All figures</th>
            {rows.map(r => <th key={r.label} className="text-right font-medium py-2 px-2">{r.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {TABLE_ROWS.map(([label, key, fmt]) => (
            <tr key={key} className="border-b border-gray-800/60">
              <td className="py-1.5 pr-4 text-gray-400">{label}</td>
              {rows.map(r => (
                <td key={r.label} className={`py-1.5 px-2 text-right font-mono tabular-nums ${r[key] == null ? 'text-gray-600' : 'text-gray-200'}`}
                    title={r[key] == null ? 'Yahoo has no figure for this year' : undefined}>
                  {r[key] == null ? '—' : fmt(r[key]).replace('Rs ', '').replace(' cr', '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-gray-600 mt-1">Money in Rs crore. A dash means Yahoo has no figure, not zero.</p>
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// TECHNICAL ANALYSIS
// ═════════════════════════════════════════════════════════════════════════════

const PERIODS = [['3m', '3M'], ['6m', '6M'], ['1y', '1Y'], ['2y', '2Y']]
const OVERLAYS = [
  ['sma20', '20-day avg', C.sma20], ['sma50', '50-day avg', C.sma50], ['sma200', '200-day avg', C.sma200],
  ['ema20', '20-day EMA', C.ema20], ['bb', 'Bollinger bands', C.band],
]

// One candle: a wick from low to high and a body from open to close. Recharts
// draws a ranged bar from low to high; the open and close are placed inside it.
function Candle({ x, y, width, height, payload }) {
  const { open, close, high, low } = payload || {}
  if ([open, close, high, low].some(v => v == null) || !(width > 0)) return null
  const up = close >= open
  const col = up ? C.up : C.down
  const span = high - low
  const yOf = v => (span === 0 ? y : y + ((high - v) / span) * height)
  const top = yOf(Math.max(open, close))
  const bot = yOf(Math.min(open, close))
  const cx = x + width / 2
  const bw = Math.max(1, width * 0.7)
  return (
    <g>
      <line x1={cx} x2={cx} y1={y} y2={y + height} stroke={col} strokeWidth={1} />
      <rect x={cx - bw / 2} y={top} width={bw} height={Math.max(1, bot - top)} fill={col} />
    </g>
  )
}

function PriceTip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const row = (k, v) => v != null && <p key={k}><span className="text-gray-500">{k} </span>{Number(v).toFixed(2)}</p>
  return (
    <div style={TIP} className="px-2.5 py-2 text-xs space-y-0.5 font-mono">
      <p className="text-gray-300 font-sans">{d.date}</p>
      {row('Open', d.open)}{row('High', d.high)}{row('Low', d.low)}{row('Close', d.close)}
      {row('20d', d.sma20)}{row('50d', d.sma50)}{row('200d', d.sma200)}
    </div>
  )
}

function Technicals({ ticker }) {
  const [period, setPeriod] = useState('1y')
  const [mode, setMode] = useState('candles')
  const [on, setOn] = useState({ sma50: true, sma200: true })
  const { data, isLoading, error } = useQuery({
    queryKey: ['technicals', ticker, period], queryFn: () => getTechnicals(ticker, period),
    enabled: !!ticker, staleTime: 15 * 60 * 1000, retry: 1,
  })

  const btn = active => `shrink-0 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
    active ? 'bg-green-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`

  const bars = (data?.bars || []).map(b => ({
    ...b,
    range: b.low != null && b.high != null ? [b.low, b.high] : null,
    band: b.bb_lower != null && b.bb_upper != null ? [b.bb_lower, b.bb_upper] : null,
    up: b.close != null && b.open != null && b.close >= b.open,
  }))
  // One tick at the first trading day of each month (every third month for 2Y),
  // so a month never appears twice on the axis.
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const monthStarts = bars.filter((b, i) => i > 0 && b.date.slice(0, 7) !== bars[i - 1].date.slice(0, 7)).map(b => b.date)
  const xTicks = period === '2y' ? monthStarts.filter((_, i) => i % 3 === 0) : monthStarts
  const xTick = d => `${MONTHS[Number(d.slice(5, 7)) - 1]} ${d.slice(2, 4)}`

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">{PERIODS.map(([k, l]) => <button key={k} className={btn(period === k)} onClick={() => setPeriod(k)}>{l}</button>)}</div>
        <span className="text-gray-700">|</span>
        <div className="flex gap-1">
          <button className={btn(mode === 'candles')} onClick={() => setMode('candles')}>Candles</button>
          <button className={btn(mode === 'line')} onClick={() => setMode('line')}>Line</button>
        </div>
        <span className="text-gray-700">|</span>
        <div className="flex flex-wrap gap-1">
          {OVERLAYS.map(([k, l, col]) => (
            <button key={k} className={btn(!!on[k])} onClick={() => setOn(s => ({ ...s, [k]: !s[k] }))}
              aria-pressed={!!on[k]}>
              <span className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle" style={{ background: col }} />{l}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? <Spinner size="sm" /> : error ? <p className="text-sm text-gray-400">{errText(error)}</p> : bars.length > 0 && (
        <>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={bars} syncId="tech" margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
                {GRID}
                <XAxis dataKey="date" {...AXIS} ticks={xTicks} interval={0} tickFormatter={xTick} />
                <YAxis {...AXIS} width={56} domain={['auto', 'auto']} tickFormatter={v => Number(v).toFixed(0)} />
                <Tooltip content={<PriceTip />} />
                {on.bb && <Area dataKey="band" stroke="none" fill={C.band} fillOpacity={0.12} isAnimationActive={false} connectNulls={false} />}
                {on.bb && <Line dataKey="bb_mid" stroke={C.band} strokeDasharray="4 3" dot={false} strokeWidth={1} isAnimationActive={false} />}
                {mode === 'candles'
                  ? <Bar dataKey="range" shape={<Candle />} isAnimationActive={false} />
                  : <Line dataKey="close" stroke="#e5e7eb" dot={false} strokeWidth={1.5} isAnimationActive={false} />}
                {['sma20', 'sma50', 'sma200', 'ema20'].filter(k => on[k]).map(k => (
                  <Line key={k} dataKey={k} stroke={C[k]} dot={false} strokeWidth={1.3} isAnimationActive={false} />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <SubChart title="Volume" height={80}>
            <BarChart data={bars} syncId="tech" margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" hide />
              <YAxis {...AXIS} width={56} tickFormatter={v => (v >= 1e7 ? `${(v / 1e7).toFixed(1)}cr` : v >= 1e5 ? `${(v / 1e5).toFixed(0)}L` : v)} />
              <Tooltip contentStyle={TIP} formatter={v => [Number(v).toLocaleString('en-IN'), 'Volume']} />
              <Bar dataKey="volume" isAnimationActive={false}>
                {bars.map((b, i) => <Cell key={i} fill={b.up ? C.up : C.down} fillOpacity={0.6} />)}
              </Bar>
            </BarChart>
          </SubChart>

          <SubChart title="RSI (14 days)" sub="Lines at 70 and 30" height={110}>
            <LineChart data={bars} syncId="tech" margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
              {GRID}
              <XAxis dataKey="date" hide />
              <YAxis {...AXIS} width={56} domain={[0, 100]} ticks={[0, 30, 50, 70, 100]} />
              <Tooltip contentStyle={TIP} formatter={v => [nx(v, 1), 'RSI']} />
              <ReferenceLine y={70} stroke="#6b7280" strokeDasharray="3 3" />
              <ReferenceLine y={30} stroke="#6b7280" strokeDasharray="3 3" />
              <Line dataKey="rsi14" stroke={C.band} dot={false} strokeWidth={1.3} isAnimationActive={false} />
            </LineChart>
          </SubChart>

          <SubChart title="MACD (12, 26, 9)" sub="MACD line, signal line and the gap between them" height={120}>
            <ComposedChart data={bars} syncId="tech" margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
              {GRID}
              <XAxis dataKey="date" {...AXIS} ticks={xTicks} interval={0} tickFormatter={xTick} />
              <YAxis {...AXIS} width={56} />
              <Tooltip contentStyle={TIP} formatter={(v, n) => [nx(v, 2), n]} />
              <ReferenceLine y={0} stroke="#4b5563" />
              <Bar dataKey="macd_hist" name="Gap" isAnimationActive={false}>
                {bars.map((b, i) => <Cell key={i} fill={(b.macd_hist ?? 0) >= 0 ? C.up : C.down} fillOpacity={0.5} />)}
              </Bar>
              <Line dataKey="macd" name="MACD" stroke={C.macd} dot={false} strokeWidth={1.3} isAnimationActive={false} />
              <Line dataKey="macd_signal" name="Signal" stroke={C.signal} dot={false} strokeWidth={1.3} isAnimationActive={false} />
            </ComposedChart>
          </SubChart>

          {data.readings?.length > 0 && (
            <div className="card-sm">
              <p className="text-sm font-medium mb-2">Latest readings <span className="text-xs text-gray-500 font-normal">({data.to})</span></p>
              <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
                {data.readings.map(r => (
                  <div key={r.key}>
                    <dt className="text-xs text-gray-500">{r.label}</dt>
                    <dd className="text-xs text-gray-300 leading-relaxed">{r.text}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          <div className="p-3 rounded-lg border border-gray-700 bg-gray-800/40 text-xs text-gray-300 leading-relaxed">
            {data.notes.untested} {data.notes.prices}
          </div>
        </>
      )}
    </div>
  )
}

function SubChart({ title, sub, height, children }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{title}{sub && <span className="text-gray-600"> · {sub}</span>}</p>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
      </div>
    </div>
  )
}
