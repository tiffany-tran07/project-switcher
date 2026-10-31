import { useEffect, useState } from 'react'
import { save } from './api'
import { archiveItems, loadArchive, type ArchiveData, type ArchiveItem, type ArchiveKind } from './archiveRecords'

const groups: { kind: ArchiveKind; heading: string; singular: string }[] = [
  { kind: 'experiences', heading: 'Archived experiences', singular: 'experience' },
  { kind: 'projects', heading: 'Archived projects', singular: 'project' },
  { kind: 'skills', heading: 'Archived skills', singular: 'skill' },
  { kind: 'evidence', heading: 'Archived evidence', singular: 'evidence' },
]

export default function ArchiveWorkspace({ onRestored }: { onRestored: () => Promise<void> }) {
  const [data, setData] = useState<ArchiveData | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    loadArchive().then((value) => { if (active) { setData(value); setError('') } })
      .catch((cause) => { if (active) setError(String(cause)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reload])

  async function restore(item: ArchiveItem) {
    if (busy || loading || item.blocked_reason || !window.confirm('Restore this career record? Saved resume versions will not change.')) return
    setBusy(true); setError(''); setNotice('')
    let restored = false
    try {
      await save(`/${item.kind}/${encodeURIComponent(item.id)}`, 'PATCH', { archived: false })
      restored = true
      setData(await loadArchive())
      await onRestored()
      setNotice('Record restored. Saved resume versions were not changed.')
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : String(cause)
      setError(restored ? `Restored, but refreshing failed. Refresh this view before retrying. ${detail}` : detail)
    } finally { setBusy(false) }
  }

  return <div className="archive-workspace">
    <section className="editor-card"><h2>Recover career records</h2>
      <p>Restore archived experiences, projects, skills, and evidence without changing their saved contents or historical resume versions.</p>
      <p className="hint">Restore linked experiences before projects, and linked projects before evidence. Restoration keeps the saved evidence state; it never verifies draft or rejected claims. Current source eligibility is still checked before drafting.</p>
      <label>Search archived records<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search titles, claims, skills, or source context" /></label>
      <div className="actions"><button type="button" className="secondary" disabled={busy || loading} onClick={() => { setError(''); setLoading(true); setReload((value) => value + 1) }}>Refresh archive</button></div>
    </section>
    {busy && <p role="status">Restoring record…</p>}
    {error && <p className="message error" role="alert">{error}</p>}
    {notice && <p className="message success" role="status">{notice}</p>}
    {data ? <ArchiveRecords items={archiveItems(data)} query={query} busy={busy || loading} onRestore={(item) => { void restore(item) }} /> : !error && <p role="status">Loading archived records…</p>}
  </div>
}

export function ArchiveRecords({ items, query, busy, onRestore }: { items: ArchiveItem[]; query: string; busy: boolean; onRestore: (item: ArchiveItem) => void }) {
  const normalized = query.trim().toLocaleLowerCase()
  return <div className="archive-grid" aria-busy={busy}>{groups.map((group) => {
    const records = items.filter((item) => item.kind === group.kind)
    const matches = records.filter((item) => `${item.label} ${item.detail}`.toLocaleLowerCase().includes(normalized))
    return <section className="editor-card" aria-label={group.heading} key={group.kind}>
      <h2>{group.heading} ({records.length})</h2>
      {matches.length ? matches.map((item) => <article className="archive-record" aria-label={`Archived ${group.singular}: ${item.label}`} key={item.id}>
        <h3>{item.label}</h3><p>{item.detail}</p><small>Archived {item.archived_at.slice(0, 10)}</small>
        {item.blocked_reason && <p className="archive-block">{item.blocked_reason}</p>}
        <div className="actions"><button type="button" disabled={busy || Boolean(item.blocked_reason)} onClick={() => onRestore(item)}>Restore {group.singular}</button></div>
      </article>) : <p className="empty">{records.length ? 'No archived records match this search.' : 'No archived records in this category.'}</p>}
    </section>
  })}</div>
}
