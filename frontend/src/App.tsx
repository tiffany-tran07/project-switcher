import { useEffect, useState, type FormEvent } from 'react'
import ResumeWorkspace from './ResumeWorkspace'
import { api, API_ROOT, save, type Bullet, type Evidence, type Experience, type Job, type Metric, type Profile, type Project, type Requirement, type RequirementMatch, type SearchResult, type Skill } from './api'

type Section = 'evidence' | 'experiences' | 'projects' | 'skills' | 'profile' | 'jobs' | 'resumes'
const emptyProfile: Profile = { name: '', email: '', phone: '', location: '', links: [] }
const emptyExperience = { organization: '', title: '', start_date: '', end_date: '', location: '', description: '' }
const emptyProject = { experience_id: '', name: '', summary: '', start_date: '', end_date: '', url: '' }
const emptySkill = { name: '', category: '', aliases: '' }
const emptyEvidence = { claim: '', source_note: '', experience_id: '', project_id: '', skill_ids: [] as string[] }
const emptyMetric = { name: '', value: '', unit: '', context: '', source_note: '' }
const emptyBullet = { text: '', tone: '', approved: false }

function dateValue(value: string | null | undefined) { return value ?? '' }
function toNullableDate(value: string) { return value || null }
function labelForExperience(row: Experience) { return `${row.title} · ${row.organization}` }

