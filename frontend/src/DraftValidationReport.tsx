import type { DraftValidation } from './api'

export default function DraftValidationReport({ report }: { report: DraftValidation }) {
  return (
    <section className={`message ${report.valid ? 'success' : 'error'}`} aria-live="polite">
      <strong>{report.valid ? 'Source checks passed.' : 'Fix these issues before saving:'}</strong>
      {report.issues.map((issue, index) => (
        <p key={`${issue.position}-${issue.code}-${index}`}>
          Bullet {issue.position + 1}: {issue.message}
        </p>
      ))}
      <p className="hint">
        Saving rechecks current evidence. This is a source check, not an ATS report.
      </p>
    </section>
  )
}
