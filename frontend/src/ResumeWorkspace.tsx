import { useEffect, useState, type FormEvent } from 'react'
import DraftValidationReport from './DraftValidationReport'
import { api, save, type DraftValidation, type Evidence, type Job, type Project, type Resume, type ResumeVersion } from './api'

type Heading = 'Experience' | 'Projects' | 'Selected evidence'
const headingOrder: Heading[] = ['Experience', 'Projects', 'Selected evidence']

export default function ResumeWorkspace({ evidence, projects, onEvidenceSelect }: { evidence: Evidence[]; projects: Project[]; onEvidenceSelect: (id: string) => void }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [resumes, setResumes] = useState<Resume[]>([])
  const [resumeId, setResumeId] = useState('')
  const [jobId, setJobId] = useState('')
  const [name, setName] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [headings, setHeadings] = useState<Record<string, Heading>>({})
  const [wording, setWording] = useState<Record<string, string>>({})
  const [suggestions, setSuggestions] = useState<Record<string, string[]>>({})
  const [versions, setVersions] = useState<ResumeVersion[]>([])
  const [version, setVersion] = useState<ResumeVersion | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [validation, setValidation] = useState<{ key: string; report: DraftValidation } | null>(null)
  const sections = headingOrder.map((heading) => ({
    heading,
    bullets: selected.filter((id) => headings[id] === heading).map((id) => ({ evidence_id: id, text: wording[id] ?? '' })),
  })).filter((section) => section.bullets.length)
  const validationKey = JSON.stringify({ resumeId, sections })
  const report = validation?.key === validationKey ? validation.report : null

  useEffect(() => {
    Promise.all([api<Job[]>('/jobs'), api<Resume[]>('/resumes')])
      .then(([jobRows, resumeRows]) => { setJobs(jobRows); setResumes(resumeRows) })
      .catch((cause) => setError(String(cause)))
  }, [])

  async function chooseResume(id: string) {
    setResumeId(id); setSelected([]); setHeadings({}); setWording({}); setSuggestions({}); setVersion(null); setError('')
    if (!id) { setVersions([]); return }
    try {
      const rows = await api<ResumeVersion[]>(`/resumes/${id}/versions`)
      setVersions(rows); setVersion(rows.at(-1) ?? null)
    } catch (cause) { setError(String(cause)) }
  }

  async function create(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      const row = await save<Resume>('/resumes', 'POST', { job_id: jobId, name })
      setResumes((current) => [row, ...current]); setName(''); await chooseResume(row.id)
    } catch (cause) { setError(String(cause)) } finally { setBusy(false) }
  }

  function move(index: number, offset: number) {
    const next = [...selected]
    const target = index + offset
    if (target < 0 || target >= next.length) return
    const moved = next[index]
    next[index] = next[target]
    next[target] = moved
    setSelected(next)
  }

  async function validate() {
    if (!resumeId || !selected.length) return
    setError(''); setBusy(true)
    try {
      const checked = await save<DraftValidation>(`/resumes/${resumeId}/validate`, 'POST', { sections })
      setValidation({ key: validationKey, report: checked })
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  async function draft(approve: boolean) {
    if (!resumeId) return
    setError(''); setBusy(true)
    try {
      const checked = await save<DraftValidation>(`/resumes/${resumeId}/validate`, 'POST', { sections })
      setValidation({ key: validationKey, report: checked })
      if (!checked.valid) return
      const created = await save<ResumeVersion>(`/resumes/${resumeId}/draft`, 'POST', { sections, approve })
      setVersions((current) => [...current, created]); setVersion(created)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  const available = evidence.filter((item) => item.state === 'verified' && !item.archived_at)
  function selectEvidence(item: Evidence, checked: boolean) {
    setSelected(checked ? [...selected, item.id] : selected.filter((id) => id !== item.id))
    if (checked) {
      setHeadings((current) => ({ ...current, [item.id]: item.project_id ? 'Projects' : item.experience_id ? 'Experience' : 'Selected evidence' }))
      setWording((current) => ({ ...current, [item.id]: item.claim }))
      void api<string[]>(`/evidence/${item.id}/resume-wordings`)
        .then((options) => setSuggestions((current) => ({ ...current, [item.id]: options })))
        .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)))
    }
  }
  function copyVersion() {
    if (!version) return
    setSelected(version.bullets.map((bullet) => bullet.evidence_id))
    setWording(Object.fromEntries(version.bullets.map((bullet) => [bullet.evidence_id, bullet.text])))
    setHeadings(Object.fromEntries(version.content.sections.flatMap((section) =>
      section.evidence_ids.map((id) => [id, section.heading as Heading]),
    )))
  }
  return <div className="resume-workspace">
    {error && <div role="alert" className="message error">{error}</div>}
    <form className="editor-card resume-create" onSubmit={create}><h2>Create a targeted resume</h2><label>Job<select required value={jobId} onChange={(event) => setJobId(event.target.value)}><option value="">Select a job</option>{jobs.map((job) => <option key={job.id} value={job.id}>{job.title} · {job.company}</option>)}</select></label><label>Resume name<input required value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Backend role" /></label><button disabled={busy || !jobId}>Create resume</button></form>
    <div className="workspace"><div className="record-list"><h2>Resumes</h2>{resumes.length ? resumes.map((row) => <button key={row.id} className={row.id === resumeId ? 'selected' : ''} onClick={() => { void chooseResume(row.id) }}>{row.name}</button>) : <p className="empty">No targeted resumes yet.</p>}</div>
      {resumeId && <div className="editor-stack"><section className="editor-card"><h2>Select verified evidence</h2><p className="hint">Only active, verified evidence is eligible. Bullets start from your claims; wording edits must pass strict source checks.</p>{available.map((item) => <label className="inline-check" key={item.id}><input type="checkbox" checked={selected.includes(item.id)} onChange={(event) => selectEvidence(item, event.target.checked)} />{item.claim}</label>)}{!available.length && <p className="empty">Verify evidence in the library to draft bullets.</p>}<h3>Sections and bullet wording</h3><p className="hint">You can remove filler words or adjust punctuation. New claims, tools, dates, and metrics must first be added to and verified in the evidence library.</p>{selected.map((id, index) => { const item = evidence.find((row) => row.id === id); return <div className="bullet-editor" key={id}><label>Section<select value={headings[id] ?? 'Selected evidence'} onChange={(event) => setHeadings((current) => ({ ...current, [id]: event.target.value as Heading }))}>{headingOrder.map((heading) => <option key={heading} value={heading} disabled={heading === 'Projects' ? !item?.project_id : heading === 'Experience' ? !(item?.experience_id || projects.find((project) => project.id === item?.project_id)?.experience_id) : false}>{heading}</option>)}</select></label>{suggestions[id]?.length > 1 && <label>Verified wording suggestions<select value="" onChange={(event) => { if (event.target.value) setWording((current) => ({ ...current, [id]: event.target.value })) }}><option value="">Choose approved wording</option>{suggestions[id].slice(1).map((option) => <option key={option} value={option}>{option}</option>)}</select></label>}<label>Bullet wording<textarea value={wording[id] ?? item?.claim ?? ''} onChange={(event) => setWording((current) => ({ ...current, [id]: event.target.value }))} /></label>{report?.issues.filter((issue) => issue.evidence_id === id).map((issue) => <p className="bullet-issue" role="alert" key={`${issue.position}-${issue.code}`}>{issue.message}</p>)}<div className="ordered-evidence"><span>Selected order: {index + 1}</span><button type="button" aria-label="Move bullet up" disabled={index === 0} onClick={() => move(index, -1)}>↑</button><button type="button" aria-label="Move bullet down" disabled={index === selected.length - 1} onClick={() => move(index, 1)}>↓</button><button type="button" onClick={() => setSelected((current) => current.filter((entry) => entry !== id))}>Remove</button></div></div> })}{selected.length > 0 && <div className="draft-preview"><h3>Review sources before saving</h3>{selected.map((id) => { const item = evidence.find((row) => row.id === id); return item && <div className="snapshot-bullet" key={id}><p>• {wording[id] ?? item.claim}</p><small>Original claim: {item.claim}</small><small>Verified source: <button className="match-link" onClick={() => onEvidenceSelect(id)}>{item.source_note}</button></small>{item.metrics.map((metric) => <small key={metric.id}>Metric: {metric.name} · {metric.value} {metric.unit} ({metric.source_note})</small>)}</div> })}</div>}{report && <DraftValidationReport report={report} />}<div className="actions"><button className="secondary" disabled={busy || selected.length === 0} onClick={() => { void validate() }}>Check sources and wording</button><button disabled={busy || selected.length === 0} onClick={() => { void draft(false) }}>Save draft version</button><button className="secondary" disabled={busy || selected.length === 0} onClick={() => { if (window.confirm('Approve these reviewed, source-backed bullets as an immutable snapshot?')) void draft(true) }}>Approve snapshot</button></div></section>
        <section className="editor-card"><h2>Version history</h2>{versions.length ? <select aria-label="Resume version" value={version?.id ?? ''} onChange={(event) => setVersion(versions.find((row) => row.id === event.target.value) ?? null)}>{versions.map((row) => <option key={row.id} value={row.id}>Version {row.version_number} · {row.approved_at ? 'approved' : 'draft'}</option>)}</select> : <p className="empty">No versions saved yet.</p>}{version && <><p className="hint">This is an immutable snapshot. Make a new version to change selection, wording, or order.</p><button type="button" className="secondary" onClick={copyVersion}>Use version as starting point</button>{version.content.sections.map((section) => <div key={section.heading}><h3>{section.heading}</h3>{section.evidence_ids.map((id) => { const bullet = version.bullets.find((item) => item.evidence_id === id); return bullet && <div className="snapshot-bullet" key={bullet.id}><p>• {bullet.text}</p><small>Verified source: <button className="match-link" onClick={() => onEvidenceSelect(bullet.evidence_id)}>{bullet.evidence_snapshot.claim}</button></small><small>{bullet.evidence_snapshot.experience?.organization ?? bullet.evidence_snapshot.project?.name ?? ''} · {bullet.evidence_snapshot.source_note}</small></div> })}</div>)}</>}</section></div>}
    </div>
  </div>
}
