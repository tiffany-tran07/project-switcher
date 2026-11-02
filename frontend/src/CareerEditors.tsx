import { useEffect, useState } from 'react'
import type { Experience, Project, Skill } from './api'

type RecordProps<T> = {
  rows: T[]; selectedId: string | null; busy: boolean
  onSelect: (id: string | null) => void
  onSave: (id: string | null, data: unknown) => Promise<string | null>
  onArchive: (id: string) => Promise<boolean>
}

function recordActions<T>(props: RecordProps<T>) {
  return {
    async save(data: unknown) {
      if (props.busy) return
      const id = await props.onSave(props.selectedId, data)
      if (id !== null) props.onSelect(id)
    },
    async archive(id: string) {
      if (props.busy) return
      if (await props.onArchive(id)) props.onSelect(null)
    },
  }
}

function RecordList<T extends { id: string }>({ title, rows, selectedId, busy, onSelect, label }: {
  title: string; rows: T[]; selectedId: string | null; busy: boolean
  onSelect: (id: string | null) => void; label: (row: T) => string
}) {
  return <section className="record-list" aria-label={`${title} records`}>
    <div className="list-heading"><h2>{title}</h2><button disabled={busy} onClick={() => onSelect(null)}>+ New</button></div>
    {rows.length ? rows.map((row) => <button disabled={busy} key={row.id} className={selectedId === row.id ? 'selected' : ''} onClick={() => onSelect(row.id)}>{label(row)}</button>) : <p className="empty">Nothing here yet. Add your first record.</p>}
  </section>
}
function experienceLabel(row: Experience) { return `${row.title} · ${row.organization}` }
function experienceForm(row?: Experience) {
  return { organization: row?.organization ?? '', title: row?.title ?? '', start_date: row?.start_date ?? '', end_date: row?.end_date ?? '', location: row?.location ?? '', description: row?.description ?? '' }
}
function projectForm(row?: Project) {
  return { experience_id: row?.experience_id ?? '', name: row?.name ?? '', summary: row?.summary ?? '', start_date: row?.start_date ?? '', end_date: row?.end_date ?? '', url: row?.url ?? '' }
}
function skillForm(row?: Skill) {
  return { name: row?.name ?? '', category: row?.category ?? '', aliases: row?.aliases.join(', ') ?? '' }
}

export function ExperienceEditor(props: RecordProps<Experience>) {
  const { rows, selectedId, busy, onSelect } = props
  const selected = rows.find((row) => row.id === selectedId)
  const [form, setForm] = useState(() => experienceForm(selected))
  useEffect(() => setForm(experienceForm(selected)), [selected])
  const actions = recordActions(props)
  return <div className="workspace">
    <RecordList title="Experiences" rows={rows} selectedId={selectedId} busy={busy} onSelect={(id) => { if (id === null) setForm(experienceForm()); onSelect(id) }} label={experienceLabel} />
    <form className="editor-card" onSubmit={(event) => {
      event.preventDefault()
      void actions.save({ ...form, start_date: form.start_date || null, end_date: form.end_date || null })
    }}>
      <h2>{selected ? 'Edit experience' : 'New experience'}</h2>
      <fieldset className="evidence-fields" disabled={busy}>
        <div className="form-grid">
          <label>Organization<input required value={form.organization} onChange={(event) => setForm({ ...form, organization: event.target.value })} /></label>
          <label>Title<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
          <label>Start date<input type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} /></label>
          <label>End date<input type="date" value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} /></label>
          <label>Location<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} /></label>
        </div>
        <label>Description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
        <div className="actions"><button>Save experience</button>{selected && <button type="button" className="danger" onClick={() => { void actions.archive(selected.id) }}>Archive</button>}</div>
      </fieldset>
    </form>
  </div>
}

export function ProjectEditor(props: RecordProps<Project> & { experiences: Experience[] }) {
  const { rows, experiences, selectedId, busy, onSelect } = props
  const selected = rows.find((row) => row.id === selectedId)
  const [form, setForm] = useState(() => projectForm(selected))
  useEffect(() => setForm(projectForm(selected)), [selected])
  const actions = recordActions(props)
  return <div className="workspace">
    <RecordList title="Projects" rows={rows} selectedId={selectedId} busy={busy} onSelect={(id) => { if (id === null) setForm(projectForm()); onSelect(id) }} label={(row) => row.name} />
    <form className="editor-card" onSubmit={(event) => {
      event.preventDefault()
      void actions.save({ ...form, experience_id: form.experience_id || null, start_date: form.start_date || null, end_date: form.end_date || null })
    }}>
      <h2>{selected ? 'Edit project' : 'New project'}</h2>
      <fieldset className="evidence-fields" disabled={busy}>
        <label>Name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label>Linked experience<select value={form.experience_id} onChange={(event) => setForm({ ...form, experience_id: event.target.value })}><option value="">Independent project</option>{experiences.map((row) => <option value={row.id} key={row.id}>{experienceLabel(row)}</option>)}</select></label>
        <div className="form-grid">
          <label>Start date<input type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} /></label>
          <label>End date<input type="date" value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} /></label>
        </div>
        <label>URL<input type="url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} /></label>
        <label>Summary<textarea value={form.summary} onChange={(event) => setForm({ ...form, summary: event.target.value })} /></label>
        <div className="actions"><button>Save project</button>{selected && <button type="button" className="danger" onClick={() => { void actions.archive(selected.id) }}>Archive</button>}</div>
      </fieldset>
    </form>
  </div>
}

export function SkillEditor(props: RecordProps<Skill>) {
  const { rows, selectedId, busy, onSelect } = props
  const selected = rows.find((row) => row.id === selectedId)
  const [form, setForm] = useState(() => skillForm(selected))
  useEffect(() => setForm(skillForm(selected)), [selected])
  const actions = recordActions(props)
  return <div className="workspace">
    <RecordList title="Skills" rows={rows} selectedId={selectedId} busy={busy} onSelect={(id) => { if (id === null) setForm(skillForm()); onSelect(id) }} label={(row) => row.name} />
    <form className="editor-card" onSubmit={(event) => {
      event.preventDefault()
      void actions.save({ name: form.name, category: form.category, aliases: form.aliases.split(',').map((value) => value.trim()).filter(Boolean) })
    }}>
      <h2>{selected ? 'Edit skill' : 'New skill'}</h2>
      <fieldset className="evidence-fields" disabled={busy}>
        <label>Name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label>Category<input value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} /></label>
        <label>Aliases, separated by commas<input value={form.aliases} onChange={(event) => setForm({ ...form, aliases: event.target.value })} placeholder="Postgres, PostgreSQL" /></label>
        <div className="actions"><button>Save skill</button>{selected && <button type="button" className="danger" onClick={() => { void actions.archive(selected.id) }}>Archive</button>}</div>
      </fieldset>
    </form>
  </div>
}