export default function App() {
  const [section, setSection] = useState<Section>('evidence')
  const [profile, setProfile] = useState<Profile>(emptyProfile)
  const [experiences, setExperiences] = useState<Experience[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [evidence, setEvidence] = useState<Evidence[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    const [nextProfile, nextExperiences, nextProjects, nextSkills, nextEvidence] = await Promise.all([
      api<Profile>('/profile'), api<Experience[]>('/experiences'), api<Project[]>('/projects'),
      api<Skill[]>('/skills'), api<Evidence[]>('/evidence'),
    ])
    setProfile(nextProfile)
    setExperiences(nextExperiences)
    setProjects(nextProjects)
    setSkills(nextSkills)
    setEvidence(nextEvidence)
  }

  useEffect(() => { load().catch((cause) => setError(String(cause))) }, [])

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(''); setNotice('')
    try { await action(); await load(); setNotice(message) }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  async function search(event: FormEvent) {
    event.preventDefault(); setError('')
    if (!query.trim()) { setResults(null); return }
    try { setResults(await api<SearchResult[]>(`/library/search?q=${encodeURIComponent(query)}`)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
  }

  function selectResult(result: SearchResult) {
    setSection(result.type === 'experience' ? 'experiences' : result.type === 'project' ? 'projects' : result.type === 'skill' ? 'skills' : 'evidence')
    setSelectedId(result.id)
    setResults(null)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">Resume Tailor</div>
        <p>Local workspace</p>
        <nav aria-label="Main navigation">
          <span className="nav-heading">CAREER LIBRARY</span>
          {(['evidence', 'experiences', 'projects', 'skills', 'jobs', 'resumes', 'profile'] as Section[]).map((item) =>
            <button key={item} className={section === item ? 'active' : ''} onClick={() => { setSection(item); setSelectedId(null); setError(''); setNotice('') }}>{item[0].toUpperCase() + item.slice(1)}</button>,
          )}
        </nav>
        <div className="sidebar-footer">Your records stay on this computer.</div>
      </aside>
      <main>
        <header className="page-head">
          <span className="eyebrow">{section === 'jobs' ? 'JOB WORKSPACE' : section === 'resumes' ? 'RESUME WORKSPACE' : 'CAREER LIBRARY'}</span>
          <h1>{section === 'jobs' ? 'Review job requirements.' : section === 'resumes' ? 'Draft from verified evidence.' : 'Build your evidence base.'}</h1>
          <p>{section === 'jobs' ? 'Paste a posting, review extracted requirements, and see what verified evidence supports them.' : section === 'resumes' ? 'Select, order, and snapshot supported claims for a targeted resume.' : 'Record what you did, where you did it, and the source that supports each claim.'}</p>
        </header>
        {section === 'resumes' ? <ResumeWorkspace evidence={evidence} projects={projects} onEvidenceSelect={(id) => { setSection('evidence'); setSelectedId(id) }} /> : section === 'jobs' ? <JobsWorkspace evidence={evidence} onEvidenceSelect={(id) => { setSection('evidence'); setSelectedId(id) }} /> : <>
        <div className="toolbar">
          <form onSubmit={search} className="search-form">
            <input aria-label="Search library" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search work, skills, and evidence" />
            <button type="submit">Search</button>
          </form>
          <a className="button secondary" href={`${API_ROOT}/library/export`} download="career-library.json">Export JSON</a>
        </div>
        {results && <div className="search-results"><h2>Search results</h2>{results.length ? results.map((result) => <button key={`${result.type}-${result.id}`} onClick={() => selectResult(result)}><span>{result.type}</span>{result.title}</button>) : <p>No matches found.</p>}</div>}
        {error && <div className="message error" role="alert">{error}</div>}
        {notice && <div className="message success" role="status">{notice}</div>}
        {section === 'profile' && <ProfileEditor profile={profile} busy={busy} onSave={(data) => run(() => save('/profile', 'PUT', data), 'Profile saved.')} />}
        {section === 'experiences' && <ExperienceEditor rows={experiences} selectedId={selectedId} busy={busy} onSelect={setSelectedId} onSave={(id, data) => run(() => save(id ? `/experiences/${id}` : '/experiences', id ? 'PATCH' : 'POST', data), 'Experience saved.')} onArchive={(id) => run(() => save(`/experiences/${id}`, 'PATCH', { archived: true }), 'Experience archived.')} />}
        {section === 'projects' && <ProjectEditor rows={projects} experiences={experiences} selectedId={selectedId} busy={busy} onSelect={setSelectedId} onSave={(id, data) => run(() => save(id ? `/projects/${id}` : '/projects', id ? 'PATCH' : 'POST', data), 'Project saved.')} onArchive={(id) => run(() => save(`/projects/${id}`, 'PATCH', { archived: true }), 'Project archived.')} />}
        {section === 'skills' && <SkillEditor rows={skills} selectedId={selectedId} busy={busy} onSelect={setSelectedId} onSave={(id, data) => run(() => save(id ? `/skills/${id}` : '/skills', id ? 'PATCH' : 'POST', data), 'Skill saved.')} onArchive={(id) => run(() => save(`/skills/${id}`, 'PATCH', { archived: true }), 'Skill archived.')} />}
        {section === 'evidence' && <EvidenceEditor rows={evidence} experiences={experiences} projects={projects} skills={skills} selectedId={selectedId} busy={busy} onSelect={setSelectedId} run={run} />}
        </>}
      </main>
    </div>
  )
}

function JobsWorkspace({ evidence, onEvidenceSelect }: { evidence: Evidence[]; onEvidenceSelect: (id: string) => void }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<string>('')
  const [company, setCompany] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [matches, setMatches] = useState<RequirementMatch[] | null>(null)
  const [requirementsDirty, setRequirementsDirty] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const job = jobs.find((item) => item.id === selected)
  async function refresh() { setJobs(await api<Job[]>('/jobs')) }
  useEffect(() => { refresh().catch((cause) => setError(String(cause))) }, [])
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const created = await save<Job>('/jobs', 'POST', { company, title, raw_description: description })
      const analyzed = await api<Job>(`/jobs/${created.id}/analyze`, { method: 'POST' })
      await refresh(); setSelected(analyzed.id); setCompany(''); setTitle(''); setDescription(''); setMatches(null); setRequirementsDirty(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) } finally { setBusy(false) }
  }
  async function reanalyze(jobId: string, method: 'deterministic' | 'ollama') {
    const selectedJob = jobs.find((item) => item.id === jobId)
    if (selectedJob?.requirements.length && !window.confirm('Replace current requirements with new suggestions? Unsaved edits will be lost.')) return
    setError('')
    try {
      const updated = await api<Job>(`/jobs/${jobId}/analyze?method=${method}&force=true`, { method: 'POST' })
      setJobs((current) => current.map((item) => item.id === updated.id ? updated : item))
      setMatches(null)
      setRequirementsDirty(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
  }
  async function review(jobId: string) {
    setSelected(jobId); setMatches(null); setError('')
    try { setMatches(await api<RequirementMatch[]>(`/jobs/${jobId}/matches`, { method: 'POST' })) }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
  }
  async function confirmRequirements(requirements: Requirement[]) {
    if (!job) return
    try {
      setError('')
      const updated = await save<Requirement[]>(`/jobs/${job.id}/requirements`, 'PATCH', { requirements })
      setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: updated } : item))
      setMatches(null)
      setRequirementsDirty(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
  }
  return <div className="job-workspace">
    {error && <div className="message error" role="alert">{error}</div>}
    <form className="editor-card job-create" onSubmit={create}><h2>Paste a job description</h2><div className="form-grid"><label>Company<input value={company} onChange={(e) => setCompany(e.target.value)} /></label><label>Role title<input required value={title} onChange={(e) => setTitle(e.target.value)} /></label></div><label>Original description<textarea required minLength={20} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Paste the full job posting…" /></label><button disabled={busy}>{busy ? 'Analyzing…' : 'Save and extract requirements'}</button></form>
    <div className="workspace"><section className="record-list"><div className="list-heading"><h2>Saved jobs</h2></div>{jobs.length ? jobs.map((item) => <button key={item.id} className={selected === item.id ? 'selected' : ''} onClick={() => { if (requirementsDirty && !window.confirm('Discard unsaved requirement edits?')) return; setSelected(item.id); setMatches(null); setRequirementsDirty(false) }}>{item.title}{item.company && ` · ${item.company}`}</button>) : <p className="empty">No job descriptions saved yet.</p>}</section>
      {job ? <section className="editor-stack"><article className="editor-card"><div className="editor-title"><h2>{job.title}{job.company && ` · ${job.company}`}</h2><div className="actions"><button type="button" className="secondary" onClick={() => { void reanalyze(job.id, 'deterministic') }}>Re-extract</button><button type="button" className="secondary" onClick={() => { void reanalyze(job.id, 'ollama') }}>Try local Ollama</button></div></div><JobDescriptionEditor key={job.id} job={job} onSave={async (changes) => { const updated = await save<Job>(`/jobs/${job.id}`, 'PATCH', changes); setJobs((current) => current.map((item) => item.id === job.id ? { ...updated, requirements: requirementsDirty ? item.requirements : updated.requirements } : item)); setMatches(null) }} /><h3>Extracted requirements <small>· editable and not yet confirmed</small></h3>{job.requirements.map((req, index) => <div className="requirement-edit" key={req.id ?? index}><input aria-label={`Requirement ${index + 1}`} value={req.text} onChange={(e) => { const next = [...job.requirements]; next[index] = { ...req, text: e.target.value, normalized_term: e.target.value.toLocaleLowerCase(), confirmed: false, supporting_span: null }; setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: next } : item)) }} /><select aria-label={`Priority for requirement ${index + 1}`} value={req.priority} onChange={(e) => { const next = [...job.requirements]; next[index] = { ...req, priority: e.target.value as Requirement['priority'] }; setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: next } : item)) }}><option value="unclear">Unclear</option><option value="required">Required</option><option value="preferred">Preferred</option></select><select aria-label={`Kind for requirement ${index + 1}`} value={req.kind} onChange={(e) => { const next = [...job.requirements]; next[index] = { ...req, kind: e.target.value as Requirement['kind'] }; setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: next } : item)) }}><option value="skill">Skill</option><option value="tool">Tool</option><option value="responsibility">Responsibility</option><option value="experience">Experience</option><option value="education">Education</option><option value="certification">Certification</option></select><label className="inline-check"><input type="checkbox" checked={req.confirmed} onChange={(e) => { const next = [...job.requirements]; next[index] = { ...req, confirmed: e.target.checked }; setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: next } : item)) }} />Confirmed</label><button type="button" className="danger" onClick={() => { setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: item.requirements.filter((_, i) => i !== index) } : item)) }}>Remove</button>{req.supporting_span && <small className="citation">From posting: “{req.supporting_span}”</small>}</div>)}<div className="actions"><button onClick={() => confirmRequirements(job.requirements).catch((cause) => setError(String(cause)))}>Save requirement edits</button><button className="secondary" onClick={() => { setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: [...item.requirements, { text: '', normalized_term: '', kind: 'responsibility', priority: 'unclear', confirmed: false }] } : item)) }}>Add requirement</button><button className="secondary" disabled={requirementsDirty} title={requirementsDirty ? 'Save requirement edits first' : undefined} onClick={() => review(job.id)}>Match verified evidence</button>{requirementsDirty && <span role="status">Save requirements before matching.</span>}</div></article>
      {matches && <article className="editor-card"><h2>Evidence match review</h2>{matches.map((result) => <div className="match-card" key={result.requirement.id}><div className="editor-title"><strong>{result.requirement.text}{!result.requirement.confirmed && <small className="review-warning"> · unconfirmed</small>}</strong><span className={`match-status ${result.status}`}>{result.status}</span></div>{result.matches.length ? result.matches.map((match) => <div className="evidence-match" key={match.evidence_id}><span>{match.status}</span><p><button type="button" className="match-link" onClick={() => onEvidenceSelect(match.evidence_id)}>{match.evidence_text}</button></p><small>{match.reason} · verified evidence</small></div>) : <p className="gap-note">No verified evidence found. This is an evidence gap, not a claim about your abilities.</p>}</div>)}</article>}
      </section> : <div className="editor-card"><p className="empty">Select a saved job to review requirements and matches.</p><small>{evidence.filter((item) => item.state === 'verified').length} verified evidence items available for matching.</small></div>}</div>
  </div>
}

