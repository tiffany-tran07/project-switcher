import { useEffect, useRef, useState, type FormEvent } from 'react'
import { API_ROOT, api, uploadSource, type SourceAttachment, type SourceAttachmentRef } from './api'

export function AttachmentLinks({ sources }: { sources: SourceAttachmentRef[] }) {
  return <ul>{sources.map((source) => <li key={source.id}>
    <a href={`${API_ROOT}/attachments/${encodeURIComponent(source.id)}/download`} download>{source.original_name}</a>
    {' '}<small>({source.size} bytes · SHA-256 {source.checksum})</small>
  </li>)}</ul>
}

type Props = {
  evidenceId: string; blocked: boolean; onPendingChange: (pending: boolean) => void
  run: (action: () => Promise<unknown>, message: string) => Promise<boolean>
}
export default function EvidenceAttachments({ evidenceId, blocked, onPendingChange, run }: Props) {
  const [sources, setSources] = useState<SourceAttachment[] | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [reload, setReload] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    let active = true
    api<SourceAttachment[]>(`/evidence/${encodeURIComponent(evidenceId)}/attachments`)
      .then((rows) => { if (active) { setSources(rows); setError('') } })
      .catch((cause) => { if (active) setError(String(cause)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [evidenceId, reload])
  function clear() {
    setFile(null); onPendingChange(false)
    if (input.current) input.current.value = ''
  }
  async function upload(event: FormEvent) {
    event.preventDefault()
    if (!file || blocked || loading || !sources) return
    if (!window.confirm('Attach this local source file and return the evidence to draft for manual review? This increment has no file replacement or deletion.')) return
    const success = await run(() => uploadSource(evidenceId, file), 'Source attached. Review all sources and verify the evidence again.')
    if (success) { clear(); setLoading(true); setReload((value) => value + 1) }
  }
  return <section className="editor-card source-attachments" aria-label="Supporting source files" aria-busy={loading}>
    <h2>Supporting source files</h2>
    <p className="hint">Attach UTF-8 .txt benchmark logs or notes (up to 1 MB). Files stay local and are not interpreted or sent to AI. Uploading returns the evidence to draft and clears bullet approvals. Review every source before verifying again. Files are append-only in this increment; replacement and deletion are not available.</p>
    {error && <p role="alert" className="message error">{error}</p>}
    {loading ? <p>Loading source files…</p> : sources && (sources.length ? <AttachmentLinks sources={sources} /> : <p>No source files attached.</p>)}
    <form onSubmit={(event) => { void upload(event) }}>
      <label>Supporting text file<input ref={input} type="file" accept=".txt,text/plain" disabled={blocked || loading} onChange={(event) => {
        const value = event.target.files?.[0] ?? null
        setFile(value); onPendingChange(Boolean(value))
      }} /></label>
      {file && <p>Selected file: {file.name}</p>}
      <div className="actions"><button disabled={blocked || loading || !sources || !file}>Attach source file</button>
        {file && <button type="button" className="secondary" disabled={blocked} onClick={clear}>Clear selected file</button>}
        <button type="button" className="secondary" disabled={blocked || loading} onClick={() => { setLoading(true); setReload((value) => value + 1) }}>Refresh sources</button>
      </div>
    </form>
  </section>
}
