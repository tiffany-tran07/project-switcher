import type { AnalysisOutcome } from './api'

export default function AnalysisNotice({ outcome }: { outcome: AnalysisOutcome }) {
  return <section className={`message ${outcome.fallback ? 'warning' : 'success'}`} aria-label="Requirement extraction outcome">
    <strong>Last extraction: {{ ollama: 'local Ollama', deterministic: 'deterministic rules', preserved: 'existing requirements retained' }[outcome.method_used]}{outcome.fallback && ' (fallback)'}</strong>
    <p>{outcome.note}</p>
    <p className="hint">Latest request in this session only; the analysis outcome is not stored in job history. Review requirements before confirmation.</p>
  </section>
}
