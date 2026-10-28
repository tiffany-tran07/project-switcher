import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { DashboardView } from './Dashboard'
import type { DashboardData } from './api'

function empty(): DashboardData {
  return {
    today_utc: '2026-10-28',
    counts: { jobs: 0, resumes: 0, applications: 0, ready_evidence: 0, evidence_needing_review: 0, follow_ups_due: 0 },
    recent_jobs: [], recent_resumes: [], recent_applications: [], due_follow_ups: [], evidence_needing_review: [],
  }
}

describe('workspace dashboard', () => {
  it('explains empty states and the UTC follow-up scope', () => {
    const html = renderToStaticMarkup(<DashboardView data={empty()} onOpen={() => {}} />)
    expect(html).toContain('No follow-ups due.')
    expect(html).toContain('2026-10-28 (UTC)')
    expect(html).toContain('No messages are sent automatically.')
    expect(html).toContain('Paste your first job description')
    expect(html).toContain('Counts include all active records')
  })

  it('distinguishes latest drafts from approved versions and escapes record text', () => {
    const data = empty()
    data.recent_resumes = [{ id: 'r', name: 'Targeted resume', latest_version: 3, latest_approved_version: 1 }]
    data.evidence_needing_review = [{ id: 'e', claim: '<script>claim</script>', reason: 'Missing source note' }]
    const html = renderToStaticMarkup(<DashboardView data={data} onOpen={() => {}} />)
    expect(html).toContain('Latest: v3')
    expect(html).toContain('Approved: v1')
    expect(html).toContain('Missing source note')
    expect(html).toContain('&lt;script&gt;')
    expect(html).not.toContain('<script>')
  })
})
