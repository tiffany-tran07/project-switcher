import { describe, expect, it } from 'vitest'
import { intakeDraftPayload, selectedClaim } from './intakeDraft'

describe('reviewed intake excerpts', () => {
  it('selects literal Unicode text using textarea offsets', () => {
    const claim = 'Built résumé tools at €20 cost'
    const text = `👋 Contact details\n${claim}\nOther work`
    const start = text.indexOf(claim)
    expect(selectedClaim(text, start, start + claim.length)).toBe(claim)
  })

  it('rejects empty or oversized selections without guessing a claim', () => {
    expect(() => selectedClaim('   ', 0, 3)).toThrow('whitespace')
    expect(() => selectedClaim('text', 0, 0)).toThrow('Highlight')
    expect(() => selectedClaim('text', -1, 2)).toThrow('Highlight')
    expect(() => selectedClaim('text', 0, 10)).toThrow('Highlight')
    expect(() => selectedClaim('a'.repeat(2001), 0, 2001)).toThrow('2,000')
  })

  it('requires context and sends only literal excerpts without verification fields', () => {
    const payload = intakeDraftPayload('Built Python services', 'Built Python services', 'experience:exp-1', '', 'Review notes')
    expect(payload).toEqual({
      source_text: 'Built Python services', source_name: 'Pasted resume', claim: 'Built Python services',
      experience_id: 'exp-1', project_id: null, source_note: 'Review notes',
    })
    expect(payload).not.toHaveProperty('state')
    expect(payload).not.toHaveProperty('verified_at')
    expect(intakeDraftPayload('Built tooling', 'Built tooling', 'project:p1', 'resume.docx', '').project_id).toBe('p1')
    expect(() => intakeDraftPayload('Used Python', 'Used AWS', 'project:p1', '', '')).toThrow('exact excerpt')
    expect(() => intakeDraftPayload('Used Python', 'Used Python', '', '', '')).toThrow('experience or project')
  })
})
