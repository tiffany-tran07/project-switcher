import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { ResumeBullet, ResumeVersion } from './api'
import ResumePreview from './ResumePreview'

function bullet(id: string, text: string): ResumeBullet {
  return {
    id, evidence_id: id, text, position: 0,
    evidence_snapshot: {
      claim: text, source_note: 'Private source notes', metrics: [],
      experience: { organization: 'Saved Employer', title: 'Engineer', start_date: '2020-01-01', end_date: null, location: 'Remote' },
      project: null,
    },
  }
}

function version(): ResumeVersion {
  return {
    id: 'version', resume_id: 'resume', version_number: 1, template: 'single_column',
    approved_at: null, created_at: '2026-01-01',
    content: {
      profile: { name: 'Saved Name', email: 'saved@example.test', links: ['https://example.test'] },
      sections: [{ heading: 'Experience', evidence_ids: ['b', 'a'] }],
    },
    bullets: [bullet('a', 'Built Python services'), bullet('b', 'Improved report performance')],
  }
}

describe('saved resume preview', () => {
  it('renders saved contact details, grouped role context, and section bullet order', () => {
    const html = renderToStaticMarkup(<ResumePreview version={version()} />)
    expect(html).toContain('Saved Name')
    expect(html).toContain('saved@example.test')
    expect(html).toContain('https://example.test')
    expect(html).toContain('2020-01-01 · Remote')
    expect(html.match(/Saved Employer/g)).toHaveLength(1)
    expect(html.indexOf('Improved report performance')).toBeLessThan(html.indexOf('Built Python services'))
    expect(html).not.toContain('Present')
    expect(html).not.toContain('Private source notes')
    expect(html).not.toContain('undefined')
  })

  it('uses project dates instead of employer dates for project sections', () => {
    const saved = version()
    saved.content.sections = [{ heading: 'Projects', evidence_ids: ['a'] }]
    saved.bullets[0].evidence_snapshot.project = {
      name: 'Pipeline', start_date: '2022-03-01', end_date: '2022-06-30', url: 'https://example.test/project',
    }
    const html = renderToStaticMarkup(<ResumePreview version={saved} />)
    expect(html).toContain('Pipeline')
    expect(html).toContain('2022-03-01 – 2022-06-30')
    expect(html).not.toContain('2020-01-01')
    expect(html).toContain('https://example.test/project')
  })

  it('handles older snapshots with no profile or dates and escapes user text', () => {
    const saved = version()
    saved.content.profile = {}
    saved.bullets[0].evidence_snapshot.experience = null
    saved.bullets[1].evidence_snapshot.experience = null
    saved.bullets[0].text = '<script>alert(1)</script>'
    const html = renderToStaticMarkup(<ResumePreview version={saved} />)
    expect(html).toContain('&lt;script&gt;')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('undefined')
    expect(html).not.toContain('<header>')
  })
})
