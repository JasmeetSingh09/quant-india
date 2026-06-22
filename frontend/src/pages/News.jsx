import { useQuery } from '@tanstack/react-query'
import { getMacroNews, getMarketNews } from '../api'
import Spinner from '../components/Spinner'
import { ExternalLink, AlertTriangle } from 'lucide-react'

function NewsArticle({ article }) {
  const mins = article.published_minutes_ago
  const time = mins < 60 ? `${mins}m ago` : `${Math.floor(mins/60)}h ago`
  const impacts = article.macro_impacts || []

  return (
    <div className="card hover:border-gray-600 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <a href={article.url} target="_blank" rel="noreferrer"
            className="text-sm font-semibold hover:text-green-400 transition-colors leading-snug flex items-start gap-1">
            {article.title}
            <ExternalLink size={11} className="shrink-0 mt-0.5 text-gray-500" />
          </a>
          <p className="text-xs text-gray-500 mt-1.5 line-clamp-2">{article.description}</p>
          <div className="flex items-center gap-2 mt-2">
            <span className="badge-blue">{article.source}</span>
            <span className="text-xs text-gray-600">{time}</span>
            <span className="text-xs text-gray-600 italic">{article.newsapi_delay_note}</span>
          </div>
        </div>
      </div>

      {/* Macro impacts */}
      {impacts.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <p className="text-xs font-semibold text-yellow-400 flex items-center gap-1 mb-2">
            <AlertTriangle size={11}/> Macro Impact Detected
          </p>
          {impacts.map((imp, i) => (
            <div key={i} className="mb-2 last:mb-0">
              <p className="text-xs font-medium text-gray-300">{imp.sector}</p>
              <p className="text-xs text-gray-500 mt-0.5">{imp.causal_chain}</p>
              <div className="flex gap-2 mt-1">
                {imp.winners?.length > 0 && (
                  <div className="flex gap-1 flex-wrap">
                    {imp.winners.map(t => (
                      <span key={t} className="badge-green text-xs">{t.replace('.NS','')}</span>
                    ))}
                  </div>
                )}
                {imp.losers?.length > 0 && (
                  <div className="flex gap-1 flex-wrap">
                    {imp.losers.map(t => (
                      <span key={t} className="badge-red text-xs">{t.replace('.NS','')}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function News() {
  const { data: macro,  isLoading: ml } = useQuery({ queryKey: ['macroNews'],  queryFn: getMacroNews,  refetchInterval: 300000 })
  const { data: market, isLoading: mkl } = useQuery({ queryKey: ['marketNews'], queryFn: getMarketNews, refetchInterval: 300000 })

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Financial News</h1>
      <p className="text-xs text-gray-500">
        NewsAPI free tier has ~60 min delay. Published times shown above articles.
      </p>

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-yellow-400 rounded-full"></span>
            Macro News
            <span className="text-xs text-gray-500 font-normal">RBI · Crude · Rupee · FII · Inflation</span>
          </h2>
          {ml ? <Spinner size="sm" /> : (
            <div className="space-y-3">
              {macro?.articles?.slice(0,8).map((a,i) => <NewsArticle key={i} article={a} />)}
            </div>
          )}
        </div>

        <div>
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <span className="w-2 h-2 bg-blue-400 rounded-full"></span>
            Market Wide
            <span className="text-xs text-gray-500 font-normal">Nifty · FII/DII · SEBI</span>
          </h2>
          {mkl ? <Spinner size="sm" /> : (
            <div className="space-y-3">
              {market?.articles?.slice(0,8).map((a,i) => <NewsArticle key={i} article={a} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
