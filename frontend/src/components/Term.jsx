import { GLOSSARY } from '../glossary'

/**
 * Term — jargon word with dotted underline. Hover to see a plain-English definition.
 *   <Term k="sharpe" />
 *   <Term k="sharpe">Sharpe Ratio</Term>
 *   <InfoTip k="sharpe" />   ← just the "?" icon
 */

const LABELS = {
  sharpe: 'Sharpe ratio', sortino: 'Sortino ratio', calmar: 'Calmar ratio',
  cagr: 'CAGR', max_drawdown: 'Max drawdown', volatility: 'Volatility',
  var95: 'VaR (95%)', cvar95: 'CVaR (95%)', alpha: 'Alpha', beta: 'Beta',
  cointegration: 'Cointegration', hedge_ratio: 'Hedge ratio', zscore: 'Z-score',
  half_life: 'Half-life', market_neutral: 'Market-neutral', pvalue: 'P-value',
  fama_french: 'Fama-French', smb: 'Size (SMB)', hml: 'Value (HML)',
  market_beta: 'Market beta', r_squared: 'R²', significant: 'Significant',
  hrp: 'HRP', markowitz: 'Markowitz', black_litterman: 'Black-Litterman',
  efficient_frontier: 'Efficient frontier', monte_carlo: 'Monte Carlo',
  bootstrap: 'Bootstrap', fat_tails: 'Fat tails', regime: 'Regime',
  alpha_score: 'Alpha score', pe_ratio: 'P/E ratio', roe: 'ROE',
}

const tooltipCls = `
  pointer-events-none absolute z-50
  left-1/2 -translate-x-1/2 bottom-full mb-2
  w-64 p-3 rounded-lg
  bg-gray-800 border border-gray-700
  text-gray-200 text-xs font-normal leading-relaxed
  normal-case tracking-normal
  opacity-0 group-hover:opacity-100
  transition-opacity duration-150
  shadow-xl
`

export function Term({ k, children, className = '' }) {
  const def  = GLOSSARY[k]
  const text = children || LABELS[k] || k
  if (!def) return <span className={className}>{text}</span>
  return (
    <span className={`relative group inline-block ${className}`}>
      <span className="border-b border-dotted border-gray-500 cursor-help">{text}</span>
      <span className={tooltipCls}>{def}</span>
    </span>
  )
}

export function InfoTip({ k }) {
  const def = GLOSSARY[k]
  if (!def) return null
  return (
    <span className="relative group inline-block ml-1 align-middle">
      <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full
                       bg-gray-700 hover:bg-gray-600 text-gray-400 hover:text-gray-200
                       text-[9px] cursor-help leading-none transition-colors">?</span>
      <span className={tooltipCls}>{def}</span>
    </span>
  )
}

export default Term
