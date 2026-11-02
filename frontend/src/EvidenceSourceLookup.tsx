import { useEffect, useState } from 'react'
import { loadEvidenceSource, type Evidence } from './api'

export type SourceLookup = { status: 'loading' } | { status: 'failed'; message: string } | { status: 'found'; source: Evidence }
type Actions = { busy: boolean; onRefresh: () => void; onOpenArchive: () => void }
export default function EvidenceSourceLookup({ evidenceId, ...actions }: Actions & { evidenceId: string }) {
  const [lookup, setLookup] = useState<SourceLookup>({ status: 'loading' })
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    loadEvidenceSource(evidenceId).then((source) => { if (active) setLookup({ status: 'found', source }) })
      .catch((cause) => { if (active) setLookup({ status: 'failed', message: cause instanceof Error ? cause.message : String(cause) }) })
    return () => { active = false }
  }, [evidenceId, retry])
  return <EvidenceSourceCard {...actions} lookup={lookup} onRetry={() => { setLookup({ status: 'loading' }); setRetry((value) => value + 1) }} />
}

export function EvidenceSourceCard({ lookup, busy, onRefresh, onOpenArchive, onRetry }: Actions & { lookup: SourceLookup; onRetry: () => void }) {
  return <section className="editor-card source-lookup" aria-label="Evidence source lookup">
    <h2>{lookup.status === 'found' && lookup.source.archived_at ? 'Archived evidence source' : 'Source not in the active library'}</h2>
    <p>Saved resume snapshots and exports are unchanged. This link never creates a new evidence record or restores a source automatically.</p>
    {lookup.status === 'loading' && <p role="status">Loading the current source record…</p>}
    {lookup.status === 'failed' && <><p role="alert">Could not load this source. It may be missing, or the API may be unavailable. {lookup.message}</p>
      <button type="button" disabled={busy} onClick={onRetry}>Retry source lookup</button></>}
    {lookup.status === 'found' && <>
      <p className="hint">Current library record—not the historical snapshot shown in your saved resume.</p>
      <h3>{lookup.source.claim}</h3>
      <p>Current library state: {lookup.source.state}</p>
      <p>Current source note: {lookup.source.source_note || 'No source note recorded.'}</p>
      {lookup.source.metrics.map((metric) => <p key={metric.id}>Metric: {metric.name} · {metric.value} {metric.unit} · {metric.source_note}</p>)}
      <p>{lookup.source.archived_at ? 'This source is archived and cannot be used in a new draft. Open Archive to review recovery; linked experiences and projects may need restoring first.' : 'The source is no longer in this view’s cached list. Refresh the career library before editing it.'}</p>
    </>}
    <div className="actions"><button type="button" className="secondary" disabled={busy} onClick={onRefresh}>Refresh career library</button>
      <button type="button" className="secondary" disabled={busy} onClick={onOpenArchive}>Open Archive</button></div>
  </section>
}
