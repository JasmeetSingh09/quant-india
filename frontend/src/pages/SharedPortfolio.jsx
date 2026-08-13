import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { getShared } from '../api'
import Spinner from '../components/Spinner'
import { Zap } from 'lucide-react'

const pct = v => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`

/**
 * SharedPortfolio — the public page a shared link opens.
 *
 * Deliberately outside the auth gate: a link that demands a login before
 * showing anything is not shareable, and the whole point is that someone with
 * no account can see the result and want one.
 *
 * The token is the credential, so there is nothing to sign in to. The payload
 * carries holdings, weights and percentage returns only — no owner, no email,
 * no rupee amounts, enforced server-side rather than by hiding fields here.
 */
export default function SharedPortfolio() {
  const { token } = useParams()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['shared', token],
    queryFn: () => getShared(token),
    retry: false,
  })

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      <header className="flex items-center justify-between px-6 py-4 max-w-3xl mx-auto">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center">
            <Zap size={15} className="text-white" />
          </div>
          <span className="font-bold text-white tracking-tight">Quant India</span>
        </Link>
        <Link to="/" className="btn-primary text-sm">Build your own</Link>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8">
        {isLoading && <div className="card"><Spinner /></div>}

        {isError && (
          <div className="card text-center py-10">
            <p className="text-gray-300">{String(error)}</p>
            <Link to="/" className="btn-ghost text-sm mt-4 inline-block">
              Go to Quant India
            </Link>
          </div>
        )}

        {data && (
          <>
            <div className="card">
              <p className="text-xs text-gray-500 uppercase tracking-wider">
                A shared paper portfolio
              </p>
              <h1 className="text-2xl font-bold text-white mt-1">{data.name}</h1>
              <div className="flex items-baseline gap-3 mt-3 flex-wrap">
                <span className={`text-4xl font-bold font-mono ${
                  data.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {pct(data.return_pct)}
                </span>
                <span className="text-sm text-gray-500">
                  {data.n_positions} stocks
                  {data.days_running != null && ` · ${data.days_running} days`}
                </span>
              </div>
            </div>

            <div className="card mt-4">
              <h2 className="font-semibold mb-3 text-sm">What it holds</h2>
              <div className="table-wrap">
                <table className="w-full min-w-[20rem] text-sm">
                  <thead>
                    <tr className="text-gray-500 text-xs border-b border-gray-800">
                      <th className="text-left py-2 font-medium">Stock</th>
                      <th className="text-right font-medium">Weight</th>
                      <th className="text-right font-medium">Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.holdings.map(h => (
                      <tr key={h.name} className="border-b border-gray-900 last:border-0">
                        <td className="py-2 font-mono">{h.name}</td>
                        <td className="text-right font-mono text-gray-400">{h.weight_pct}%</td>
                        <td className={`text-right font-mono ${
                          h.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {pct(h.return_pct)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[11px] text-gray-600 mt-3">{data.disclaimer}</p>
            </div>

            <div className="card mt-4 text-center">
              <p className="text-sm text-gray-300">
                Build a portfolio, see how much you could lose, and paper-trade it free.
              </p>
              <Link to="/" className="btn-primary text-sm mt-3 inline-block">
                Try Quant India
              </Link>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
