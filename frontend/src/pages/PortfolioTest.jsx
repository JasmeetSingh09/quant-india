import { useMutation } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { runBacktest } from '../api'
import Spinner from '../components/Spinner'
import usePersistentState from '../usePersistentState'
import HoldingsEditor, { newRow, rowsToHoldings, rowsValid } from '../components/HoldingsEditor'

const DEFAULT_ROWS = [
  newRow('HDFCBANK.NS', 40), newRow('TCS.NS', 30), newRow('RELIANCE.NS', 30),
]

function Tile({ label, value, accent }) {
  return (
    <div className="card-sm">
      <p className="stat-label">{label}</p>
      <p className={`stat-value ${accent || 'text-white'}`}>{value ?? '—'}</p>
    </div>
  )
}

export default function PortfolioTest() {
  const [rows, setRows]   = usePersistentState('ptest.rows', DEFAULT_ROWS)
  const [start, setStart] = usePersistentState('ptest.start', '2021-01-01')

  const ok = rowsValid(rows)
  const bt = useMutation({
    mutationFn: () => runBacktest({ holdings: rowsToHoldings(rows), start_date: start }),
  })
  const d = bt.data

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Portfolio Test — Historical Backtest</h1>
        <p className="text-sm text-gray-400 mt-1 max-w-3xl">
          How your exact portfolio would have performed, net of Indian transaction
          costs, vs the Nifty — with a significance test and an honest in-sample /
          out-of-sample split so you can see if the result generalises or is overfit.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Input */}
        <div className="card space-y-3">
          <h3 className="text-sm font-semibold text-white">Portfolio</h3>
          <HoldingsEditor rows={rows} setRows={setRows} />
          <div>
            <label className="text-xs text-gray-400">Start date</label>
            <input className="input w-full text-xs" value={start} onChange={e => setStart(e.target.value)} placeholder="YYYY-MM-DD" />
          </div>
          <button className="btn-primary w-full" disabled={!ok || bt.isPending} onClick={() => bt.mutate()}>
            {bt.isPending ? 'Backtesting…' : 'Run backtest'}
          </button>
          {bt.isError && <p className="text-xs text-red-400">{String(bt.error)}</p>}
        </div>

        {/* Results */}
        <div className="col-span-2 space-y-4">
          {bt.isPending && <div className="card"><Spinner /></div>}
          {d && (
            <>
              <div className="grid grid-cols-4 gap-3">
                <Tile label="Total return" value={`${d.total_return_pct}%`} accent={d.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'} />
                <Tile label="CAGR" value={`${d.cagr_pct}%`} />
                <Tile label="Sharpe" value={d.sharpe_ratio} />
                <Tile label="Max drawdown" value={`${d.max_drawdown_pct}%`} accent="text-red-400" />
              </div>

              {d.benchmark && (
                <div className="card-sm grid grid-cols-4 gap-4">
                  <div><p className="stat-label">Beat the Nifty by</p>
                    <p className={`stat-value ${d.benchmark.alpha >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {d.benchmark.alpha > 0 ? '+' : ''}{d.benchmark.alpha}%
                    </p></div>
                  <div><p className="stat-label">Nifty return</p><p className="stat-value">{d.benchmark.nifty_total_return}%</p></div>
                  <div><p className="stat-label">Nifty Sharpe</p><p className="stat-value">{d.benchmark.nifty_sharpe}</p></div>
                  <div><p className="stat-label">Significance</p>
                    <p className={`text-sm font-semibold mt-1 ${d.significance_test?.alpha_significant ? 'text-green-400' : 'text-yellow-400'}`}>
                      {d.significance_test?.alpha_significant ? '✓ Significant' : '✗ Not significant'}
                    </p>
                    <p className="text-xs text-gray-500">p={d.significance_test?.p_value}</p></div>
                </div>
              )}

              {/* In / out of sample — the honesty */}
              <div className="grid grid-cols-2 gap-3">
                {[['In-sample', d.in_sample], ['Out-of-sample', d.out_of_sample]].map(([lbl, s]) => s && (
                  <div key={lbl} className="card-sm">
                    <p className="stat-label">{lbl} Sharpe</p>
                    <p className={`stat-value ${(s.sharpe ?? 0) >= 0 ? 'text-white' : 'text-red-400'}`}>{s.sharpe}</p>
                  </div>
                ))}
              </div>
              {d.overfitting_warning && (
                <div className="border border-yellow-700 bg-yellow-900/20 rounded-lg p-3 text-xs">
                  <p className="text-yellow-400 font-semibold">⚠ Overfitting warning</p>
                  <p className="text-yellow-300/70 mt-1">Out-of-sample Sharpe is far below in-sample — the result may not generalise.</p>
                </div>
              )}

              {/* Equity curve */}
              {d.portfolio_chart && (
                <div className="card">
                  <h3 className="text-sm font-semibold text-white mb-2">Portfolio vs Nifty 50</h3>
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                      <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} minTickGap={40} allowDuplicatedCategory={false} />
                      <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} width={64} tickFormatter={v => `₹${(v / 1000).toFixed(0)}k`} />
                      <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                               formatter={v => `₹${Number(v).toLocaleString('en-IN')}`} />
                      <Legend />
                      <Line data={d.portfolio_chart} type="monotone" dataKey="value" name="Portfolio" stroke="#22c55e" strokeWidth={2} dot={false} />
                      {d.benchmark?.nifty_chart && (
                        <Line data={d.benchmark.nifty_chart} type="monotone" dataKey="value" name="Nifty 50" stroke="#9ca3af" strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Per-stock contribution */}
              {d.stock_contributions?.length > 0 && (
                <div className="card">
                  <h3 className="text-sm font-semibold text-white mb-2">Per-stock contribution</h3>
                  <table className="w-full text-xs">
                    <thead><tr className="text-gray-500 text-left">
                      <th className="font-medium">Stock</th><th className="font-medium text-right">Weight</th>
                      <th className="font-medium text-right">Return</th><th className="font-medium text-right">Contribution</th>
                    </tr></thead>
                    <tbody>
                      {d.stock_contributions.map(s => (
                        <tr key={s.ticker} className="border-t border-gray-800">
                          <td className="py-1.5 text-gray-300">{s.ticker.replace('.NS', '')}</td>
                          <td className="py-1.5 text-right text-gray-400">{Math.round(s.weight * 100)}%</td>
                          <td className={`py-1.5 text-right ${s.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>{s.return_pct}%</td>
                          <td className={`py-1.5 text-right ${s.contribution_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>{s.contribution_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
          {!d && !bt.isPending && (
            <div className="card text-sm text-gray-500">Enter your portfolio (summing to 100%) and hit <b>Run backtest</b>.</div>
          )}
        </div>
      </div>
    </div>
  )
}
