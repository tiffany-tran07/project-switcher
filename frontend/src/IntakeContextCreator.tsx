import { useState, type FormEvent } from 'react'
import { save, type Experience, type Project } from './api'
import { contextPayload, type ContextFields } from './intakeContext'

type Props = {
  experiences: Experience[]
  disabled: boolean
  onBusyChange: (busy: boolean) => void
  onExperienceCreated: (row: Experience) => void
  onProjectCreated: (row: Project) => void
  onCancel: () => void
}

export default function IntakeContextCreator({ experiences, disabled, onBusyChange, onExperienceCreated, onProjectCreated, onCancel }: Props) {
  const [form, setForm] = useState<ContextFields>({
    kind: 'experience', organization: '', title: '', name: '', experience_id: '',
    start_date: '', end_date: '', description: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setSaving(true); onBusyChange(true)
    try {
      const payload = contextPayload(form)
      if (payload.kind === 'experience') {
        onExperienceCreated(await save<Experience>('/experiences', 'POST', payload.data))
      } else {
        onProjectCreated(await save<Project>('/projects', 'POST', payload.data))
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setSaving(false); onBusyChange(false) }
  }

  return <form className="intake-context-form" aria-label="New source context" onSubmit={submit}>
    <h3>Create source context</h3>
    <p className="hint">Enter the role or project yourself; nothing is inferred from the resume. Your preview, selected claim, and notes stay in place.</p>
    <fieldset disabled={disabled || saving}>
      <label>New source type<select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as ContextFields['kind'] })}><option value="experience">Experience</option><option value="project">Project</option></select></label>
      {form.kind === 'experience' ? <div className="form-grid"><label>Organization<input required maxLength={200} value={form.organization} onChange={(event) => setForm({ ...form, organization: event.target.value })} /></label><label>Role title<input required maxLength={200} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label></div> : <><label>Project name<input required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>Linked experience<select value={form.experience_id} onChange={(event) => setForm({ ...form, experience_id: event.target.value })}><option value="">Independent project</option>{experiences.filter((row) => !row.archived_at).map((row) => <option value={row.id} key={row.id}>{row.title} · {row.organization}</option>)}</select></label></>}
      <div className="form-grid"><label>Start date<input type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} /></label><label>End date<input type="date" value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} /></label></div>
      <label>Description or summary (optional)<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
      <div className="actions"><button type="submit">{saving ? 'Creating…' : 'Create source and select it'}</button><button type="button" className="secondary" onClick={onCancel}>Cancel source creation</button></div>
    </fieldset>
    {error && <p className="message error" role="alert">{error}</p>}
  </form>
}
