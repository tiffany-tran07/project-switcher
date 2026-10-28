import { useEffect, useState, type FormEvent } from 'react'
import { api, save, type Application, type ApplicationStatus, type Job, type Resume, type ResumeVersion } from './api'
import ApplicationHistory from './ApplicationHistory'
import ResumePreview from './ResumePreview'
import ResumeExports from './ResumeExports'

const statuses: ApplicationStatus[] = ['planned', 'applied', 'interview', 'offer', 'rejected', 'withdrawn']
type VersionChoice = { id: string; jobId: string; label: string }

export default function ApplicationsWorkspace({ onEvidenceSelect }: { onEvidenceSelect: (id: string) => void }) {
  const [rows, setRows] = useState<Application[]>([])
  const [choices, setChoices] = useState<VersionChoice[]>([])
  const [selected, setSelected] = useState('')
  const [versionId, setVersionId] = useState('')
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const application = rows.find((row) => row.id === selected)

  useEffect(() => {
    let active = true
    async function load() {
      const [applications, resumes, jobs] = await Promise.all([
        api<Application[]>('/applications'), api<Resume[]>('/resumes'), api<Job[]>('/jobs'),
      ])
      const groups = await Promise.all(resumes.map(async (resume) => {
        const versions = await api<ResumeVersion[]>(`/resumes/${resume.id}/versions`)
        const job = jobs.find((row) => row.id === resume.job_id)
        return versions.filter((version) => version.approved_at).map((version) => ({
          id: version.id, jobId: resume.job_id,
          label: `${job?.company ?? ''} · ${job?.title ?? resume.name} · ${resume.name} v${version.version_number}`,
        }))
      }))
      if (active) { setRows(applications); setChoices(groups.flat()) }
    }
    void load().catch((cause) => { if (active) setError(String(cause)) })
    return () => { active = false }
  }, [])

  async function create(event: FormEvent) {
    event.preventDefault()
    const choice = choices.find((row) => row.id === versionId)
    if (!choice) return
    setError(''); setBusy(true)
    try {
      const row = await save<Application>('/applications', 'POST', { job_id: choice.jobId, resume_version_id: choice.id })
      setRows((current) => [row, ...current]); setSelected(row.id)
    } catch (cause) { setError(String(cause)) } finally { setBusy(false) }
  }

  function updated(row: Application) { setRows((current) => current.map((item) => item.id === row.id ? row : item)) }

  return <div className="applications-workspace">
    {error && <p className="message error" role="alert">{error}</p>}
    <form className="editor-card resume-create" onSubmit={create}>
      <h2>Track an application</h2><p className="hint">Choose the exact approved resume version. This only creates a local record; it does not submit an application.</p>
      <label>Approved resume version<select required value={versionId} onChange={(event) => setVersionId(event.target.value)}><option value="">Select a version</option>{choices.map((choice) => <option value={choice.id} key={choice.id}>{choice.label}</option>)}</select></label>
      {!choices.length && <p className="empty">Create an approved resume snapshot first.</p>}
      <button disabled={busy || !versionId}>Create application record</button>
    </form>
    <div className="workspace"><section className="record-list"><h2>Applications</h2>
      <label>Filter status<select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All</option>{statuses.map((status) => <option key={status}>{status}</option>)}</select></label>
      {rows.filter((row) => !filter || row.status === filter).map((row) => <button className={selected === row.id ? 'selected' : ''} key={row.id} onClick={() => setSelected(row.id)}>{row.company} · {row.title}<small className="application-status">{row.status}{row.follow_up_date && ` · Follow up ${row.follow_up_date}`}</small></button>)}
      {!rows.length && <p className="empty">No applications tracked yet.</p>}
    </section>
    {application ? <ApplicationDetail key={`${application.id}-${application.updated_at}`} application={application} onUpdate={updated} onEvidenceSelect={onEvidenceSelect} /> : <p className="empty">Select an application to review its history and resume.</p>}
    </div>
  </div>
}

function ApplicationDetail({ application, onUpdate, onEvidenceSelect }: { application: Application; onUpdate: (row: Application) => void; onEvidenceSelect: (id: string) => void }) {
  const [form, setForm] = useState({ status: application.status, notes: application.notes, applied_date: application.applied_date ?? '', follow_up_date: application.follow_up_date ?? '', event_note: '' })
  const [eventNote, setEventNote] = useState('')
  const [version, setVersion] = useState<ResumeVersion | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api<ResumeVersion>(`/resume-versions/${application.resume_version_id}`)
      .then((row) => { if (active) setVersion(row) })
      .catch((cause) => { if (active) setError(String(cause)) })
    return () => { active = false }
  }, [application.resume_version_id])

  async function update(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      onUpdate(await save<Application>(`/applications/${application.id}`, 'PATCH', {
        ...form, applied_date: form.applied_date || (form.status === 'applied' && application.status !== 'applied' ? undefined : null), follow_up_date: form.follow_up_date || null,
      }))
    } catch (cause) { setError(String(cause)) } finally { setBusy(false) }
  }

  async function addNote(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { onUpdate(await save<Application>(`/applications/${application.id}/events`, 'POST', { note: eventNote })) }
    catch (cause) { setError(String(cause)) } finally { setBusy(false) }
  }

  return <div className="editor-stack">
    {error && <p className="message error" role="alert">{error}</p>}
    <form className="editor-card" onSubmit={update}><h2>{application.title} · {application.company}</h2>
      {application.url && <p className="posting-url">Posting: {application.url}</p>}
      <p className="hint">Job and resume links are fixed for this record. Changing career data will not change its saved resume.</p>
      <fieldset disabled={busy} className="application-fields"><label>Status<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ApplicationStatus })}>{statuses.map((status) => <option key={status}>{status}</option>)}</select></label>
      <div className="form-grid"><label>Applied date<input type="date" value={form.applied_date} onChange={(event) => setForm({ ...form, applied_date: event.target.value })} /></label><label>Follow-up date<input type="date" value={form.follow_up_date} onChange={(event) => setForm({ ...form, follow_up_date: event.target.value })} /></label></div>
      <label>Notes<textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></label>
      <label>History note for this update<input value={form.event_note} onChange={(event) => setForm({ ...form, event_note: event.target.value })} /></label>
      </fieldset><button disabled={busy}>Save application</button>
    </form>
    <section className="editor-card"><ApplicationHistory events={application.events} />
      <form className="description-form" onSubmit={addNote}><label>Add a history note<textarea required maxLength={2000} value={eventNote} onChange={(event) => setEventNote(event.target.value)} /></label><button disabled={busy || !eventNote.trim()}>Add note</button></form>
    </section>
    {version && <section className="editor-card"><h2>Linked resume · version {version.version_number}</h2><p className="hint">Exact immutable version ID: {version.id}</p><ResumePreview version={version} /><ResumeExports key={version.id} versionId={version.id} approved={Boolean(version.approved_at)} onEvidenceSelect={onEvidenceSelect} /></section>}
  </div>
}
