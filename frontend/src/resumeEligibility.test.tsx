import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Evidence, ResumeEvidenceStatus } from './api'
import ResumeEvidencePicker from './ResumeEvidencePicker'
import ResumeWorkspace from './ResumeWorkspace'
import { emptyWorkingDraft } from './resumeDraft'
import { eligibleEvidence } from './resumeEligibility'

const evidence: Evidence[] = [
  { id: 'good', claim: 'Built tools', source_note: 'Notes', experience_id: 'exp', project_id: null, state: 'verified', archived_at: null, verified_at: '2026-10-29', skill_ids: [], metrics: [], bullet_variants: [] },
  { id: 'blocked', claim: '<script>Archived role claim</script>', source_note: 'Notes', experience_id: 'old-exp', project_id: null, state: 'verified', archived_at: null, verified_at: '2026-10-29', skill_ids: [], metrics: [], bullet_variants: [] },
]
const statuses: ResumeEvidenceStatus[] = [
  { evidence_id: 'good', eligible: true, problem: null },
  { evidence_id: 'blocked', eligible: false, problem: 'Linked source unavailable' },
]
const handlers = { onRefresh: () => {}, onSelect: () => {}, onReview: () => {} }

describe('API-owned resume source eligibility', () => {
  it('does not infer eligibility from the cached verified flag', () => {
    expect(eligibleEvidence(evidence, statuses).map((row) => row.id)).toEqual(['good'])
    expect(eligibleEvidence(evidence, null)).toEqual([])
    expect(eligibleEvidence(evidence, [])).toEqual([])
    expect(eligibleEvidence([{ ...evidence[0], state: 'draft' }], statuses)).toHaveLength(1)
  })
  it('renders ready choices and safely explains blocked sources', () => {
    const html = renderToStaticMarkup(<ResumeEvidencePicker {...handlers} evidence={evidence} statuses={statuses} selected={['blocked']} checking={false} error="" busy={false} />)
    expect(html.match(/type="checkbox"/g)).toHaveLength(1)
    expect(html).toContain('Linked source unavailable')
    expect(html).toContain('&lt;script&gt;Archived role claim&lt;/script&gt;')
    expect(html).not.toContain('<script>')
    expect(html).toContain('not wording/section approval')
  })
  it('fails closed on loading or errors without falling back to cached flags', () => {
    for (const checking of [true, false]) {
      const html = renderToStaticMarkup(<ResumeEvidencePicker {...handlers} evidence={evidence} statuses={statuses} selected={['good']} checking={checking} error={checking ? '' : 'Server unavailable'} busy={false} />)
      expect(html).not.toContain('type="checkbox"')
      expect(html).toContain(checking ? 'Checking current source availability' : 'Your working edits are kept')
    }
  })
  it('offers review for selected sources absent from the active cache', () => {
    const html = renderToStaticMarkup(<ResumeEvidencePicker {...handlers} evidence={[]} statuses={[]} selected={['missing']} checking={false} error="" busy={false} />)
    expect(html).toContain('Review selected source')
  })
  it('keeps working wording while availability is pending', () => {
    const draft = { ...emptyWorkingDraft(), selected: ['blocked'], wording: { blocked: 'Kept working wording' } }
    const html = renderToStaticMarkup(<ResumeWorkspace evidence={evidence} projects={[]} initialResumeId="resume" workingDrafts={{ resume: draft }} onWorkingDraftChange={() => {}} onResumeSelect={() => {}} onEvidenceSelect={() => {}} />)
    expect(html).toContain('Kept working wording')
    expect(html).toContain('Some selected evidence is unavailable or not yet checked')
    expect(html).toContain('disabled="">Approve snapshot')
  })
})