function JobDescriptionEditor({ job, onSave }: { job: Job; onSave: (changes: { company: string; title: string; url: string }) => Promise<void> }) {
  const [form, setForm] = useState({ company: job.company, title: job.title, url: job.url })
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  return <details><summary>Original job description and posting details</summary><form className="description-form" onSubmit={(event) => { event.preventDefault(); setError(''); setSaved(false); onSave(form).then(() => setSaved(true)).catch((cause) => setError(String(cause))) }}><div className="form-grid"><label>Company<input value={form.company} onChange={(event) => setForm({ ...form, company: event.target.value })} /></label><label>Role title<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label></div><label>Posting URL<input type="url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} /></label><div><strong>Original description (preserved)</strong><p className="job-description">{job.raw_description}</p></div><p className="hint">To change the posting text, save a new job. You can edit extracted requirements below.</p><button>Save posting</button>{error && <span role="alert">{error}</span>}{saved && <span role="status">Posting saved.</span>}</form></details>
}

type SaveHandler = (id: string | null, data: unknown) => void
function RecordList({ title, rows, selectedId, onSelect, render }: { title: string; rows: { id: string }[]; selectedId: string | null; onSelect: (id: string | null) => void; render: (row: never) => string }) {
  return <div className="record-list"><div className="list-heading"><h2>{title}</h2><button onClick={() => onSelect(null)}>+ New</button></div>{rows.length ? rows.map((row) => <button key={row.id} className={selectedId === row.id ? 'selected' : ''} onClick={() => onSelect(row.id)}>{render(row as never)}</button>) : <p className="empty">Nothing here yet. Add your first record.</p>}</div>
}

