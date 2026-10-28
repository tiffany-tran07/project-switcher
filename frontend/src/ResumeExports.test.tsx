import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ResumeExports from './ResumeExports'

describe('version export controls', () => {
  it('prevents draft exports and explains approval', () => {
    const html = renderToStaticMarkup(<ResumeExports versionId="draft" approved={false} />)
    expect(html).toContain('disabled=""')
    expect(html).toContain('Draft versions cannot be exported')
  })

  it('enables exports for approved snapshots and explains the local converter', () => {
    const html = renderToStaticMarkup(<ResumeExports versionId="approved" approved />)
    expect(html).toContain('Generate DOCX')
    expect(html).not.toContain('disabled=""')
    expect(html).toContain('Generate PDF')
    expect(html).toContain('PDF conversion requires local LibreOffice')
  })
})
