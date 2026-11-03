import type { Evidence, ResumeEvidenceStatus } from './api'
import { eligibleEvidence } from './resumeEligibility'

type Props = {
  evidence: Evidence[]; statuses: ResumeEvidenceStatus[] | null; selected: string[]
  checking: boolean; error: string; busy: boolean
  onRefresh: () => void; onSelect: (item: Evidence, checked: boolean) => void; onReview: (id: string) => void
}
export default function ResumeEvidencePicker({ evidence, statuses, selected, checking, error, busy, onRefresh, onSelect, onReview }: Props) {
  const available = eligibleEvidence(evidence, checking || error ? null : statuses)
  const availableIds = new Set(available.map((row) => row.id))
  const blocked = evidence.filter((row) => !availableIds.has(row.id))
  return <section aria-label="Resume source availability">
    <p className="hint">The API checks verification, linked experiences/projects, and attached source files. This is a point-in-time check, not wording/section approval. Saving rechecks every source. Refresh after changes outside this view.</p>
    <button type="button" className="secondary" disabled={busy || checking} onClick={onRefresh}>Refresh source availability</button>
    {checking && <p role="status">Checking current source availability…</p>}
    {error && <p role="alert" className="message error">Could not check source availability. Your working edits are kept. {error}</p>}
    {available.map((item) => <label className="inline-check" key={item.id}><input type="checkbox" disabled={busy} checked={selected.includes(item.id)} onChange={(event) => onSelect(item, event.target.checked)} />{item.claim}</label>)}
    {!checking && !error && !available.length && <p className="empty">No currently eligible sources. Review verification, linked context, and supporting files in the library.</p>}
    {!checking && !error && blocked.length > 0 && <details><summary>Unavailable sources ({blocked.length})</summary>
      {blocked.map((item) => <div className="snapshot-bullet" key={item.id}>
        <p>{item.claim}</p><small>{statuses?.find((row) => row.evidence_id === item.id)?.problem ?? 'Source is not in the current availability result.'}</small>
        <button type="button" className="match-link" disabled={busy} onClick={() => onReview(item.id)}>Review source</button>
      </div>)}
    </details>}
    {selected.filter((id) => !evidence.some((item) => item.id === id)).map((id) => <p key={id}>A selected source is not in the active library. <button type="button" className="match-link" disabled={busy} onClick={() => onReview(id)}>Review selected source</button></p>)}
  </section>
}
