import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import LocalAISettings from './LocalAISettings'
import AnalysisNotice from './AnalysisNotice'

describe('optional local AI transparency', () => {
  it('explains privacy boundaries and does not start runtime checks on rendering', () => {
    const html = renderToStaticMarkup(<LocalAISettings />)
    expect(html).toContain('Core features work without AI')
    expect(html).toContain('Environment proxies and redirects are disabled')
    expect(html).toContain('sends no resume, evidence, or job text')
    expect(html).toContain('does not download models')
    expect(html).toContain('disabled=""')
  })

  it('makes deterministic fallback visible without claiming a model succeeded', () => {
    const html = renderToStaticMarkup(<AnalysisNotice outcome={{
      requested_method: 'ollama', method_used: 'deterministic', fallback: true,
      note: 'Local analysis unavailable; deterministic extraction was used.',
    }} />)
    expect(html).toContain('deterministic rules (fallback)')
    expect(html).toContain('deterministic extraction was used')
    expect(html).toContain('not stored in job history')
    expect(html).not.toContain('Last extraction: local Ollama')
  })

  it('clearly identifies retained requirements when the model fails', () => {
    const html = renderToStaticMarkup(<AnalysisNotice outcome={{
      requested_method: 'ollama', method_used: 'preserved', fallback: true,
      note: 'Existing requirements were kept.',
    }} />)
    expect(html).toContain('existing requirements retained (fallback)')
    expect(html).not.toContain('Last extraction: local Ollama')
  })

  it('labels successful local extraction but still requires review', () => {
    const html = renderToStaticMarkup(<AnalysisNotice outcome={{
      requested_method: 'ollama', method_used: 'ollama', fallback: false, note: 'Local extraction complete.',
    }} />)
    expect(html).toContain('Last extraction: local Ollama')
    expect(html).toContain('Review requirements before confirmation')
    expect(html).not.toContain('(fallback)')
  })
})
