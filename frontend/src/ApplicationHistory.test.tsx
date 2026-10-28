import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ApplicationHistory from './ApplicationHistory'
import ApplicationsWorkspace from './ApplicationsWorkspace'

describe('application tracking', () => {
  it('requires an approved snapshot and explains that tracking does not submit', () => {
    const html = renderToStaticMarkup(<ApplicationsWorkspace onEvidenceSelect={() => {}} />)
    expect(html).toContain('exact approved resume version')
    expect(html).toContain('does not submit an application')
    expect(html).toContain('Create an approved resume snapshot first.')
    expect(html).toContain('disabled=""')
  })

  it('shows append-only history entries with status transitions and escaped notes', () => {
    const html = renderToStaticMarkup(<ApplicationHistory events={[
      { id: '1', event_type: 'created', previous_status: null, status: 'planned', note: 'Local record', created_at: '2026-01-01T10:00:00Z' },
      { id: '2', event_type: 'status_changed', previous_status: 'planned', status: 'applied', note: '<script>bad</script>', created_at: '2026-01-02T10:00:00Z' },
    ]} />)
    expect(html).toContain('planned → applied')
    expect(html).toContain('dateTime="2026-01-02T10:00:00Z"')
    expect(html).toContain('&lt;script&gt;')
    expect(html).not.toContain('<script>')
    expect(html.indexOf('Local record')).toBeLessThan(html.indexOf('status changed'))
  })
})
