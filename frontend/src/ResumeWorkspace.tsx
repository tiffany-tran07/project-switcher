import { useEffect, useState, type FormEvent, type SetStateAction } from 'react'
import DraftValidationReport from './DraftValidationReport'
import ResumePreview from './ResumePreview'
import ResumeExports from './ResumeExports'
import ResumeEvidencePicker from './ResumeEvidencePicker'
import { eligibleEvidence } from './resumeEligibility'
import { AttachmentLinks } from './EvidenceAttachments'
import { api, save, type DraftValidation, type Evidence, type Job, type Project, type Resume, type ResumeVersion, type ResumeEvidenceStatus } from './api'

import { buildSections, defaultHeadingOrder, emptyWorkingDraft, moveWithinSection, type Heading, type WorkingDrafts, type WorkingDraftUpdate } from './resumeDraft'

export default function ResumeWorkspace({ evidence, projects, onEvidenceSelect, initialResumeId, workingDrafts, onWorkingDraftChange, onResumeSelect }: { evidence: Evidence[]; projects: Project[]; onEvidenceSelect: (id: string) => void; initialResumeId?: string; workingDrafts: WorkingDrafts; onWorkingDraftChange: (id: string, update: WorkingDraftUpdate) => void; onResumeSelect: (id: string) => void }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [resumes, setResumes] = useState<Resume[]>([])
  const [resumeId, setResumeId] = useState(initialResumeId ?? '')
  const [jobId, setJobId] = useState('')
  const [name, setName] = useState('')
  const { selected, headingOrder, headings, wording } = workingDrafts[resumeId] ?? emptyWorkingDraft()
  const setSelected = (value: SetStateAction<string[]>) => onWorkingDraftChange(resumeId, (current) => ({ ...current, selected: typeof value === 'function' ? value(current.selected) : value }))
  const setHeadingOrder = (value: SetStateAction<Heading[]>) => onWorkingDraftChange(resumeId, (current) => ({ ...current, headingOrder: typeof value === 'function' ? value(current.headingOrder) : value }))
  const setHeadings = (value: SetStateAction<Record<string, Heading>>) => onWorkingDraftChange(resumeId, (current) => ({ ...current, headings: typeof value === 'function' ? value(current.headings) : value }))
  const setWording = (value: SetStateAction<Record<string, string>>) => onWorkingDraftChange(resumeId, (current) => ({ ...current, wording: typeof value === 'function' ? value(current.wording) : value }))
  const [suggestions, setSuggestions] = useState<Record<string, string[]>>({})
  const [versions, setVersions] = useState<ResumeVersion[]>([])
  const [version, setVersion] = useState<ResumeVersion | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loadingVersions, setLoadingVersions] = useState(Boolean(initialResumeId))
  const [validation, setValidation] = useState<{ key: string; report: DraftValidation } | null>(null)
  const [sourceStatus, setSourceStatus] = useState<{ inputs: Evidence[]; rows: ResumeEvidenceStatus[] } | null>(null)
  const [sourceChecking, setSourceChecking] = useState(true)
  const [sourceError, setSourceError] = useState('')
  const [sourceRefresh, setSourceRefresh] = useState(0)
  const checking = sourceChecking || sourceStatus?.inputs !== evidence && !sourceError
  const statuses = !checking && !sourceError && sourceStatus?.inputs === evidence ? sourceStatus.rows : null
  const available = eligibleEvidence(evidence, statuses)
  const sourcesReady = statuses !== null && selected.length > 0 && selected.every((id) => available.some((item) => item.id === id))
  const sections = buildSections(headingOrder, selected, headings, wording)
  const orderedSelected = sections.flatMap((section) => section.bullets.map((bullet) => bullet.evidence_id))
  const validationKey = JSON.stringify({ resumeId, sections })
  const report = validation?.key === validationKey ? validation.report : null

  useEffect(() => {
    let active = true
    Promise.all([api<Job[]>('/jobs'), api<Resume[]>('/resumes')])
      .then(([jobRows, resumeRows]) => {
        if (active) { setJobs(jobRows); setResumes(resumeRows) }
      })
      .catch((cause) => { if (active) setError(String(cause)) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    setSourceChecking(true); setSourceError(''); setValidation(null)
    api<ResumeEvidenceStatus[]>('/resume-evidence')
      .then((rows) => { if (active) setSourceStatus({ inputs: evidence, rows }) })
      .catch((cause) => { if (active) setSourceError(cause instanceof Error ? cause.message : String(cause)) })
      .finally(() => { if (active) setSourceChecking(false) })
    return () => { active = false }
  }, [evidence, sourceRefresh])

  function refreshSources() {
    setSourceChecking(true); setSourceError(''); setValidation(null); setSourceRefresh((value) => value + 1)
  }

  useEffect(() => {
    if (!resumeId) return
    let active = true
    api<ResumeVersion[]>(`/resumes/${resumeId}/versions`)
      .then((rows) => { if (active) { setVersions(rows); setVersion(rows.at(-1) ?? null) } })
      .catch((cause) => { if (active) setError(String(cause)) })
      .finally(() => { if (active) setLoadingVersions(false) })
    return () => { active = false }
  }, [resumeId])

  useEffect(() => {
    if (!selected.length) return
    let active = true
    setSuggestions({})
    for (const id of selected) {
      void api<string[]>(`/evidence/${id}/resume-wordings`)
        .then((options) => { if (active) setSuggestions((current) => ({ ...current, [id]: options })) })
        .catch(() => { /* Source validation will report unavailable or unverified evidence. */ })
    }
    return () => { active = false }
  }, [resumeId, selected])

  function chooseResume(id: string) {
    if (busy || id === resumeId) return
    setResumeId(id); onResumeSelect(id); setSuggestions({}); setVersions([]); setVersion(null); setError(''); setValidation(null); setLoadingVersions(Boolean(id))
  }

  async function create(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      const row = await save<Resume>('/resumes', 'POST', { job_id: jobId, name })
      setResumes((current) => [row, ...current]); setName(''); setResumeId(row.id); onResumeSelect(row.id); setVersions([]); setVersion(null); setValidation(null); setLoadingVersions(true)
    } catch (cause) { setError(String(cause)) } finally { setBusy(false) }
  }

  function moveSection(index: number, offset: -1 | 1) {
    const target = index + offset
    if (target < 0 || target >= headingOrder.length) return
    const next = [...headingOrder]
    const moved = next[index]
    next[index] = next[target]
    next[target] = moved
    setHeadingOrder(next)
  }

  function rememberValidation(checked: DraftValidation) {
    setValidation({ key: validationKey, report: checked })
    const problems = new Map(checked.issues.filter((issue) => issue.code === 'unavailable_evidence').map((issue) => [issue.evidence_id, issue.message]))
    if (problems.size) setSourceStatus((current) => current && ({ ...current, rows: current.rows.map((row) => problems.has(row.evidence_id) ? { ...row, eligible: false, problem: problems.get(row.evidence_id)! } : row) }))
  }

  async function validate() {
    if (!resumeId || !selected.length) return
    setError(''); setBusy(true)
    try {
      const checked = await save<DraftValidation>(`/resumes/${resumeId}/validate`, 'POST', { sections })
      rememberValidation(checked)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  async function draft(approve: boolean) {
    if (!resumeId || busy || loadingVersions || !sourcesReady) return
    setError(''); setBusy(true)
    try {
      const checked = await save<DraftValidation>(`/resumes/${resumeId}/validate`, 'POST', { sections })
      rememberValidation(checked)
      if (!checked.valid) return
      const created = await save<ResumeVersion>(`/resumes/${resumeId}/draft`, 'POST', { sections, approve })
      setVersions((current) => [...current, created]); setVersion(created)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  function selectEvidence(item: Evidence, checked: boolean) {
    setSelected((current) => checked ? [...current.filter((id) => id !== item.id), item.id] : current.filter((id) => id !== item.id))
    if (checked) {
      setHeadings((current) => ({ ...current, [item.id]: item.project_id ? 'Projects' : item.experience_id ? 'Experience' : 'Selected evidence' }))
      setWording((current) => ({ ...current, [item.id]: item.claim }))
    }
  }
  function copyVersion() {
    if (!version || busy) return
    if (selected.length && !window.confirm('Replace the working selection and wording with this saved version?')) return
    const savedOrder = version.content.sections.map((section) => section.heading as Heading)
    setHeadingOrder([...savedOrder, ...defaultHeadingOrder.filter((heading) => !savedOrder.includes(heading))])
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
      {resumeId && <div className="editor-stack"><section className="editor-card"><fieldset className="review-fields" disabled={busy}><h2>Select verified evidence</h2><p className="hint">Working selections and wording stay in memory while you switch pages or resumes in this tab. Reloading or closing clears them; saved versions remain permanent. Sources are rechecked before saving.</p>{selected.some((id) => !available.some((item) => item.id === id)) && <p className="message warning">Some selected evidence is unavailable or not yet checked. Your edits are kept; source checks must pass before saving.</p>}{selected.length > 0 && <div className="actions"><button type="button" className="secondary" onClick={() => { if (window.confirm('Clear this working selection and wording? Saved versions will not change.')) { onWorkingDraftChange(resumeId, () => emptyWorkingDraft()); setValidation(null); setError('') } }}>Clear working selection</button></div>}<ResumeEvidencePicker evidence={evidence} statuses={statuses} selected={selected} checking={checking} error={sourceError} busy={busy} onRefresh={refreshSources} onSelect={selectEvidence} onReview={onEvidenceSelect} /><h3>Section order</h3><div role="group" aria-label="Resume section order">{headingOrder.map((heading, index) => <div className="ordered-evidence" key={heading}><span>{heading}</span><button type="button" aria-label={`Move ${heading} section up`} disabled={index === 0} onClick={() => moveSection(index, -1)}>↑</button><button type="button" aria-label={`Move ${heading} section down`} disabled={index === headingOrder.length - 1} onClick={() => moveSection(index, 1)}>↓</button></div>)}</div><p className="hint">Empty sections are omitted. Bullets are grouped by section in this order.</p><h3>Sections and bullet wording</h3><p className="hint">You can omit a leading “I” and its auxiliaries, adjust capitalization/spacing, or add a final period. Other words, metric signs, currency, comparisons, and technical punctuation must stay unchanged. Verify broader changes in the evidence library first.</p>{orderedSelected.map((id, index) => { const item = evidence.find((row) => row.id === id); const peers = orderedSelected.filter((entry) => (headings[entry] ?? 'Selected evidence') === (headings[id] ?? 'Selected evidence')); return <div className="bullet-editor" key={id}><label>Section<select value={headings[id] ?? 'Selected evidence'} onChange={(event) => setHeadings((current) => ({ ...current, [id]: event.target.value as Heading }))}>{headingOrder.map((heading) => <option key={heading} value={heading} disabled={heading === 'Projects' ? !item?.project_id : heading === 'Experience' ? !(item?.experience_id || projects.find((project) => project.id === item?.project_id)?.experience_id) : false}>{heading}</option>)}</select></label>{suggestions[id]?.length > 1 && <label>Verified wording suggestions<select value="" onChange={(event) => { if (event.target.value) setWording((current) => ({ ...current, [id]: event.target.value })) }}><option value="">Choose approved wording</option>{suggestions[id].slice(1).map((option) => <option key={option} value={option}>{option}</option>)}</select></label>}<label>Bullet wording<textarea value={wording[id] ?? item?.claim ?? ''} onChange={(event) => setWording((current) => ({ ...current, [id]: event.target.value }))} /></label>{report?.issues.filter((issue) => issue.evidence_id === id).map((issue) => <p className="bullet-issue" role="alert" key={`${issue.position}-${issue.code}`}>{issue.message}</p>)}<div className="ordered-evidence"><span>Document bullet: {index + 1}</span><button type="button" aria-label="Move bullet up" disabled={peers[0] === id} onClick={() => setSelected((current) => moveWithinSection(current, headings, id, -1))}>↑</button><button type="button" aria-label="Move bullet down" disabled={peers.at(-1) === id} onClick={() => setSelected((current) => moveWithinSection(current, headings, id, 1))}>↓</button><button type="button" onClick={() => setSelected((current) => current.filter((entry) => entry !== id))}>Remove</button></div></div> })}{selected.length > 0 && <div className="draft-preview" role="region" aria-label="Working resume source review"><h3>Review sources before saving</h3>{orderedSelected.map((id, index) => { const item = evidence.find((row) => row.id === id); return item && <div className="snapshot-bullet" key={id}>{(index === 0 || headings[orderedSelected[index - 1]] !== headings[id]) && <h4>{headings[id] ?? 'Selected evidence'}</h4>}<p>• {wording[id] ?? item.claim}</p><small>Current claim: {item.claim} · Source state: {item.state}</small><small>Source note: <button className="match-link" onClick={() => onEvidenceSelect(id)}>{item.source_note}</button></small>{item.metrics.map((metric) => <small key={metric.id}>Metric: {metric.name} · {metric.value} {metric.unit} ({metric.source_note})</small>)}</div> })}</div>}{report && <DraftValidationReport report={report} />}<div className="actions"><button className="secondary" disabled={busy || selected.length === 0} onClick={() => { void validate() }}>Check sources and wording</button><button disabled={busy || loadingVersions || !sourcesReady} onClick={() => { void draft(false) }}>Save draft version</button><button className="secondary" disabled={busy || loadingVersions || !sourcesReady} onClick={() => { if (window.confirm('Approve these reviewed, source-backed bullets as an immutable snapshot?')) void draft(true) }}>Approve snapshot</button></div>{loadingVersions && <p role="status">Loading version history…</p>}</fieldset></section>
        <section className="editor-card"><h2>Version history</h2>{versions.length ? <select aria-label="Resume version" value={version?.id ?? ''} onChange={(event) => setVersion(versions.find((row) => row.id === event.target.value) ?? null)}>{versions.map((row) => <option key={row.id} value={row.id}>Version {row.version_number} · {row.approved_at ? 'approved' : 'draft'}</option>)}</select> : <p className="empty">No versions saved yet.</p>}{version && <><p className="hint">This is an immutable snapshot. Make a new version to change selection, wording, or order.</p><button type="button" className="secondary" onClick={copyVersion}>Use version as starting point</button><h3>Saved document preview</h3><p className="hint">Uses saved contact details and role context only. Browser layout is not a DOCX/PDF export or page-count check.</p><ResumePreview version={version} /><ResumeExports key={version.id} versionId={version.id} approved={Boolean(version.approved_at)} onEvidenceSelect={onEvidenceSelect} /><h3>Source review</h3>{version.content.sections.map((section) => <div key={section.heading}><h3>{section.heading}</h3>{section.evidence_ids.map((id) => { const bullet = version.bullets.find((item) => item.evidence_id === id); return bullet && <div className="snapshot-bullet" key={bullet.id}><p>• {bullet.text}</p><small>Verified source: <button className="match-link" onClick={() => onEvidenceSelect(bullet.evidence_id)}>{bullet.evidence_snapshot.claim}</button></small><small>{bullet.evidence_snapshot.experience?.organization ?? bullet.evidence_snapshot.project?.name ?? ''} · {bullet.evidence_snapshot.source_note}</small>{Boolean(bullet.evidence_snapshot.attachments?.length) && <AttachmentLinks sources={bullet.evidence_snapshot.attachments ?? []} />}</div> })}</div>)}</>}</section></div>}
    </div>
  </div>
}