function ProfileEditor({ profile, busy, onSave }: { profile: Profile; busy: boolean; onSave: (data: Profile) => void }) {
  const [form, setForm] = useState(profile)
  useEffect(() => setForm(profile), [profile])
  return <div className="editor-only"><form className="editor-card" onSubmit={(event) => { event.preventDefault(); onSave(form) }}><h2>Contact profile</h2><div className="form-grid"><label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label><label>Phone<input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></label><label>Location<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} /></label></div><label>Links, one per line<textarea value={form.links.join('\n')} onChange={(event) => setForm({ ...form, links: event.target.value.split('\n').filter(Boolean) })} /></label><button disabled={busy}>Save profile</button></form></div>
}

function ExperienceEditor({ rows, selectedId, busy, onSelect, onSave, onArchive }: { rows: Experience[]; selectedId: string | null; busy: boolean; onSelect: (id: string | null) => void; onSave: SaveHandler; onArchive: (id: string) => void }) {
  const selected = rows.find((row) => row.id === selectedId)
  const [form, setForm] = useState(emptyExperience)
  useEffect(() => setForm(selected ? { organization: selected.organization, title: selected.title, start_date: dateValue(selected.start_date), end_date: dateValue(selected.end_date), location: selected.location, description: selected.description } : emptyExperience), [selected])
  return <div className="workspace"><RecordList title="Experiences" rows={rows} selectedId={selectedId} onSelect={onSelect} render={(row: Experience) => labelForExperience(row)} /><form className="editor-card" onSubmit={(event) => { event.preventDefault(); onSave(selectedId, { ...form, start_date: toNullableDate(form.start_date), end_date: toNullableDate(form.end_date) }) }}><h2>{selected ? 'Edit experience' : 'New experience'}</h2><div className="form-grid"><label>Organization<input required value={form.organization} onChange={(event) => setForm({ ...form, organization: event.target.value })} /></label><label>Title<input required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><label>Start date<input type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} /></label><label>End date<input type="date" value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} /></label><label>Location<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} /></label></div><label>Description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label><div className="actions"><button disabled={busy}>Save experience</button>{selected && <button type="button" className="danger" disabled={busy} onClick={() => { onArchive(selected.id); onSelect(null) }}>Archive</button>}</div></form></div>
}

