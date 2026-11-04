import { describe, expect, it } from 'vitest'
import { editedFilePreview, hasPendingIntakeReview, samePreview, type IntakeReview } from './intakeReview'
import { intakeDraftPayload } from './intakeDraft'

const empty: IntakeReview = { text: '', originalText: '', source: '', claim: '', sourceNote: '', context: '', creatingContext: false }
const loaded: IntakeReview = { ...empty, text: 'Built tools', originalText: 'Built tools', source: 'resume.pdf' }

describe('intake review preservation and provenance', () => {
  it('does not treat a clean file extraction as an unsaved manual edit', () => {
    expect(editedFilePreview(loaded)).toBe(false)
    expect(hasPendingIntakeReview(loaded)).toBe(false)
    expect(hasPendingIntakeReview(empty)).toBe(false)
  })
  it('protects excerpts, notes, context choices, unfinished forms, and pasted text', () => {
    for (const changes of [{ claim: 'Built tools' }, { sourceNote: 'Review notes' }, { context: 'project:p' }, { creatingContext: true }]) {
      expect(hasPendingIntakeReview({ ...loaded, ...changes })).toBe(true)
    }
    expect(hasPendingIntakeReview({ ...empty, text: 'Pasted resume' })).toBe(true)
  })
  it('labels edited file previews without claiming pasted text is a file extraction', () => {
    expect(editedFilePreview({ ...loaded, text: 'Edited tools' })).toBe(true)
    expect(hasPendingIntakeReview({ ...loaded, text: 'Edited tools' })).toBe(true)
    expect(editedFilePreview({ ...empty, text: 'Pasted tools' })).toBe(false)
  })
  it('recognizes identical re-previews even with an unfinished review', () => {
    const pending = { ...loaded, claim: 'Built tools', sourceNote: 'Keep these notes' }
    expect(samePreview(pending, loaded.text, loaded.source)).toBe(true)
    expect(samePreview(pending, loaded.text, 'another.pdf')).toBe(false)
    expect(samePreview(pending, 'Different text', loaded.source)).toBe(false)
  })
  it('reports editing as provenance only, without verification fields or note rewriting', () => {
    const payload = intakeDraftPayload('Edited tools', 'Edited tools', 'project:p', 'resume.pdf', 'Keep notes', true)
    expect(payload.source_edited).toBe(true)
    expect(payload.source_note).toBe('Keep notes')
    expect(payload.source_text).toBe('Edited tools')
    expect(payload).not.toHaveProperty('state')
    expect(payload).not.toHaveProperty('verified_at')
    expect(intakeDraftPayload('Built tools', 'Built tools', 'project:p', 'resume.pdf', '')).not.toHaveProperty('source_edited')
  })
})
