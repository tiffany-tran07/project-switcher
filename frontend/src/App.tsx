import { useEffect, useState, type FormEvent } from 'react'
import ResumeWorkspace from './ResumeWorkspace'
import EvidenceEditor from './EvidenceEditor'
import ProfileEditor from './ProfileEditor'
import { ExperienceEditor, ProjectEditor, SkillEditor } from './CareerEditors'
import ArchiveWorkspace from './ArchiveWorkspace'
import ApplicationsWorkspace from './ApplicationsWorkspace'
import BackupSettings from './BackupSettings'
import Dashboard from './Dashboard'
import ResumeIntake from './ResumeIntake'
import LocalAISettings from './LocalAISettings'
import AnalysisNotice from './AnalysisNotice'
import { updateWorkingDraft, type WorkingDrafts } from './resumeDraft'
import { api, API_ROOT, save, type Evidence, type Experience, type Job, type Profile, type Project, type Requirement, type RequirementMatch, type SearchResult, type Skill } from './api'

type Section = 'evidence' | 'experiences' | 'projects' | 'skills' | 'profile' | 'jobs' | 'resumes' | 'applications' | 'settings' | 'dashboard' | 'intake' | 'archive'
const emptyProfile: Profile = { name: '', email: '', phone: '', location: '', links: [] }

