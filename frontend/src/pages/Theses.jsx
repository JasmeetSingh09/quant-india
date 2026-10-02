import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listTheses, getThesis, createThesis, reviseThesis, closeThesis, deleteThesis } from '../api'
import Spinner from '../components/Spinner'
import { signalLabel } from '../signalLabel'

/**
 * Theses — write down why you hold a view, so a later review can say which part
 * was wrong. Spec: docs/PROPOSAL_PRODUCT_ADDITIONS_2026-09-23.md (#4).
 *
 * The user's own notes. The app never suggests a thesis and never rates one;
 * it flags measurable triggers and leaves every decision to the user.
 */
const STANCES = ['expect to outperform', 'expect to underperform', 'watching']
const RANKS = ['Ranked high', 'Middle', 'Ranked low', 'Bottom ranked']
const CLOSE_REASONS = ['trigger met', 'horizon reached', 'changed my mind']
// api.js rejects with the server's message as plain text.
const errText = e => (typeof e === 'string' ? e : e?.response?.data?.detail || e?.message) || 'Something went wrong.'
const day = iso => (iso || '').slice(0, 10)

function blank() {
  return { ticker: '', stance: STANCES[0], horizon_months: 12, reasons: '', evidence: '',
           bear_case: '', risks: '', what_changed: '', invalidation: [{ text: '', kind: '', level: '' }] }
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="text-xs text-gray-400">{label}</span>
      {hint && <span className="text-[11px] text-gray-600 ml-2">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  )
}

function TriggerEditor({ triggers, onChange }) {
  const set = (i, patch) => onChange(triggers.map((t, j) => (j === i ? { ...t, ...patch } : t)))
  return (
    <div className="space-y-2">
      {triggers.map((t, i) => (
        <div key={i} className="flex flex-col sm:flex-row gap-2">
          <input className="input flex-1" value={t.text} placeholder="What would make me wrong"
                 onChange={e => set(i, { text: e.target.value })} aria-label={`Trigger ${i + 1}`} />
          <select className="input sm:w-40" value={t.kind} onChange={e => set(i, { kind: e.target.value, level: '' })}
                  aria-label={`Trigger ${i + 1} measurable part`}>
            <option value="">Not measurable</option>
            <option value="price_below">Price closes below</option>
            <option value="rank_at_or_below">Rank falls to</option>
          </select>
          {t.kind === 'price_below' && (
            <input className="input sm:w-28 font-mono" type="number" min="0" step="any" value={t.level}
                   placeholder="Rs" onChange={e => set(i, { level: e.target.value })} aria-label="Price level" />
          )}
          {t.kind === 'rank_at_or_below' && (
            <select className="input sm:w-36" value={t.level} onChange={e => set(i, { level: e.target.value })} aria-label="Rank level">
              <option value="">Choose…</option>
              {RANKS.map(r => <option key={r} value={r}>{r} or below</option>)}
            </select>
          )}
          {triggers.length > 1 && (
            <button type="button" className="text-xs text-gray-500 hover:text-gray-300 px-2"
                    onClick={() => onChange(triggers.filter((_, j) => j !== i))}>Remove</button>
          )}
        </div>
      ))}
      {triggers.length < 10 && (
        <button type="button" className="text-xs text-sky-400 hover:text-sky-300"
                onClick={() => onChange([...triggers, { text: '', kind: '', level: '' }])}>+ Add another trigger</button>
      )}
    </div>
  )
}

