import { useEffect, useState } from 'react'
import { api, type DashboardData } from './api'
import WorkspaceIcon from './WorkspaceIcon'

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
    { label: 'Ready achievements', count: data.counts.ready_evidence, destination: 'evidence' },
    { label: 'Achievements needing review', count: data.counts.evidence_needing_review, destination: 'evidence' },
    { label: 'Follow-ups due', count: data.counts.follow_ups_due, destination: 'applications' },
  ]
  return <div className="dashboard">
    <section className="dashboard-welcome" aria-labelledby="welcome-title">
      <div className="welcome-copy"><span className="eyebrow">BUILT ON YOUR EXPERIENCE</span><h2 id="welcome-title">Your story. A stronger next chapter.</h2><p>Turn the work you’ve done into a resume that opens the right doors. One verified detail at a time.</p><div className="actions"><button onClick={() => onOpen('resumes')}>Work on a resume <WorkspaceIcon name="arrow" /></button><button className="secondary" onClick={() => onOpen('jobs')}>Explore saved jobs</button></div></div>
      <div className="welcome-art" aria-hidden="true"><div className="art-orbit" /><div className="art-paper"><span className="art-monogram">You, on paper.</span><i /><i /><div className="art-rule" /><b>EXPERIENCE THAT MATTERS</b><i /><i /><i /><div className="art-rule" /><b>A NEXT CHAPTER, WELL TOLD.</b><i /><i /></div><span className="art-seal"><WorkspaceIcon name="evidence" /></span></div>
    </section>
    <div className="section-heading"><h2>Your workspace at a glance</h2><span>Small steps. Real progress.</span></div>
    <div className="dashboard-counts">{tiles.map((tile, index) => <button key={tile.label} className={index > 3 ? 'attention-tile' : ''} onClick={() => onOpen(tile.destination)}><span className="stat-top"><WorkspaceIcon name={tile.destination} /><WorkspaceIcon name="arrow" /></span><strong>{String(tile.count).padStart(2, '0')}</strong><span>{tile.label}</span></button>)}</div>
    <div className="section-heading"><h2>Pick up where you left off</h2><span>Your next move starts here</span></div>
    <div className="dashboard-grid">
      <section className="editor-card"><h2>Follow-ups due</h2><p className="hint">Due on or before {data.today_utc} (UTC). Rejected and withdrawn records are excluded. No messages are sent automatically.</p>{data.due_follow_ups.length ? data.due_follow_ups.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('applications', row.id)}><strong>{row.company} · {row.title}</strong><span>{row.follow_up_date} · {row.status}</span></button>) : <p className="empty">No follow-ups due.</p>}</section>
      <section className="editor-card"><h2>Achievements needing review</h2>{data.evidence_needing_review.length ? data.evidence_needing_review.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('evidence', row.id)}><strong>{row.claim}</strong><span>{row.reason}</span></button>) : <p className="empty">No achievements awaiting review. Add or review achievements in the career library.</p>}<p className="hint">Only active verified achievements with available source context are ready for drafting.</p></section>
      <section className="editor-card"><h2>Recent jobs</h2>{data.recent_jobs.length ? data.recent_jobs.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('jobs', row.id)}><strong>{row.title}</strong><span>{row.company || 'Company not recorded'}</span></button>) : <p className="empty">Paste your first job description in Jobs.</p>}</section>
      <section className="editor-card"><h2>Recent resumes</h2>{data.recent_resumes.length ? data.recent_resumes.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('resumes', row.id)}><strong>{row.name}</strong><span>{row.latest_version === null ? 'No saved versions' : `Latest: v${row.latest_version}`}{row.latest_approved_version !== null && ` · Approved: v${row.latest_approved_version}`}</span></button>) : <p className="empty">Create a targeted resume from verified achievements.</p>}</section>
      <section className="editor-card"><h2>Recent applications</h2>{data.recent_applications.length ? data.recent_applications.map((row) => <button className="dashboard-row" key={row.id} onClick={() => onOpen('applications', row.id)}><strong>{row.company} · {row.title}</strong><span>{row.status}</span></button>) : <p className="empty">Track an application once you have an approved resume snapshot.</p>}</section>
    </div>
    <p className="hint">Each list shows up to five records. Counts include all active records.</p>
  </div>
}
