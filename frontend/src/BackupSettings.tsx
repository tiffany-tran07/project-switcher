import { useState } from 'react'
import { downloadBackup } from './api'

export default function BackupSettings() {
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function download() {
    if (!acknowledged) return
    setBusy(true); setError(''); setNotice('')
    try {
      const blob = await downloadBackup()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      try {
        link.href = url; link.download = 'resume-backup.zip'
        document.body.appendChild(link); link.click()
      } finally {
        link.remove()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
      setNotice('Backup download started. Keep it in a private location.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  return <section className="editor-card editor-only" aria-label="Backup settings">
    <h2>Portable backup</h2>
    <p>Download a consistent SQLite snapshot, attachments, and registered resume exports with a checksum manifest.</p>
    <p className="message error">Backups contain personal data, source notes, and application history. They are not encrypted. Store them privately and avoid public repositories or shared folders.</p>
    <label className="inline-check"><input type="checkbox" disabled={busy} checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />I understand this backup contains unencrypted personal data.</label>
    <div className="actions"><button type="button" disabled={busy || !acknowledged} onClick={() => { void download() }}>{busy ? 'Preparing backup…' : 'Download backup'}</button></div>
    {error && <p className="message error" role="alert">{error}</p>}
    {notice && <p className="message success" role="status">{notice}</p>}
    <h3>Restore safely into a new directory</h3>
    <p>Restore is available from the backend command line. Existing directories and the active data directory are never overwritten. Use only backups you created and trust; checksums detect corruption, not authorship.</p>
    <pre className="restore-command">{'# From backend, with the project virtual environment active:\npython -m app.restore /path/to/resume-backup.zip --check-only\npython -m app.restore /path/to/resume-backup.zip --destination /new/data-directory'}</pre>
    <p className="hint">The destination must not exist, and its parent must already exist. After restore succeeds, stop the API, set DATA_DIR to the new absolute path, clear DATABASE_URL, and restart. Keep the original data until you have reviewed the restored installation.</p>
    <p className="hint">Backups omit .env, runtime dependencies, temporary files, and unregistered export artifacts. Limit: 256 MB uncompressed, 2,000 data files. Missing or damaged registered export files must be repaired first; generating a new artifact does not replace the original record.</p>
  </section>
}
