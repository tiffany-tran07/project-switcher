import { describe, expect, it } from 'vitest'
import { buildSections, defaultHeadingOrder, moveWithinSection } from './resumeDraft'

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
