import { describe, expect, it } from 'vitest'
import { buildSections, defaultHeadingOrder, emptyWorkingDraft, moveWithinSection, updateWorkingDraft, type WorkingDrafts } from './resumeDraft'

describe('session working drafts', () => {
  it('merges sequential field updates without dropping earlier selection or wording', () => {
    let drafts: WorkingDrafts = {}
    drafts = updateWorkingDraft(drafts, 'r1', (current) => ({ ...current, selected: ['e1'] }))
    drafts = updateWorkingDraft(drafts, 'r1', (current) => ({ ...current, headings: { e1: 'Experience' } }))
    drafts = updateWorkingDraft(drafts, 'r1', (current) => ({ ...current, wording: { e1: 'Edited wording' } }))
    expect(drafts.r1.selected).toEqual(['e1'])
    expect(drafts.r1.wording.e1).toBe('Edited wording')
    expect(buildSections(drafts.r1.headingOrder, drafts.r1.selected, drafts.r1.headings, drafts.r1.wording))
      .toEqual([{ heading: 'Experience', bullets: [{ evidence_id: 'e1', text: 'Edited wording' }] }])
  })

  it('keeps resumes independent and clears only the explicitly selected working draft', () => {
    const original: WorkingDrafts = { r1: { ...emptyWorkingDraft(), selected: ['e1'], wording: { e1: 'First' } } }
    let drafts = updateWorkingDraft(original, 'r2', (current) => ({ ...current, selected: ['e2'] }))
    drafts = updateWorkingDraft(drafts, 'r2', (current) => ({ ...current, headingOrder: ['Projects', 'Selected evidence', 'Experience'] }))
    expect(drafts.r1).toBe(original.r1)
    expect(original).not.toHaveProperty('r2')
    drafts = updateWorkingDraft(drafts, 'r2', () => emptyWorkingDraft())
    expect(drafts.r1.selected).toEqual(['e1'])
    expect(drafts.r2.selected).toEqual([])
    expect(updateWorkingDraft(drafts, '', () => emptyWorkingDraft())).toBe(drafts)
  })

  it('does not share mutable default arrays across drafts', () => {
    const a = emptyWorkingDraft()
    const b = emptyWorkingDraft()
    a.selected.push('only-a')
    a.headingOrder.reverse()
    expect(b.selected).toEqual([])
    expect(b.headingOrder).toEqual(defaultHeadingOrder)
  })
})

describe('resume section ordering', () => {
  const selected = ['a', 'b', 'c']
  const headings = { a: 'Experience', b: 'Projects', c: 'Experience' } as const
  const wording = { a: 'Built services', b: 'Built project', c: 'Improved latency' }

  it('uses the same grouped order for previews and save payloads', () => {
    const result = buildSections(['Projects', 'Experience', 'Selected evidence'], selected, headings, wording)
    expect(result.map((section) => section.heading)).toEqual(['Projects', 'Experience'])
    expect(result.flatMap((section) => section.bullets.map((bullet) => bullet.evidence_id)))
      .toEqual(['b', 'a', 'c'])
    expect(result[1].bullets[1].text).toBe('Improved latency')
  })

  it('moves bullets only within their section', () => {
    const moved = moveWithinSection(selected, headings, 'c', -1)
    expect(moved).toEqual(['c', 'b', 'a'])
    expect(selected).toEqual(['a', 'b', 'c'])
    expect(buildSections(defaultHeadingOrder, moved, headings, wording)[0].bullets.map((b) => b.evidence_id))
      .toEqual(['c', 'a'])
    expect(moveWithinSection(selected, headings, 'b', -1)).toEqual(selected)
    expect(moveWithinSection(selected, headings, 'a', -1)).toEqual(selected)
    expect(moveWithinSection(selected, headings, 'c', 1)).toEqual(selected)
  })

  it('retains uncategorized selections instead of silently omitting them', () => {
    expect(buildSections(defaultHeadingOrder, ['unknown'], {}, {})).toEqual([
      { heading: 'Selected evidence', bullets: [{ evidence_id: 'unknown', text: '' }] },
    ])
    expect(buildSections(defaultHeadingOrder, [], {}, {})).toEqual([])
  })
})
