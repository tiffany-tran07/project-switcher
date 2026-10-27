import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import DraftValidationReport from './DraftValidationReport'

describe('draft validation report', () => {
  it('shows source validation separately from ATS readiness', () => {
    const html = renderToStaticMarkup(<DraftValidationReport report={{ valid: true, issues: [] }} />)
    expect(html).toContain('Source checks passed.')
    expect(html).toContain('not an ATS report')
    expect(html).toContain('Saving rechecks current evidence')
  })

  it('labels each issue by its one-based bullet number', () => {
    const html = renderToStaticMarkup(<DraftValidationReport report={{ valid: false, issues: [
      { evidence_id: 'a', position: 0, code: 'unsafe_wording', message: 'Preserve metrics.' },
      { evidence_id: 'b', position: 2, code: 'unavailable_evidence', message: 'Source is no longer verified.' },
    ] }} />)
    expect(html).toContain('Fix these issues before saving:')
    expect(html).toContain('Bullet 1: Preserve metrics.')
    expect(html).toContain('Bullet 3: Source is no longer verified.')
    expect(html).not.toContain('Source checks passed.')
  })
})