function ThesisForm({ initial, revising, onSubmit, pending, error, onCancel }) {
  const [f, setF] = useState(initial)
  const set = patch => setF(prev => ({ ...prev, ...patch }))
  const submit = e => {
    e.preventDefault()
    onSubmit({ ...f, invalidation: f.invalidation.filter(t => t.text.trim()).map(t =>
      t.kind ? { text: t.text, kind: t.kind, level: t.kind === 'price_below' ? Number(t.level) : t.level } : { text: t.text }) })
  }
  return (
    <form onSubmit={submit} className="card space-y-3">
      <h2 className="font-semibold">{revising ? 'Revise this thesis' : 'New thesis'}</h2>
      {!revising && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="Ticker"><input className="input w-full font-mono" value={f.ticker} placeholder="TCS"
                                       onChange={e => set({ ticker: e.target.value })} /></Field>
          <Field label="Stance">
            <select className="input w-full" value={f.stance} onChange={e => set({ stance: e.target.value })}>
              {STANCES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Horizon (months)"><input className="input w-full" type="number" min="1" max="60" value={f.horizon_months}
                                                 onChange={e => set({ horizon_months: e.target.value })} /></Field>
        </div>
      )}
      {revising && (
        <Field label="What changed" hint="required: what made you revise">
          <input className="input w-full" value={f.what_changed} onChange={e => set({ what_changed: e.target.value })} />
        </Field>
      )}
      <Field label="Reasons" hint="required"><textarea className="input w-full h-20" value={f.reasons} onChange={e => set({ reasons: e.target.value })} /></Field>
      <Field label="Evidence"><textarea className="input w-full h-16" value={f.evidence} onChange={e => set({ evidence: e.target.value })} /></Field>
      <Field label="The bear case" hint="required: the best argument against you">
        <textarea className="input w-full h-16" value={f.bear_case} onChange={e => set({ bear_case: e.target.value })} />
      </Field>
      <Field label="Risks"><textarea className="input w-full h-14" value={f.risks} onChange={e => set({ risks: e.target.value })} /></Field>
      <Field label="What would make me wrong" hint="at least one; a measurable one is checked against prices and nightly ranks">
        <TriggerEditor triggers={f.invalidation} onChange={inv => set({ invalidation: inv })} />
      </Field>
      {error && <p className="text-sm text-red-400">{errText(error)}</p>}
      <div className="flex gap-2">
        <button className="btn-primary text-sm" disabled={pending}>{pending ? 'Saving…' : revising ? 'Save revision' : 'Open thesis'}</button>
        {onCancel && <button type="button" className="text-sm text-gray-400 px-3" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  )
}

function Snapshot({ s }) {
  if (!s) return null
  const bits = []
  if (s.price != null) bits.push(`price ${Number(s.price).toLocaleString('en-IN')}${s.price_date ? ` (${s.price_date})` : ''}`)
  if (s.signal) bits.push(`rank ${signalLabel(s.signal)}`)
  if (s.alpha_score != null) bits.push(`score ${Number(s.alpha_score).toFixed(0)}`)
  return <p className="text-[11px] text-gray-500">When written: {bits.join(' · ') || 'no market data recorded'}</p>
}

function Detail({ id, onGone }) {
  const qc = useQueryClient()
  const { data: t, isLoading, error } = useQuery({ queryKey: ['thesis', id], queryFn: () => getThesis(id) })
  const [mode, setMode] = useState(null)
  const [closeReason, setCloseReason] = useState(CLOSE_REASONS[0])
  const refresh = () => { qc.invalidateQueries({ queryKey: ['thesis', id] }); qc.invalidateQueries({ queryKey: ['theses'] }) }
  const revise = useMutation({ mutationFn: reviseThesis, onSuccess: () => { setMode(null); refresh() } })
  const close = useMutation({ mutationFn: closeThesis, onSuccess: () => { setMode(null); refresh() } })
  const del = useMutation({ mutationFn: deleteThesis, onSuccess: () => { qc.invalidateQueries({ queryKey: ['theses'] }); onGone() } })

  if (isLoading) return <div className="card flex items-center gap-2"><Spinner /><span className="text-sm text-gray-400">Loading…</span></div>
  if (error) return <p className="text-sm text-red-400">{errText(error)}</p>
  if (!t) return null
  const latest = t.revisions[t.revisions.length - 1]
  const statuses = t.trigger_status || []
  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <h2 className="text-lg font-semibold font-mono">{t.ticker.replace('.NS', '')}</h2>
          <span className={`text-xs px-2 py-0.5 rounded border ${t.status === 'open' ? 'border-sky-700 text-sky-300' : 'border-gray-700 text-gray-400'}`}>
            {t.status === 'open' ? 'Open' : `Closed ${day(t.closed_at)}: ${t.close_reason}`}
          </span>
        </div>
        <p className="text-sm text-gray-300">{t.stance} · {t.horizon_months} months · opened {day(t.created_at)}</p>
        <div className="grid sm:grid-cols-2 gap-3 text-sm">
          <div><p className="stat-label">Reasons</p><p className="text-gray-200 whitespace-pre-wrap">{latest.reasons}</p></div>
          <div><p className="stat-label">The bear case</p><p className="text-gray-200 whitespace-pre-wrap">{latest.bear_case}</p></div>
          {latest.evidence && <div><p className="stat-label">Evidence</p><p className="text-gray-300 whitespace-pre-wrap">{latest.evidence}</p></div>}
          {latest.risks && <div><p className="stat-label">Risks</p><p className="text-gray-300 whitespace-pre-wrap">{latest.risks}</p></div>}
        </div>
        <div>
          <p className="stat-label">What would make me wrong</p>
          <ul className="space-y-1 mt-1">
            {latest.invalidation.map((tr, i) => {
              const st = statuses[i]
              return (
                <li key={i} className="text-sm flex flex-wrap items-center gap-2">
                  <span className="text-gray-200">{tr.text}</span>
                  {tr.kind && st?.met === false && <span className="text-[11px] text-gray-500">checked: not met</span>}
                  {tr.kind && st?.met == null && <span className="text-[11px] text-gray-500">{st?.detail || 'not checked yet'}</span>}
                  {st?.met && <span className="text-[11px] px-1.5 py-0.5 rounded border border-amber-700 text-amber-300">met on {st.met_on}: {st.detail}</span>}
                </li>
              )
            })}
          </ul>
          <p className="text-[11px] text-gray-600 mt-1">A met trigger is a flag for you to review. The app never closes a thesis by itself.</p>
        </div>
        {t.status === 'open' && !mode && (
          <div className="flex gap-3 flex-wrap pt-1">
            <button className="btn-primary text-sm" onClick={() => setMode('revise')}>Revise</button>
            <button className="text-sm text-gray-300 border border-gray-700 rounded px-3" onClick={() => setMode('close')}>Close</button>
            <button className="text-sm text-gray-500 hover:text-red-400 px-2" onClick={() => setMode('delete')}>Delete</button>
          </div>
        )}
        {t.status !== 'open' && !mode && (
          <button className="text-sm text-gray-500 hover:text-red-400" onClick={() => setMode('delete')}>Delete</button>
        )}
        {mode === 'close' && (
          <div className="flex gap-2 flex-wrap items-center">
            <select className="input" value={closeReason} onChange={e => setCloseReason(e.target.value)} aria-label="Reason for closing">
              {CLOSE_REASONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <button className="btn-primary text-sm" disabled={close.isPending} onClick={() => close.mutate({ id, reason: closeReason })}>Close thesis</button>
            <button className="text-sm text-gray-400 px-2" onClick={() => setMode(null)}>Cancel</button>
            {close.error && <span className="text-sm text-red-400">{errText(close.error)}</span>}
          </div>
        )}
        {mode === 'delete' && (
          <div className="flex gap-2 flex-wrap items-center text-sm">
            <span className="text-gray-300">Delete this thesis and all {t.revisions.length} revision{t.revisions.length > 1 ? 's' : ''}? This cannot be undone.</span>
            <button className="text-sm border border-red-800 text-red-300 rounded px-3 py-1" disabled={del.isPending} onClick={() => del.mutate(id)}>Delete</button>
            <button className="text-sm text-gray-400 px-2" onClick={() => setMode(null)}>Keep it</button>
          </div>
        )}
      </div>

      {mode === 'revise' && (
        <ThesisForm revising pending={revise.isPending} error={revise.error} onCancel={() => setMode(null)}
                    initial={{ ...blank(), ...latest, what_changed: '',
                               invalidation: latest.invalidation.map(tr => ({ text: tr.text, kind: tr.kind || '', level: tr.level ?? '' })) }}
                    onSubmit={body => revise.mutate({ id, body })} />
      )}

      <div className="card">
        <h3 className="font-semibold mb-2">History</h3>
        <ol className="space-y-3">
          {[...t.revisions].reverse().map((r, i) => (
            <li key={r.id} className="border-l-2 border-gray-700 pl-3">
              <p className="text-xs text-gray-400">{day(r.created_at)} · {i === t.revisions.length - 1 ? 'opened' : `revised: ${r.what_changed}`}</p>
              <Snapshot s={r.snapshot} />
              <p className="text-sm text-gray-300 mt-1 whitespace-pre-wrap">{r.reasons}</p>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}

export default function Theses() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['theses'], queryFn: listTheses })
  const [selected, setSelected] = useState(null)
  const [creating, setCreating] = useState(false)
  const create = useMutation({ mutationFn: createThesis, onSuccess: t => {
    qc.invalidateQueries({ queryKey: ['theses'] }); setCreating(false); setSelected(t.id) } })
  const theses = data?.theses || []

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Theses</h1>
          <p className="text-gray-400 text-sm mt-0.5 max-w-2xl">
            Write down why you hold a view, the best case against it, and what would prove you wrong.
            Revisions are added, never edited, so you can see later what you believed and when.
          </p>
        </div>
        {!creating && <button className="btn-primary text-sm" onClick={() => { setCreating(true); setSelected(null) }}>New thesis</button>}
      </div>

      {creating && <ThesisForm initial={blank()} pending={create.isPending} error={create.error}
                               onSubmit={body => create.mutate(body)} onCancel={() => setCreating(false)} />}

      {isLoading && <div className="card flex items-center gap-2"><Spinner /><span className="text-sm text-gray-400">Loading…</span></div>}
      {error && <p className="text-sm text-red-400">{errText(error)}</p>}
      {!isLoading && !error && theses.length === 0 && !creating && (
        <p className="text-sm text-gray-500">No theses yet. They are private to you.</p>
      )}

      {theses.length > 0 && (
        <div className="grid lg:grid-cols-[260px_1fr] gap-4 items-start">
          <ul className="card p-2 space-y-1" aria-label="Your theses">
            {theses.map(t => (
              <li key={t.id}>
                <button onClick={() => { setSelected(t.id); setCreating(false) }}
                        className={`w-full text-left rounded px-2 py-1.5 text-sm ${selected === t.id ? 'bg-gray-800' : 'hover:bg-gray-800/60'}`}>
                  <span className="font-mono">{t.ticker.replace('.NS', '')}</span>
                  <span className="text-[11px] text-gray-500 ml-2">{t.stance} · {t.status}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected ? <Detail id={selected} onGone={() => setSelected(null)} />
                    : <p className="text-sm text-gray-500">Choose a thesis to see its history.</p>}
        </div>
      )}
      <p className="text-[11px] text-gray-600">Your notes, private to you. The app never suggests a thesis or rates one as right or wrong.</p>
    </div>
  )
}