function ProjectEditor({ rows, experiences, selectedId, busy, onSelect, onSave, onArchive }: { rows: Project[]; experiences: Experience[]; selectedId: string | null; busy: boolean; onSelect: (id: string | null) => void; onSave: SaveHandler; onArchive: (id: string) => void }) {
  const selected = rows.find((row) => row.id === selectedId)
  const [form, setForm] = useState(emptyProject)
  useEffect(() => setForm(selected ? { experience_id: selected.experience_id ?? '', name: selected.name, summary: selected.summary, start_date: dateValue(selected.start_date), end_date: dateValue(selected.end_date), url: selected.url } : emptyProject), [selected])
  return <div className="workspace"><RecordList title="Projects" rows={rows} selectedId={selectedId} onSelect={onSelect} render={(row: Project) => row.name} /><form className="editor-card" onSubmit={(event) => { event.preventDefault(); onSave(selectedId, { ...form, experience_id: form.experience_id || null, start_date: toNullableDate(form.start_date), end_date: toNullableDate(form.end_date) }) }}><h2>{selected ? 'Edit project' : 'New project'}</h2><label>Name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>Linked experience<select value={form.experience_id} onChange={(event) => setForm({ ...form, experience_id: event.target.value })}><option value="">Independent project</option>{experiences.map((row) => <option key={row.id} value={row.id}>{labelForExperience(row)}</option>)}</select></label><div className="form-grid"><label>Start date<input type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} /></label><label>End date<input type="date" value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} /></label></div><label>URL<input type="url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} /></label><label>Summary<textarea value={form.summary} onChange={(event) => setForm({ ...form, summary: event.target.value })} /></label><div className="actions"><button disabled={busy}>Save project</button>{selected && <button type="button" className="danger" disabled={busy} onClick={() => { onArchive(selected.id); onSelect(null) }}>Archive</button>}</div></form></div>
}

function SkillEditor({ rows, selectedId, busy, onSelect, onSave, onArchive }: { rows: Skill[]; selectedId: string | null; busy: boolean; onSelect: (id: string | null) => void; onSave: SaveHandler; onArchive: (id: string) => void }) {
  const selected = rows.find((row) => row.id === selectedId)
  const [form, setForm] = useState(emptySkill)
  useEffect(() => setForm(selected ? { name: selected.name, category: selected.category, aliases: selected.aliases.join(', ') } : emptySkill), [selected])
  return <div className="workspace"><RecordList title="Skills" rows={rows} selectedId={selectedId} onSelect={onSelect} render={(row: Skill) => row.name} /><form className="editor-card" onSubmit={(event) => { event.preventDefault(); onSave(selectedId, { name: form.name, category: form.category, aliases: form.aliases.split(',').map((value) => value.trim()).filter(Boolean) }) }}><h2>{selected ? 'Edit skill' : 'New skill'}</h2><label>Name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label>Category<input value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} /></label><label>Aliases, separated by commas<input value={form.aliases} onChange={(event) => setForm({ ...form, aliases: event.target.value })} placeholder="Postgres, PostgreSQL" /></label><div className="actions"><button disabled={busy}>Save skill</button>{selected && <button type="button" className="danger" disabled={busy} onClick={() => { onArchive(selected.id); onSelect(null) }}>Archive</button>}</div></form></div>
}