export default function App() {
  const [section, setSection] = useState<Section>('dashboard')
  const [profile, setProfile] = useState<Profile>(emptyProfile)
  const [experiences, setExperiences] = useState<Experience[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [skills, setSkills] = useState<Skill[]>([])
  const [evidence, setEvidence] = useState<Evidence[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [lastResumeId, setLastResumeId] = useState<string | null>(null)
  const [workingResumeDrafts, setWorkingResumeDrafts] = useState<WorkingDrafts>({})
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
    let saved = false
    try { await action(); saved = true; await load(); setNotice(message); return true }
    catch (cause) {
      const detail = cause instanceof Error ? cause.message : String(cause)
      setError(saved ? `Saved, but refreshing failed. Reload the page before retrying. ${detail}` : detail)
      return false
    }
    finally { setBusy(false) }
  }

  async function saveCareerRecord(collection: 'experiences' | 'projects' | 'skills', id: string | null, data: unknown, message: string): Promise<string | null> {
    let saved: { id: string } | undefined
    const success = await run(async () => {
      saved = await save<{ id: string }>(id ? `/${collection}/${encodeURIComponent(id)}` : `/${collection}`, id ? 'PATCH' : 'POST', data)
    }, message)
    return success && saved ? saved.id : null
  }

  async function refreshLibrary() {
    setBusy(true); setError(''); setNotice('')
    try { await load(); setNotice('Library refreshed.') }
    catch (cause) { setError(`Could not refresh the career library. ${cause instanceof Error ? cause.message : String(cause)}`) }
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
          {(['dashboard', 'intake', 'evidence', 'experiences', 'projects', 'skills', 'archive', 'jobs', 'resumes', 'applications', 'profile', 'settings'] as Section[]).map((item) =>
            <button key={item} disabled={busy} className={section === item ? 'active' : ''} onClick={() => { setSection(item); setSelectedId(null); setError(''); setNotice('') }}>{item[0].toUpperCase() + item.slice(1)}</button>,
          )}
        </nav>
        <div className="sidebar-footer">Your records stay on this computer.</div>
      </aside>
      <main>
        <header className="page-head">
          <span className="eyebrow">{section === 'archive' ? 'CAREER ARCHIVE' : section === 'intake' ? 'RESUME INTAKE' : section === 'dashboard' ? 'LOCAL WORKSPACE' : section === 'settings' ? 'SETTINGS' : section === 'applications' ? 'APPLICATION TRACKER' : section === 'jobs' ? 'JOB WORKSPACE' : section === 'resumes' ? 'RESUME WORKSPACE' : 'CAREER LIBRARY'}</span>
          <h1>{section === 'archive' ? 'Recover archived work.' : section === 'intake' ? 'Start from your existing resume.' : section === 'dashboard' ? 'Your resume workspace.' : section === 'settings' ? 'Protect your local data.' : section === 'applications' ? 'Track your applications.' : section === 'jobs' ? 'Review job requirements.' : section === 'resumes' ? 'Draft from verified evidence.' : 'Build your evidence base.'}</h1>
          <p>{section === 'archive' ? 'Restore source records without rewriting past resume snapshots.' : section === 'intake' ? 'Preview its text, then review claims before adding them to your evidence library.' : section === 'dashboard' ? 'Pick up where you left off and see what needs attention.' : section === 'settings' ? 'Create a portable backup of your evidence, resumes, and application history.' : section === 'applications' ? 'Keep your status history and the exact resume snapshot used for each job.' : section === 'jobs' ? 'Paste a posting, review extracted requirements, and see what verified evidence supports them.' : section === 'resumes' ? 'Select, order, and snapshot supported claims for a targeted resume.' : 'Record what you did, where you did it, and the source that supports each claim.'}</p>
        </header>
        {section === 'archive' ? <ArchiveWorkspace onRestored={load} /> : section === 'intake' ? <ResumeIntake experiences={experiences} projects={projects} onExperienceCreated={(row) => setExperiences((current) => [row, ...current.filter((item) => item.id !== row.id)])} onProjectCreated={(row) => setProjects((current) => [row, ...current.filter((item) => item.id !== row.id)])} onDraftSaved={(row) => setEvidence((current) => [row, ...current.filter((item) => item.id !== row.id)])} onOpenEvidence={(id) => { setSelectedId(id); setSection('evidence') }} /> : section === 'dashboard' ? <Dashboard onOpen={(destination, id) => { setSection(destination); setSelectedId(id ?? null); if (destination === 'resumes' && id) setLastResumeId(id) }} /> : section === 'settings' ? <div className="editor-stack"><LocalAISettings /><BackupSettings /></div> : section === 'applications' ? <ApplicationsWorkspace initialApplicationId={selectedId ?? undefined} onEvidenceSelect={(id) => { setSection('evidence'); setSelectedId(id) }} /> : section === 'resumes' ? <ResumeWorkspace initialResumeId={selectedId ?? lastResumeId ?? undefined} workingDrafts={workingResumeDrafts} onWorkingDraftChange={(id, update) => setWorkingResumeDrafts((current) => updateWorkingDraft(current, id, update))} onResumeSelect={(id) => { setLastResumeId(id || null); setSelectedId(id || null) }} evidence={evidence} projects={projects} onEvidenceSelect={(id) => { setSection('evidence'); setSelectedId(id) }} /> : section === 'jobs' ? <JobsWorkspace initialJobId={selectedId ?? undefined} evidence={evidence} onEvidenceSelect={(id) => { setSection('evidence'); setSelectedId(id) }} /> : <>
        <div className="toolbar">
          <form onSubmit={search} className="search-form">
            <input aria-label="Search library" disabled={busy} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search work, skills, and evidence" />
            <button type="submit" disabled={busy}>Search</button>
          </form>
          <a className="button secondary" href={`${API_ROOT}/library/export`} download="career-library.json">Export JSON</a>
        </div>
        {results && <div className="search-results"><h2>Search results</h2>{results.length ? results.map((result) => <button key={`${result.type}-${result.id}`} disabled={busy} onClick={() => selectResult(result)}><span>{result.type}</span>{result.title}</button>) : <p>No matches found.</p>}</div>}
        {error && <div className="message error" role="alert">{error}</div>}
        {notice && <div className="message success" role="status">{notice}</div>}
        {section === 'profile' && <ProfileEditor profile={profile} busy={busy} onSave={(data) => run(() => save('/profile', 'PUT', data), 'Profile saved.')} />}
        {section === 'experiences' && <ExperienceEditor rows={experiences} selectedId={selectedId} busy={busy} onSelect={setSelectedId} onSave={(id, data) => saveCareerRecord('experiences', id, data, 'Experience saved.')} onArchive={(id) => run(() => save(`/experiences/${id}`, 'PATCH', { archived: true }), 'Experience archived.')} />}
        {section === 'projects' && <ProjectEditor rows={projects} experiences={experiences} selectedId={selectedId} busy={busy} onSelect={setSelectedId} onSave={(id, data) => saveCareerRecord('projects', id, data, 'Project saved.')} onArchive={(id) => run(() => save(`/projects/${id}`, 'PATCH', { archived: true }), 'Project archived.')} />}
        {section === 'skills' && <SkillEditor rows={skills} selectedId={selectedId} busy={busy} onSelect={setSelectedId} onSave={(id, data) => saveCareerRecord('skills', id, data, 'Skill saved.')} onArchive={(id) => run(() => save(`/skills/${id}`, 'PATCH', { archived: true }), 'Skill archived.')} />}
        {section === 'evidence' && <EvidenceEditor rows={evidence} experiences={experiences} projects={projects} skills={skills} selectedId={selectedId} busy={busy} onSelect={setSelectedId} run={run} onRefresh={() => { void refreshLibrary() }} onOpenArchive={() => { setSection('archive'); setSelectedId(null); setError(''); setNotice('') }} />}
        </>}
      </main>
    </div>
  )
}

function JobsWorkspace({ evidence, onEvidenceSelect, initialJobId }: { evidence: Evidence[]; onEvidenceSelect: (id: string) => void; initialJobId?: string }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<string>(initialJobId ?? '')
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
      await refresh(); setJobs((current) => current.map((item) => item.id === analyzed.id ? analyzed : item)); setSelected(analyzed.id); setCompany(''); setTitle(''); setDescription(''); setMatches(null); setRequirementsDirty(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) } finally { setBusy(false) }
  }
  async function reanalyze(jobId: string, method: 'deterministic' | 'ollama') {
    if (busy) return
    const selectedJob = jobs.find((item) => item.id === jobId)
    if (selectedJob?.requirements.length && !window.confirm('Replace current requirements with new suggestions? Unsaved edits will be lost.')) return
    setError(''); setBusy(true)
    try {
      const updated = await api<Job>(`/jobs/${jobId}/analyze?method=${method}&force=true`, { method: 'POST' })
      const keepEdits = Boolean(updated.analysis?.fallback && requirementsDirty)
      setJobs((current) => current.map((item) => item.id === updated.id ? { ...updated, requirements: keepEdits ? item.requirements : updated.requirements } : item))
      setMatches(null)
      setRequirementsDirty(keepEdits)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }
  async function review(jobId: string) {
    if (busy) return
    setSelected(jobId); setMatches(null); setError(''); setBusy(true)
    try { setMatches(await api<RequirementMatch[]>(`/jobs/${jobId}/matches`, { method: 'POST' })) }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }
  async function confirmRequirements(requirements: Requirement[]) {
    if (!job || busy) return
    setBusy(true)
    try {
      setError('')
      const updated = await save<Requirement[]>(`/jobs/${job.id}/requirements`, 'PATCH', { requirements })
      setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: updated } : item))
      setMatches(null)
      setRequirementsDirty(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }
  return <div className="job-workspace">
    {error && <div className="message error" role="alert">{error}</div>}
    <form className="editor-card job-create" onSubmit={create}><h2>Paste a job description</h2><div className="form-grid"><label>Company<input value={company} onChange={(e) => setCompany(e.target.value)} /></label><label>Role title<input required value={title} onChange={(e) => setTitle(e.target.value)} /></label></div><label>Original description<textarea required minLength={20} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Paste the full job posting…" /></label><button disabled={busy}>{busy ? 'Analyzing…' : 'Save and extract requirements'}</button></form>
    <div className="workspace"><section className="record-list"><div className="list-heading"><h2>Saved jobs</h2></div>{jobs.length ? jobs.map((item) => <button key={item.id} className={selected === item.id ? 'selected' : ''} disabled={busy} onClick={() => { if (requirementsDirty && !window.confirm('Discard unsaved requirement edits?')) return; setSelected(item.id); setMatches(null); setRequirementsDirty(false) }}>{item.title}{item.company && ` · ${item.company}`}</button>) : <p className="empty">No job descriptions saved yet.</p>}</section>
      {job ? <section className="editor-stack"><article className="editor-card"><fieldset className="review-fields" disabled={busy}><div className="editor-title"><h2>{job.title}{job.company && ` · ${job.company}`}</h2><div className="actions"><button type="button" className="secondary" onClick={() => { void reanalyze(job.id, 'deterministic') }}>Re-extract</button><button type="button" className="secondary" onClick={() => { void reanalyze(job.id, 'ollama') }}>Try local Ollama</button></div></div><p className="hint">Optional Ollama extraction sends only this job description to the configured local runtime. View its endpoint and model in Settings. Deterministic extraction makes no model call.</p>{job.analysis && <AnalysisNotice outcome={job.analysis} />}<JobDescriptionEditor key={job.id} job={job} onSave={async (changes) => { const updated = await save<Job>(`/jobs/${job.id}`, 'PATCH', changes); setJobs((current) => current.map((item) => item.id === job.id ? { ...updated, requirements: requirementsDirty ? item.requirements : updated.requirements } : item)); setMatches(null) }} /><h3>Extracted requirements <small>· editable and not yet confirmed</small></h3>{job.requirements.map((req, index) => <div className="requirement-edit" key={req.id ?? index}><input aria-label={`Requirement ${index + 1}`} value={req.text} onChange={(e) => { const next = [...job.requirements]; next[index] = { ...req, text: e.target.value, normalized_term: e.target.value.toLocaleLowerCase(), confirmed: false, supporting_span: null }; setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: next } : item)) }} /><select aria-label={`Priority for requirement ${index + 1}`} value={req.priority} onChange={(e) => { const next = [...job.requirements]; next[index] = { ...req, priority: e.target.value as Requirement['priority'] }; setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: next } : item)) }}><option value="unclear">Unclear</option><option value="required">Required</option><option value="preferred">Preferred</option></select><select aria-label={`Kind for requirement ${index + 1}`} value={req.kind} onChange={(e) => { const next = [...job.requirements]; next[index] = { ...req, kind: e.target.value as Requirement['kind'] }; setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: next } : item)) }}><option value="skill">Skill</option><option value="tool">Tool</option><option value="responsibility">Responsibility</option><option value="experience">Experience</option><option value="education">Education</option><option value="certification">Certification</option></select><label className="inline-check"><input type="checkbox" checked={req.confirmed} onChange={(e) => { const next = [...job.requirements]; next[index] = { ...req, confirmed: e.target.checked }; setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: next } : item)) }} />Confirmed</label><button type="button" className="danger" onClick={() => { setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: item.requirements.filter((_, i) => i !== index) } : item)) }}>Remove</button>{req.supporting_span && <small className="citation">From posting: “{req.supporting_span}”</small>}</div>)}<div className="actions"><button onClick={() => confirmRequirements(job.requirements).catch((cause) => setError(String(cause)))}>Save requirement edits</button><button className="secondary" onClick={() => { setRequirementsDirty(true); setJobs((current) => current.map((item) => item.id === job.id ? { ...item, requirements: [...item.requirements, { text: '', normalized_term: '', kind: 'responsibility', priority: 'unclear', confirmed: false }] } : item)) }}>Add requirement</button><button className="secondary" disabled={requirementsDirty} title={requirementsDirty ? 'Save requirement edits first' : undefined} onClick={() => review(job.id)}>Match verified evidence</button>{requirementsDirty && <span role="status">Save requirements before matching.</span>}</div></fieldset></article>
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
