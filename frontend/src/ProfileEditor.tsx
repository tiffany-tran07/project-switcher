import { useEffect, useState } from 'react'
import type { Profile } from './api'
import { profileDraft, profilePayload } from './profileDraft'

export default function ProfileEditor({ profile, busy, onSave }: { profile: Profile; busy: boolean; onSave: (data: Profile) => void }) {
  const [form, setForm] = useState(() => profileDraft(profile))
  useEffect(() => setForm(profileDraft(profile)), [profile])
  return <div className="editor-only"><form className="editor-card" onSubmit={(event) => {
    event.preventDefault()
    if (!busy) onSave(profilePayload(form))
  }}>
    <h2>Contact profile</h2>
    <fieldset className="evidence-fields" disabled={busy}>
      <div className="form-grid">
        <label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label>Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
        <label>Phone<input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></label>
        <label>Location<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} /></label>
      </div>
      <label>Links, one per line<textarea value={form.linksText} onChange={(event) => setForm({ ...form, linksText: event.target.value })} /></label>
      <p className="hint">Blank lines and surrounding link whitespace are removed only when saving. Profile edits do not change existing resume snapshots. Save before leaving this page.</p>
      <button>Save profile</button>
    </fieldset>
  </form></div>
}
