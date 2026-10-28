import type { AtsReport, AtsStatus } from './api'

const labels: Record<AtsStatus, string> = {
  present_exact: 'Wording present',
  present_alias: 'Alias present',
  supported_but_missing_from_resume: 'Supported, wording missing',
  no_verified_evidence: 'No direct verified evidence',
}

export default function AtsReadiness({ report, onEvidenceSelect }: { report: AtsReport; onEvidenceSelect?: (id: string) => void }) {
  return <section className="ats-report" aria-label="ATS readiness report">
    <h3>ATS readiness report</h3>
    <p className="hint">Not an employer score prediction. These results apply to this DOCX and the current confirmed job requirements.</p>
    {!report.requirements.length && <p>No confirmed requirements. Review and confirm them in Jobs, then rerun this report.</p>}
    {report.requirements.map((row) => <div className="match-card" key={row.requirement_id}>
      <div className="editor-title"><strong>{row.text}</strong><span className={`match-status ${row.status === 'no_verified_evidence' ? 'unsupported' : row.status === 'supported_but_missing_from_resume' ? 'related' : ''}`}>{labels[row.status]}</span></div>
      <p>{row.reason}</p>
      {row.evidence_ids.map((id, index) => <button type="button" className="match-link" key={id} onClick={() => onEvidenceSelect?.(id)}>Source evidence {index + 1}</button>)}
    </div>)}
    <h4>Formatting checks</h4>
    <ul>{report.formatting.map((check) => <li key={check.name}><strong>{check.name.replaceAll('_', ' ')}: {check.status.replaceAll('_', ' ')}</strong> — {check.message}</li>)}</ul>
    <details><summary>Text extracted for this report</summary><pre>{report.extracted_text}</pre></details>
    <details><summary>Scope and limitations</summary><ul>{report.notes.map((note) => <li key={note}>{note}</li>)}</ul></details>
  </section>
}
