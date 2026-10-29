import { useEffect, useRef, useState } from 'react'
import { previewResume, save, type Evidence, type Experience, type Project } from './api'
import { intakeDraftPayload, selectedClaim } from './intakeDraft'
import IntakeContextCreator from './IntakeContextCreator'

export default function ResumeIntake({ experiences = [], projects = [], onDraftSaved, onOpenEvidence, onExperienceCreated, onProjectCreated }: { experiences?: Experience[]; projects?: Project[]; onDraftSaved?: (row: Evidence) => void; onOpenEvidence?: (id: string) => void; onExperienceCreated?: (row: Experience) => void; onProjectCreated?: (row: Project) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState('')
  const [source, setSource] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [claim, setClaim] = useState('')
  const [context, setContext] = useState('')
  const [creatingContext, setCreatingContext] = useState(false)
  const [sourceNote, setSourceNote] = useState('')
  const [saved, setSaved] = useState<Evidence | null>(null)
  const textInput = useRef<HTMLTextAreaElement>(null)
  const activeExperiences = experiences.filter((row) => !row.archived_at)
  const activeProjects = projects.filter((row) => !row.archived_at && (!row.experience_id || activeExperiences.some((experience) => experience.id === row.experience_id)))
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
        setClaim(''); setSourceNote(''); setSaved(null)
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause))
    } finally { if (!controller.signal.aborted) setBusy(false) }
  }

  function clear() {
    setFile(null); setText(''); setSource(''); setWarnings([]); setError('')
    setClaim(''); setContext(''); setSourceNote(''); setSaved(null); setCreatingContext(false)
    if (fileInput.current) fileInput.current.value = ''
  }

  function selectExcerpt() {
    const input = textInput.current
    if (!input) return
    try {
      setClaim(selectedClaim(text, input.selectionStart, input.selectionEnd)); setError(''); setSaved(null)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
  }

  async function saveDraft() {
    setBusy(true); setError('')
    try {
      const payload = intakeDraftPayload(text, claim, context, source, sourceNote)
      const row = await save<Evidence>('/resume-intake/drafts', 'POST', payload)
      onDraftSaved?.(row); setSaved(row); setClaim(''); setSourceNote('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  return <div className="editor-stack intake-workspace">
    <section className="editor-card"><h2>Preview an existing resume</h2>
      <p>Choose a DOCX or UTF-8 text file, or paste text below. PDF intake is not available yet; copy its text into the editor instead.</p>
      <p className="hint">File previews are processed by your configured backend (localhost by default). No AI is called, files are not saved, and no career records are created or verified by file preview.</p>
      <label>Resume file (.docx or .txt, maximum 5 MB)<input ref={fileInput} type="file" accept=".docx,.txt" disabled={busy} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError('') }} /></label>
      <div className="actions"><button type="button" disabled={busy || !file} onClick={() => { void preview() }}>{busy ? 'Reading resume…' : 'Preview file text'}</button><button type="button" className="secondary" disabled={busy} onClick={clear}>Clear preview</button></div>
      {error && <p className="message error" role="alert">{error}</p>}
      {warnings.length > 0 && <ul className="intake-warnings">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
    </section>
    <section className="editor-card"><h2>Review or paste resume text</h2>
      {source && <p>Preview source: {source}</p>}
      <label>Resume text<textarea ref={textInput} className="intake-text" maxLength={100000} disabled={busy} value={text} onChange={(event) => { setText(event.target.value); setClaim(''); setSaved(null) }} placeholder="Paste your resume here, or preview a file above." /></label>
      <p className="hint">Preview text is temporary and is cleared when you leave this page. Review dates, metrics, symbols, and table reading order; extraction may omit text boxes, headers, or images.</p>
      <div className="actions"><button type="button" className="secondary" disabled={busy || !text.trim()} onClick={selectExcerpt}>Use highlighted text as a claim</button></div>
      <h3>Save one reviewed accomplishment</h3>
      <p className="hint">Highlight an accomplishment in the text above, then choose its experience or project. The saved claim is the exact selected excerpt, without rewriting.</p>
      <label>Selected claim<textarea readOnly value={claim} placeholder="Highlight text above, then choose Use highlighted text as a claim." /></label>
      <label>Source experience or project<select value={context} disabled={busy} onChange={(event) => setContext(event.target.value)}><option value="">Choose the correct source context</option><optgroup label="Experiences">{activeExperiences.map((row) => <option value={`experience:${row.id}`} key={row.id}>{row.title} · {row.organization}</option>)}</optgroup><optgroup label="Projects">{activeProjects.map((row) => <option value={`project:${row.id}`} key={row.id}>{row.name}</option>)}</optgroup></select></label>
      {!activeExperiences.length && !activeProjects.length && <p className="empty">Create an experience or project below without leaving your resume preview.</p>}
      {!creatingContext && <div className="actions"><button type="button" className="secondary" disabled={busy} onClick={() => setCreatingContext(true)}>Create experience or project here</button></div>}
      {creatingContext && <IntakeContextCreator experiences={activeExperiences} disabled={busy} onBusyChange={setBusy} onCancel={() => setCreatingContext(false)} onExperienceCreated={(row) => { onExperienceCreated?.(row); setContext(`experience:${row.id}`); setCreatingContext(false) }} onProjectCreated={(row) => { onProjectCreated?.(row); setContext(`project:${row.id}`); setCreatingContext(false) }} />}
      <label>Supporting source notes (optional)<textarea disabled={busy} maxLength={5000} value={sourceNote} onChange={(event) => setSourceNote(event.target.value)} placeholder="Where can you verify this work? A resume alone is not proof." /></label>
      <div className="actions"><button type="button" disabled={busy || !claim || !context} onClick={() => { void saveDraft() }}>Save as draft evidence</button></div>
      {saved && <div className="message success" role="status"><p>Saved as draft evidence—not verified. Add metrics and review supporting sources in Evidence.</p>{onOpenEvidence && <button type="button" className="match-link" onClick={() => onOpenEvidence(saved.id)}>Open saved evidence</button>}</div>}
      <p className="hint">An existing resume is a starting point, not independent proof of its claims. Nothing in this preview enters an approved resume automatically.</p>
    </section>
  </div>
}
