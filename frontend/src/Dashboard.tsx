import { useEffect, useState } from 'react'
import { api, type DashboardData } from './api'

type Destination = 'jobs' | 'resumes' | 'applications' | 'evidence'
type Open = (destination: Destination, id?: string) => void

export default function Dashboard({ onOpen }: { onOpen: Open }) {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let active = true
    api<DashboardData>('/dashboard')
      .then((value) => { if (active) { setData(value); setError('') } })
      .catch((cause) => { if (active) setError(String(cause)) })
    return () => { active = false }
  }, [refresh])
  if (error) return <div className="message error" role="alert"><p>{error}</p><button onClick={() => setRefresh((value) => value + 1)}>Retry dashboard</button></div>
  if (!data) return <p role="status">Loading workspace overview…</p>
  return <DashboardView data={data} onOpen={onOpen} />
}

export function DashboardView({ data, onOpen }: { data: DashboardData; onOpen: Open }) {
  const tiles: { label: string; count: number; destination: Destination }[] = [
    { label: 'Jobs', count: data.counts.jobs, destination: 'jobs' },
    { label: 'Resumes', count: data.counts.resumes, destination: 'resumes' },
    { label: 'Applications', count: data.counts.applications, destination: 'applications' },
    { label: 'Ready evidence', count: data.counts.ready_evidence, destination: 'evidence' },
    { label: 'Evidence needing review', count: data.counts.evidence_needing_review, destination: 'evidence' },
    { label: 'Follow-ups due', count: data.counts.follow_ups_due, destination: 'applications' },
  ]
  return <div className="dashboard">
    <div className="dashboard-counts">{tiles.map((tile) => <button key={tile.label} onClick={() => onOpen(tile.destination)}><strong>{tile.count}</strong><span>{tile.label}</span></button>)}</div>
    <div className="dashboard-grid">
      <section className="editor-card"><h2>Follow-ups due</h2><p className="hint">Due on or before {data.today_utc} (UTC). Rejected and withdrawn records are excluded. No messages are sent automatically.</p>{data.due_follow_ups.length ? data.due_follow_ups.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('applications', row.id)}><strong>{row.company} · {row.title}</strong><span>{row.follow_up_date} · {row.status}</span></button>) : <p className="empty">No follow-ups due.</p>}</section>
      <section className="editor-card"><h2>Evidence needing review</h2>{data.evidence_needing_review.length ? data.evidence_needing_review.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('evidence', row.id)}><strong>{row.claim}</strong><span>{row.reason}</span></button>) : <p className="empty">No evidence awaiting review. Add or review claims in the career library.</p>}<p className="hint">Only active verified evidence with available source context is ready for drafting.</p></section>
      <section className="editor-card"><h2>Recent jobs</h2>{data.recent_jobs.length ? data.recent_jobs.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('jobs', row.id)}><strong>{row.title}</strong><span>{row.company || 'Company not recorded'}</span></button>) : <p className="empty">Paste your first job description in Jobs.</p>}</section>
      <section className="editor-card"><h2>Recent resumes</h2>{data.recent_resumes.length ? data.recent_resumes.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('resumes', row.id)}><strong>{row.name}</strong><span>{row.latest_version === null ? 'No saved versions' : `Latest: v${row.latest_version}`}{row.latest_approved_version !== null && ` · Approved: v${row.latest_approved_version}`}</span></button>) : <p className="empty">Create a targeted resume from verified evidence.</p>}</section>
      <section className="editor-card"><h2>Recent applications</h2>{data.recent_applications.length ? data.recent_applications.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('applications', row.id)}><strong>{row.company} · {row.title}</strong><span>{row.status}</span></button>) : <p className="empty">Track an application once you have an approved resume snapshot.</p>}</section>
    </div>
    <p className="hint">Each list shows up to five records. Counts include all active records.</p>
  </div>
}
