import { useEffect, useState, type FormEvent } from 'react'
import { api, save, type Bullet, type Evidence, type Experience, type Metric, type Project, type Skill } from './api'
import EvidenceAttachments from './EvidenceAttachments'
import { evidenceForm, hasEvidenceEdits } from './evidenceEditing'

const emptyMetric = { name: '', value: '', unit: '', context: '', source_note: '' }
const emptyBullet = { text: '', tone: '', approved: false }
type Props = {
  rows: Evidence[]; experiences: Experience[]; projects: Project[]; skills: Skill[]
  selectedId: string | null; busy: boolean; onSelect: (id: string | null) => void
  run: (action: () => Promise<unknown>, message: string) => Promise<boolean>
}

export default function EvidenceEditor({ rows, experiences, projects, skills, selectedId, busy: saving, onSelect, run }: Props) {
  const selected = rows.find((row) => row.id === selectedId)
  const [form, setForm] = useState(() => evidenceForm(selected))
  const [metricForm, setMetricForm] = useState(emptyMetric)
  const [bulletForm, setBulletForm] = useState(emptyBullet)
  const [editingMetric, setEditingMetric] = useState<string | null>(null)
  const [editingBullet, setEditingBullet] = useState<string | null>(null)
  const [pendingAttachment, setPendingAttachment] = useState(false)
  const busy = saving || pendingAttachment
  const dirty = hasEvidenceEdits(form, selected)
  const pendingMetric = editingMetric !== null || Object.values(metricForm).some(Boolean)
  const pendingBullet = editingBullet !== null || Boolean(bulletForm.text || bulletForm.tone || bulletForm.approved)
  const pending = dirty || pendingMetric || pendingBullet || pendingAttachment

  useEffect(() => {
    setForm(evidenceForm(selected)); setMetricForm(emptyMetric); setBulletForm(emptyBullet)
    setEditingMetric(null); setEditingBullet(null); setPendingAttachment(false)
  }, [selected])

  function selectRecord(id: string | null) {
    if (busy || (id === selectedId && id !== null)) return
    if (pending && !window.confirm('Discard unsaved evidence, metric, or bullet edits?')) return
    if (id === null) {
      setForm(evidenceForm()); setMetricForm(emptyMetric); setBulletForm(emptyBullet)
      setEditingMetric(null); setEditingBullet(null)
    }
    onSelect(id)
  }

  async function saveEvidence(event: FormEvent) {
    event.preventDefault()
    if (busy || pendingMetric || pendingBullet) return
    let saved: Evidence | undefined
    const success = await run(async () => {
      saved = await save<Evidence>(selected ? `/evidence/${selected.id}` : '/evidence', selected ? 'PATCH' : 'POST', {
        ...form, experience_id: form.experience_id || null, project_id: form.project_id || null,
      })
    }, 'Evidence saved. Review its verification state.')
    if (success && saved) onSelect(saved.id)
  }

  async function saveMetric(event: FormEvent) {
    event.preventDefault()
    if (!selected || busy || dirty || pendingBullet) return
    const success = await run(() => save(
      editingMetric ? `/metrics/${editingMetric}` : `/evidence/${selected.id}/metrics`,
      editingMetric ? 'PATCH' : 'POST', metricForm,
    ), 'Metric saved. Evidence returned to draft.')
    if (success) { setMetricForm(emptyMetric); setEditingMetric(null) }
  }

  async function saveBullet(event: FormEvent) {
    event.preventDefault()
    if (!selected || busy || dirty || pendingMetric || (bulletForm.approved && selected.state !== 'verified')) return
    const success = await run(() => save(
      editingBullet ? `/bullets/${editingBullet}` : `/evidence/${selected.id}/bullets`,
      editingBullet ? 'PATCH' : 'POST', bulletForm,
    ), 'Bullet saved.')
    if (success) { setBulletForm(emptyBullet); setEditingBullet(null) }
  }

  function chooseMetric(metric: Metric) {
    if (pendingMetric && !window.confirm('Discard the current unsaved metric form?')) return
    setEditingMetric(metric.id)
    setMetricForm({ name: metric.name, value: metric.value, unit: metric.unit, context: metric.context, source_note: metric.source_note })
  }

  function chooseBullet(bullet: Bullet) {
    if (pendingBullet && !window.confirm('Discard the current unsaved bullet form?')) return
    setEditingBullet(bullet.id)
    setBulletForm({ text: bullet.text, tone: bullet.tone, approved: Boolean(bullet.approved_at) })
  }

  async function deleteMetric() {
    if (!editingMetric || busy || dirty || pendingBullet || !window.confirm('Delete this metric?')) return
    if (await run(() => api<void>(`/metrics/${editingMetric}`, { method: 'DELETE' }), 'Metric deleted. Evidence returned to draft.')) {
      setEditingMetric(null); setMetricForm(emptyMetric)
    }
  }

  async function deleteBullet() {
    if (!editingBullet || busy || dirty || pendingMetric || !window.confirm('Delete this bullet?')) return
    if (await run(() => api<void>(`/bullets/${editingBullet}`, { method: 'DELETE' }), 'Bullet deleted.')) {
      setEditingBullet(null); setBulletForm(emptyBullet)
    }
  }

  async function archive() {
    if (!selected || busy || pending) return
    if (await run(() => save(`/evidence/${selected.id}`, 'PATCH', { archived: true }), 'Evidence archived.')) onSelect(null)
  }

  const experienceLabel = (row: Experience) => `${row.title} · ${row.organization}`
  return <div className="workspace">
    <section className="record-list"><div className="list-heading"><h2>Evidence</h2><button disabled={busy} onClick={() => selectRecord(null)}>+ New</button></div>
      {rows.length ? rows.map((row) => <button disabled={busy} key={row.id} className={selectedId === row.id ? 'selected' : ''} onClick={() => selectRecord(row.id)}>{row.claim} · {row.state}</button>) : <p className="empty">Nothing here yet. Add your first record.</p>}
    </section>
    <div className="editor-stack">
      <form className="editor-card" onSubmit={(event) => { void saveEvidence(event) }}>
        <div className="editor-title"><h2>{selected ? 'Edit evidence' : 'New evidence'}</h2>{selected && <span className={`badge ${selected.state}`}>{selected.state}</span>}</div>
        <fieldset className="evidence-fields" disabled={busy}>
          <label>Claim<textarea required value={form.claim} onChange={(event) => setForm({ ...form, claim: event.target.value })} placeholder="What did you do?" /></label>
          <label>Source note<textarea value={form.source_note} onChange={(event) => setForm({ ...form, source_note: event.target.value })} placeholder="Where can you verify this claim?" /></label>
          <div className="form-grid"><label>Experience<select value={form.experience_id} onChange={(event) => setForm({ ...form, experience_id: event.target.value })}><option value="">None</option>{experiences.map((row) => <option value={row.id} key={row.id}>{experienceLabel(row)}</option>)}</select></label><label>Project<select value={form.project_id} onChange={(event) => setForm({ ...form, project_id: event.target.value })}><option value="">None</option>{projects.map((row) => <option value={row.id} key={row.id}>{row.name}</option>)}</select></label></div>
          <fieldset><legend>Skills demonstrated</legend><div className="skill-options">{skills.length ? skills.map((skill) => <label key={skill.id}><input type="checkbox" checked={form.skill_ids.includes(skill.id)} onChange={(event) => setForm({ ...form, skill_ids: event.target.checked ? [...form.skill_ids, skill.id] : form.skill_ids.filter((id) => id !== skill.id) })} />{skill.name}</label>) : <span>Add skills in the Skills section to link them here.</span>}</div></fieldset>
        </fieldset>
        <div className="actions">
          <button disabled={busy || pendingMetric || pendingBullet}>Save evidence</button>
          {selected && <>
            {dirty && <button type="button" className="secondary" disabled={busy} onClick={() => setForm(evidenceForm(selected))}>Reset evidence edits</button>}
            <button type="button" className="secondary" disabled={busy || pending || !selected.source_note.trim() || selected.state === 'verified'} onClick={() => { if (!pending) void run(() => save(`/evidence/${selected.id}`, 'PATCH', { state: 'verified' }), 'Evidence verified.') }}>Verify</button>
            <button type="button" className="secondary" disabled={busy || pending} onClick={() => { void run(() => save(`/evidence/${selected.id}`, 'PATCH', { state: 'rejected' }), 'Evidence rejected.') }}>Reject</button>
            <button type="button" className="danger" disabled={busy || pending} onClick={() => { void archive() }}>Archive</button>
          </>}
        </div>
        {dirty && <p className="hint" role="status">Unsaved evidence changes. Save or reset them before verification or editing subrecords.</p>}
        {(pendingMetric || pendingBullet) && <p className="hint">Save or clear the metric/bullet form before saving or verifying evidence.</p>}
        {pendingAttachment && <p className="hint">Attach or clear the selected source file before editing or verifying evidence.</p>}
        <p className="hint">Verification applies only to the saved claim. Editing a claim, its context, or a metric returns it to draft.</p>
      </form>
      {selected && <>
        <EvidenceAttachments key={selected.id} evidenceId={selected.id} blocked={saving || dirty || pendingMetric || pendingBullet} onPendingChange={setPendingAttachment} run={run} />
        <form className="editor-card" onSubmit={(event) => { void saveMetric(event) }}><h2>Metrics</h2>
          {selected.metrics.map((metric) => <button type="button" className="subrecord" disabled={busy || dirty || pendingBullet} key={metric.id} onClick={() => chooseMetric(metric)}>{metric.name}: {metric.value} {metric.unit}</button>)}
          <fieldset className="evidence-fields" disabled={busy || dirty || pendingBullet}>
            <div className="form-grid"><label>Name<input required value={metricForm.name} onChange={(event) => setMetricForm({ ...metricForm, name: event.target.value })} /></label><label>Value<input required value={metricForm.value} onChange={(event) => setMetricForm({ ...metricForm, value: event.target.value })} /></label><label>Unit<input value={metricForm.unit} onChange={(event) => setMetricForm({ ...metricForm, unit: event.target.value })} /></label></div>
            <label>Context<textarea value={metricForm.context} onChange={(event) => setMetricForm({ ...metricForm, context: event.target.value })} /></label>
            <label>Metric source note<textarea value={metricForm.source_note} onChange={(event) => setMetricForm({ ...metricForm, source_note: event.target.value })} /></label>
          </fieldset>
          <div className="actions"><button disabled={busy || dirty || pendingBullet}>{editingMetric ? 'Update metric' : 'Add metric'}</button>
            {pendingMetric && <button type="button" className="secondary" disabled={busy} onClick={() => { setEditingMetric(null); setMetricForm(emptyMetric) }}>{editingMetric ? 'Cancel edit' : 'Clear metric form'}</button>}
            {editingMetric && <button type="button" className="danger" disabled={busy || dirty || pendingBullet} onClick={() => { void deleteMetric() }}>Delete metric</button>}
          </div>
        </form>
        <form className="editor-card" onSubmit={(event) => { void saveBullet(event) }}><h2>Bullet variants</h2>
          {selected.bullet_variants.map((bullet) => <button type="button" className="subrecord" disabled={busy || dirty || pendingMetric} key={bullet.id} onClick={() => chooseBullet(bullet)}>{bullet.text} {bullet.approved_at ? '✓ Approved' : ''}</button>)}
          <fieldset className="evidence-fields" disabled={busy || dirty || pendingMetric}>
            <label>Wording<textarea required value={bulletForm.text} onChange={(event) => setBulletForm({ ...bulletForm, text: event.target.value })} /></label>
            <label>Tone<input value={bulletForm.tone} onChange={(event) => setBulletForm({ ...bulletForm, tone: event.target.value })} placeholder="Concise" /></label>
            <label className="inline-check"><input type="checkbox" checked={bulletForm.approved} disabled={selected.state !== 'verified'} onChange={(event) => setBulletForm({ ...bulletForm, approved: event.target.checked })} />Approve this bullet</label>
          </fieldset>
          <p className="hint">Approval requires verified evidence. Editing the evidence or metric removes approval.</p>
          <div className="actions"><button disabled={busy || dirty || pendingMetric || (bulletForm.approved && selected.state !== 'verified')}>{editingBullet ? 'Update bullet' : 'Add bullet'}</button>
            {pendingBullet && <button type="button" className="secondary" disabled={busy} onClick={() => { setEditingBullet(null); setBulletForm(emptyBullet) }}>{editingBullet ? 'Cancel edit' : 'Clear bullet form'}</button>}
            {editingBullet && <button type="button" className="danger" disabled={busy || dirty || pendingMetric} onClick={() => { void deleteBullet() }}>Delete bullet</button>}
          </div>
        </form>
      </>}
    </div>
  </div>
}