function EvidenceEditor({ rows, experiences, projects, skills, selectedId, busy, onSelect, run }: { rows: Evidence[]; experiences: Experience[]; projects: Project[]; skills: Skill[]; selectedId: string | null; busy: boolean; onSelect: (id: string | null) => void; run: (action: () => Promise<unknown>, message: string) => Promise<void> }) {
  const selected = rows.find((row) => row.id === selectedId)
  const [form, setForm] = useState(emptyEvidence)
  const [metricForm, setMetricForm] = useState(emptyMetric)
  const [bulletForm, setBulletForm] = useState(emptyBullet)
  const [editingMetric, setEditingMetric] = useState<string | null>(null)
  const [editingBullet, setEditingBullet] = useState<string | null>(null)
  useEffect(() => { setForm(selected ? { claim: selected.claim, source_note: selected.source_note, experience_id: selected.experience_id ?? '', project_id: selected.project_id ?? '', skill_ids: selected.skill_ids } : emptyEvidence); setMetricForm(emptyMetric); setBulletForm(emptyBullet); setEditingMetric(null); setEditingBullet(null) }, [selected])
  async function saveEvidence() {
    const data = { ...form, experience_id: form.experience_id || null, project_id: form.project_id || null }
    await run(() => save(selectedId ? `/evidence/${selectedId}` : '/evidence', selectedId ? 'PATCH' : 'POST', data), 'Evidence saved. Review its verification state.')
  }
  function chooseMetric(metric: Metric) { setEditingMetric(metric.id); setMetricForm({ name: metric.name, value: metric.value, unit: metric.unit, context: metric.context, source_note: metric.source_note }) }
  function chooseBullet(bullet: Bullet) { setEditingBullet(bullet.id); setBulletForm({ text: bullet.text, tone: bullet.tone, approved: Boolean(bullet.approved_at) }) }
  return <div className="workspace"><RecordList title="Evidence" rows={rows} selectedId={selectedId} onSelect={onSelect} render={(row: Evidence) => `${row.claim} · ${row.state}`} /><div className="editor-stack"><form className="editor-card" onSubmit={(event) => { event.preventDefault(); void saveEvidence() }}><div className="editor-title"><h2>{selected ? 'Edit evidence' : 'New evidence'}</h2>{selected && <span className={`badge ${selected.state}`}>{selected.state}</span>}</div><label>Claim<textarea required value={form.claim} onChange={(event) => setForm({ ...form, claim: event.target.value })} placeholder="What did you do?" /></label><label>Source note<textarea value={form.source_note} onChange={(event) => setForm({ ...form, source_note: event.target.value })} placeholder="Where can you verify this claim?" /></label><div className="form-grid"><label>Experience<select value={form.experience_id} onChange={(event) => setForm({ ...form, experience_id: event.target.value })}><option value="">None</option>{experiences.map((row) => <option key={row.id} value={row.id}>{labelForExperience(row)}</option>)}</select></label><label>Project<select value={form.project_id} onChange={(event) => setForm({ ...form, project_id: event.target.value })}><option value="">None</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label></div><fieldset><legend>Skills demonstrated</legend><div className="skill-options">{skills.length ? skills.map((skill) => <label key={skill.id}><input type="checkbox" checked={form.skill_ids.includes(skill.id)} onChange={(event) => setForm({ ...form, skill_ids: event.target.checked ? [...form.skill_ids, skill.id] : form.skill_ids.filter((id) => id !== skill.id) })} />{skill.name}</label>) : <span>Add skills in the Skills section to link them here.</span>}</div></fieldset><div className="actions"><button disabled={busy}>Save evidence</button>{selected && <><button type="button" className="secondary" disabled={busy || !selected.source_note} onClick={() => run(() => save(`/evidence/${selected.id}`, 'PATCH', { state: 'verified' }), 'Evidence verified.')}>Verify</button><button type="button" className="secondary" disabled={busy} onClick={() => run(() => save(`/evidence/${selected.id}`, 'PATCH', { state: 'rejected' }), 'Evidence rejected.')}>Reject</button><button type="button" className="danger" disabled={busy} onClick={() => { run(() => save(`/evidence/${selected.id}`, 'PATCH', { archived: true }), 'Evidence archived.'); onSelect(null) }}>Archive</button></>}</div><p className="hint">Save changes before verifying. Editing a claim, its context, or a metric returns it to draft.</p></form>{selected && <><form className="editor-card" onSubmit={(event) => { event.preventDefault(); run(() => save(editingMetric ? `/metrics/${editingMetric}` : `/evidence/${selected.id}/metrics`, editingMetric ? 'PATCH' : 'POST', metricForm), 'Metric saved. Evidence returned to draft.'); setMetricForm(emptyMetric); setEditingMetric(null) }}><h2>Metrics</h2>{selected.metrics.map((metric) => <button type="button" className="subrecord" key={metric.id} onClick={() => chooseMetric(metric)}>{metric.name}: {metric.value} {metric.unit}</button>)}<div className="form-grid"><label>Name<input required value={metricForm.name} onChange={(event) => setMetricForm({ ...metricForm, name: event.target.value })} /></label><label>Value<input required value={metricForm.value} onChange={(event) => setMetricForm({ ...metricForm, value: event.target.value })} /></label><label>Unit<input value={metricForm.unit} onChange={(event) => setMetricForm({ ...metricForm, unit: event.target.value })} /></label></div><label>Context<textarea value={metricForm.context} onChange={(event) => setMetricForm({ ...metricForm, context: event.target.value })} /></label><label>Metric source note<textarea value={metricForm.source_note} onChange={(event) => setMetricForm({ ...metricForm, source_note: event.target.value })} /></label><div className="actions"><button disabled={busy}>{editingMetric ? 'Update metric' : 'Add metric'}</button>{editingMetric && <button type="button" className="secondary" onClick={() => { setEditingMetric(null); setMetricForm(emptyMetric) }}>Cancel edit</button>}{editingMetric && <button type="button" className="danger" disabled={busy} onClick={() => { if (window.confirm("Delete this metric?")) { void run(() => api<void>(`/metrics/${editingMetric}`, { method: "DELETE" }), "Metric deleted. Evidence returned to draft."); setEditingMetric(null); setMetricForm(emptyMetric) } }}>Delete metric</button>}</div></form><form className="editor-card" onSubmit={(event) => { event.preventDefault(); run(() => save(editingBullet ? `/bullets/${editingBullet}` : `/evidence/${selected.id}/bullets`, editingBullet ? 'PATCH' : 'POST', bulletForm), 'Bullet saved.'); setBulletForm(emptyBullet); setEditingBullet(null) }}><h2>Bullet variants</h2>{selected.bullet_variants.map((bullet) => <button type="button" className="subrecord" key={bullet.id} onClick={() => chooseBullet(bullet)}>{bullet.text} {bullet.approved_at ? '✓ Approved' : ''}</button>)}<label>Wording<textarea required value={bulletForm.text} onChange={(event) => setBulletForm({ ...bulletForm, text: event.target.value })} /></label><label>Tone<input value={bulletForm.tone} onChange={(event) => setBulletForm({ ...bulletForm, tone: event.target.value })} placeholder="Concise" /></label><label className="inline-check"><input type="checkbox" checked={bulletForm.approved} onChange={(event) => setBulletForm({ ...bulletForm, approved: event.target.checked })} />Approve this bullet</label><p className="hint">Approval requires verified evidence. Editing the evidence or metric removes approval.</p><div className="actions"><button disabled={busy}>{editingBullet ? 'Update bullet' : 'Add bullet'}</button>{editingBullet && <button type="button" className="secondary" onClick={() => { setEditingBullet(null); setBulletForm(emptyBullet) }}>Cancel edit</button>}{editingBullet && <button type="button" className="danger" disabled={busy} onClick={() => { if (window.confirm("Delete this bullet?")) { void run(() => api<void>(`/bullets/${editingBullet}`, { method: "DELETE" }), "Bullet deleted."); setEditingBullet(null); setBulletForm(emptyBullet) } }}>Delete bullet</button>}</div></form></>}</div></div>
}
