import { useEffect, useState } from 'react'
import { api, API_ROOT, save, type AtsReport, type ExportFile } from './api'
import AtsReadiness from './AtsReadiness'

export default function ResumeExports({ versionId, approved, onEvidenceSelect }: { versionId: string; approved: boolean; onEvidenceSelect?: (id: string) => void }) {
  const [files, setFiles] = useState<ExportFile[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [reports, setReports] = useState<Record<string, AtsReport>>({})
  const [analyzing, setAnalyzing] = useState<string | null>(null)
  const [pageTarget, setPageTarget] = useState(2)

  useEffect(() => {
    let active = true
    api<ExportFile[]>(`/resume-versions/${versionId}/exports`)
      .then((rows) => { if (active) setFiles(rows) })
      .catch((cause) => { if (active) setError(String(cause)) })
    return () => { active = false }
  }, [versionId])

  async function generate(format: 'docx' | 'pdf') {
    setError(''); setBusy(true)
    try {
      const artifact = await save<ExportFile>(`/resume-versions/${versionId}/export`, 'POST', { format })
      setFiles((current) => [artifact, ...current])
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  async function analyze(exportId: string) {
    setError(''); setAnalyzing(exportId)
    setReports((current) => Object.fromEntries(Object.entries(current).filter(([id]) => id !== exportId)))
    try {
      const report = await save<AtsReport>(`/resume-versions/${versionId}/ats`, 'POST', { export_id: exportId, page_target: pageTarget })
      setReports((current) => ({ ...current, [exportId]: report }))
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setAnalyzing(null) }
  }

  return <section className="resume-exports" aria-label="Version exports">
    <h3>Document exports</h3>
    <p className="hint">Single-column documents from this saved snapshot. PDF conversion requires local LibreOffice; extracted text and page count are checked before saving. Visually review the result in a document viewer.</p>
    {!approved && <p>Approve a new snapshot before exporting. Draft versions cannot be exported.</p>}
    <div className="actions"><button type="button" disabled={!approved || busy} onClick={() => { void generate('docx') }}>Generate DOCX</button><button type="button" disabled={!approved || busy} onClick={() => { void generate('pdf') }}>Generate PDF</button>{busy && <span role="status">Generating…</span>}</div>
    <label>Maximum resume pages<select value={pageTarget} disabled={analyzing !== null} onChange={(event) => { setPageTarget(Number(event.target.value)); setReports({}) }}>{[1, 2, 3, 4, 5].map((count) => <option value={count} key={count}>{count}</option>)}</select></label>
    <p className="hint">The readiness report compares this target against the actual PDF page count. DOCX pagination is not measured.</p>
    {error && <p className="message error" role="alert">{error}</p>}
    {files.map((file) => <div className="export-file" key={file.id}>
      <a className="button secondary" href={`${API_ROOT}/exports/${file.id}/download`} download={`resume.${file.format}`}>Download {file.format.toUpperCase()}</a>
      <small>Generated {new Date(file.created_at).toLocaleString()}{file.page_count !== null && ` · ${file.page_count} page${file.page_count === 1 ? '' : 's'}`}</small>
      <details><summary>Extracted document text</summary><pre>{file.extracted_text}</pre><small>SHA-256: {file.checksum}</small></details>
      <div className="actions"><button type="button" className="secondary" disabled={analyzing !== null} onClick={() => { void analyze(file.id) }}>{analyzing === file.id ? 'Analyzing…' : 'Run ATS readiness check'}</button></div>
      {reports[file.id] && <AtsReadiness report={reports[file.id]} onEvidenceSelect={onEvidenceSelect} />}
    </div>)}
  </section>
}
