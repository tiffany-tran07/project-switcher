import { describe, expect, it } from 'vitest'
import type { Evidence } from './api'
import { evidenceForm, hasEvidenceEdits } from './evidenceEditing'

const row: Evidence = {
  id: 'e1', claim: 'Built Python services', source_note: 'Review log',
  experience_id: 'exp1', project_id: null, state: 'draft', verified_at: null, archived_at: null,
  skill_ids: ['b', 'a'], metrics: [], bullet_variants: [],
}

describe('unsaved evidence detection', () => {
  it('starts clean and copies skill IDs rather than mutating saved evidence', () => {
    const form = evidenceForm(row)
    expect(hasEvidenceEdits(form, row)).toBe(false)
    form.skill_ids.push('c')
    expect(row.skill_ids).toEqual(['b', 'a'])
    expect(hasEvidenceEdits(form, row)).toBe(true)
    expect(hasEvidenceEdits({ ...evidenceForm(row), skill_ids: ['a', 'b'] }, row)).toBe(false)
  })

  it('detects claim, source, and context changes independently', () => {
    const saved = evidenceForm(row)
    expect(hasEvidenceEdits({ ...saved, claim: 'Built Kubernetes services' }, row)).toBe(true)
    expect(hasEvidenceEdits({ ...saved, source_note: 'New note' }, row)).toBe(true)
    expect(hasEvidenceEdits({ ...saved, experience_id: 'exp2' }, row)).toBe(true)
    expect(hasEvidenceEdits({ ...saved, project_id: 'project' }, row)).toBe(true)
    expect(hasEvidenceEdits({ ...saved, skill_ids: [] }, row)).toBe(true)
  })

  it('tracks new unsaved records without treating empty form initialization as an edit', () => {
    expect(hasEvidenceEdits(evidenceForm())).toBe(false)
    expect(hasEvidenceEdits({ ...evidenceForm(), claim: 'New claim' })).toBe(true)
  })
})
