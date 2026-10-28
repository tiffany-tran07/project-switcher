import { useEffect, useRef, useState } from 'react'
import { previewResume } from './api'

export default function ResumeIntake() {
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState('')
  const [source, setSource] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const request = useRef<AbortController | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  useEffect(() => () => request.current?.abort(), [])

  async function preview() {
    if (!file) return
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setBusy(true); setError('')
    try {
      const result = await previewResume(file, controller.signal)
      if (!controller.signal.aborted) {
        setText(result.text); setSource(result.filename); setWarnings(result.warnings)
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause))
    } finally { if (!controller.signal.aborted) setBusy(false) }
  }

  function clear() {
    setFile(null); setText(''); setSource(''); setWarnings([]); setError('')
    if (fileInput.current) fileInput.current.value = ''
  }

  return <div className="editor-stack intake-workspace">
    <section className="editor-card"><h2>Preview an existing resume</h2>
      <p>Choose a DOCX or UTF-8 text file, or paste text below. PDF intake is not available yet; copy its text into the editor instead.</p>
      <p className="hint">File previews are processed by your configured backend (localhost by default). No AI is called, files are not saved, and no career records are created or verified.</p>
      <label>Resume file (.docx or .txt, maximum 5 MB)<input ref={fileInput} type="file" accept=".docx,.txt" disabled={busy} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError('') }} /></label>
      <div className="actions"><button type="button" disabled={busy || !file} onClick={() => { void preview() }}>{busy ? 'Reading resume…' : 'Preview file text'}</button><button type="button" className="secondary" disabled={busy} onClick={clear}>Clear preview</button></div>
      {error && <p className="message error" role="alert">{error}</p>}
      {warnings.length > 0 && <ul className="intake-warnings">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
    </section>
    <section className="editor-card"><h2>Review or paste resume text</h2>
      {source && <p>Preview source: {source}</p>}
      <label>Resume text<textarea className="intake-text" maxLength={100000} disabled={busy} value={text} onChange={(event) => setText(event.target.value)} placeholder="Paste your resume here, or preview a file above." /></label>
      <p className="hint">Preview text is temporary and is cleared when you leave this page. Review dates, metrics, symbols, and table reading order; extraction may omit text boxes, headers, or images.</p>
      <h3>Next: turn reviewed claims into evidence</h3>
      <ol><li>Add the relevant experience or project in the career library.</li><li>Copy one accurate accomplishment into an Evidence claim and link its context.</li><li>Add source notes and metrics, then verify only after checking the underlying work.</li></ol>
      <p className="hint">An existing resume is a starting point, not independent proof of its claims. Nothing in this preview enters an approved resume automatically.</p>
    </section>
  </div>
}
