import { useEffect, useState } from 'react'
import { api, API_ROOT, save, type ExportFile } from './api'

export default function ResumeExports({ versionId, approved }: { versionId: string; approved: boolean }) {
  const [files, setFiles] = useState<ExportFile[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    api<ExportFile[]>(`/resume-versions/${versionId}/exports`)
      .then((rows) => { if (active) setFiles(rows) })
      .catch((cause) => { if (active) setError(String(cause)) })
    return () => { active = false }
  }, [versionId])

  async function generate() {
    setError(''); setBusy(true)
    try {
      const artifact = await save<ExportFile>(`/resume-versions/${versionId}/export`, 'POST', { format: 'docx' })
      setFiles((current) => [artifact, ...current])
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  return <section className="resume-exports" aria-label="Version exports">
    <h3>DOCX export</h3>
    <p className="hint">Single-column Word document from this saved snapshot. Text extraction is checked; PDF, page count, and ATS analysis are not available yet.</p>
    {!approved && <p>Approve a new snapshot before exporting. Draft versions cannot be exported.</p>}
    <div className="actions"><button type="button" disabled={!approved || busy} onClick={() => { void generate() }}>{busy ? 'Generating…' : 'Generate DOCX'}</button></div>
    {error && <p className="message error" role="alert">{error}</p>}
    {files.map((file) => <div className="export-file" key={file.id}>
      <a className="button secondary" href={`${API_ROOT}/exports/${file.id}/download`} download="resume.docx">Download DOCX</a>
      <small>Generated {new Date(file.created_at).toLocaleString()}</small>
      <details><summary>Extracted document text</summary><pre>{file.extracted_text}</pre><small>SHA-256: {file.checksum}</small></details>
    </div>)}
  </section>
}
