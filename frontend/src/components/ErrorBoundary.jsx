import { Component } from 'react'
import { AlertTriangle, RotateCw } from 'lucide-react'

/**
 * ErrorBoundary — the difference between a broken panel and a blank app.
 *
 * React unmounts the entire tree when a render throws. With no boundary
 * anywhere, one bad property access in one component turns the whole page
 * white: no message, no recovery, nothing to report. That is what "the app
 * keeps blanking out" is.
 *
 * This catches it and keeps the failure local. It also shows the error rather
 * than hiding it — a user who can read "Cannot read properties of undefined
 * (reading 'p50')" can tell us something useful, and a user staring at a white
 * screen cannot.
 *
 * Reset is per-boundary, so recovering one panel does not reload the app and
 * lose whatever else was on screen.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, info: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    this.setState({ info })
    // Keep it in the console too: a screenshot of this panel plus the console
    // trace is usually enough to find the cause without reproducing it.
    console.error('[ErrorBoundary]', this.props.name || 'unnamed', error, info)
  }

  render() {
    const { error, info } = this.state
    if (!error) return this.props.children

    // "The page section" read awkwardly because the App-level boundary is named
    // "page". Panels get "The X panel"; the page-level one says so directly.
    const label = !this.props.name ? 'This section'
      : this.props.name === 'page' ? 'This page'
      : `The ${this.props.name} panel`

    return (
      <div className="card border border-red-800/70 bg-red-950/20 space-y-2">
        <p className="text-sm font-medium text-red-200 flex items-center gap-2">
          <AlertTriangle size={15} className="shrink-0" />
          {label} could not be displayed
        </p>
        <p className="text-xs text-gray-400 leading-relaxed">
          Something went wrong rendering this panel. The rest of the page still
          works — nothing you have saved is affected.
        </p>
        {/* Shown without needing a click. Someone reporting this should not have
            to find a toggle before they can tell us anything useful. */}
        <p className="text-[11px] font-mono text-red-200/80 break-words">
          {String(error?.message || error)}
        </p>

        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => this.setState({ error: null, info: null })}
                  className="btn-ghost text-xs flex items-center gap-1.5">
            <RotateCw size={12} /> Try this section again
          </button>
          <button onClick={() => window.location.reload()} className="btn-ghost text-xs">
            Reload the page
          </button>
        </div>

        {/* Shown, not hidden. A reported error message is worth more than a
            tidy screen, especially during a pilot. */}
        <details className="text-[11px] text-gray-500">
          <summary className="cursor-pointer hover:text-gray-300">
            Technical detail (useful if you report this)
          </summary>
          <pre className="mt-1.5 whitespace-pre-wrap break-words text-[10px] text-gray-500 max-h-40 overflow-y-auto">
            {String(error?.message || error)}
            {info?.componentStack ? '\n' + info.componentStack.split('\n').slice(0, 6).join('\n') : ''}
          </pre>
        </details>
      </div>
    )
  }
}
