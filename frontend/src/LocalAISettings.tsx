import { useEffect, useState } from 'react'
import { api, type LocalAICheck, type LocalAIConfig } from './api'

export default function LocalAISettings() {
  const [config, setConfig] = useState<LocalAIConfig | null>(null)
  const [check, setCheck] = useState<LocalAICheck | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api<LocalAIConfig>('/local-ai/config')
      .then((value) => { if (active) setConfig(value) })
      .catch((cause) => { if (active) setError(String(cause)) })
    return () => { active = false }
  }, [])

  async function diagnose() {
    setBusy(true); setError(''); setCheck(null)
    try { setCheck(await api<LocalAICheck>('/local-ai/check', { method: 'POST' })) }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) }
    finally { setBusy(false) }
  }

  return <section className="editor-card editor-only" aria-label="Local AI settings">
    <h2>Optional local AI</h2>
    <p>Core features work without AI. File intake, evidence verification, and resume drafting do not call a model.</p>
    {config ? <>
      <dl className="local-ai-config"><dt>Endpoint</dt><dd>{config.endpoint ?? 'Blocked configuration (URL hidden)'}</dd><dt>Model</dt><dd>{config.model || 'No model selected'}</dd></dl>
      <p>{config.message}</p>
    </> : <p role="status">Loading local AI configuration…</p>}
    <p className="hint">Only plain localhost HTTP is allowed, pinned to 127.0.0.1 without DNS. Environment proxies and redirects are disabled. Edit OLLAMA_BASE_URL and OLLAMA_CHAT_MODEL in .env, then restart the backend to change configuration.</p>
    <div className="actions"><button type="button" disabled={!config?.allowed || busy} onClick={() => { void diagnose() }}>{busy ? 'Checking…' : 'Check local runtime'}</button></div>
    <p className="hint">This check requests model inventory only; it sends no resume, evidence, or job text and does not download models.</p>
    {check && <p className={`message ${check.runtime_available ? 'success' : 'warning'}`} role="status">{check.message}</p>}
    {error && <p className="message error" role="alert">{error}</p>}
  </section>
}
