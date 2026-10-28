import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { AtsReport } from './api'
import AtsReadiness from './AtsReadiness'

function report(): AtsReport {
  return {
    version_id: 'v', export_id: 'e', format: 'docx', page_count: null, page_target: 2, extracted_text: 'Built Python services',
    requirements: [], formatting: [{ name: 'page_target', status: 'not_checked', message: 'Not paginated.' }],
    notes: ['No PDF analysis.'],
  }
}

describe('ATS readiness report', () => {
  it('explains empty confirmation and unchecked pagination without a score', () => {
    const html = renderToStaticMarkup(<AtsReadiness report={report()} />)
    expect(html).toContain('No confirmed requirements')
    expect(html).toContain('Not an employer score prediction')
    expect(html).toContain('page target: not checked')
    expect(html).toContain('Built Python services')
    expect(html).toContain('No PDF analysis.')
  })

  it('shows measured PDF pagination separately from DOCX', () => {
    const value = report()
    value.format = 'pdf'; value.page_count = 3; value.page_target = 2
    value.formatting = [{ name: 'page_target', status: 'warning', message: 'PDF exceeds target.' }]
    const html = renderToStaticMarkup(<AtsReadiness report={value} />)
    expect(html).toContain('this PDF')
    expect(html).toContain('PDF page count: 3.')
    expect(html).toContain('Page target: 2 maximum.')
    expect(html).toContain('PDF exceeds target.')
    expect(html).not.toContain('Page count is not measured for DOCX.')
  })

  it('separates wording gaps from evidence gaps and shows sources', () => {
    const value = report()
    value.requirements = [
      { requirement_id: 'r1', text: 'Docker', status: 'supported_but_missing_from_resume', evidence_ids: ['evidence'], reason: 'Direct source exists.' },
      { requirement_id: 'r2', text: 'Kubernetes', status: 'no_verified_evidence', evidence_ids: [], reason: 'No verified source.' },
    ]
    const html = renderToStaticMarkup(<AtsReadiness report={value} />)
    expect(html).toContain('Supported, wording missing')
    expect(html).toContain('No direct verified evidence')
    expect(html).toContain('Source evidence 1')
    expect(html).not.toContain('No confirmed requirements')
  })
})
