import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_ROOT, loadEvidenceSource, type Evidence } from './api'
import EvidenceEditor from './EvidenceEditor'
import { EvidenceSourceCard, type SourceLookup } from './EvidenceSourceLookup'

const source: Evidence = { id: 'source', claim: '<script>Current claim</script>', source_note: 'Current note', experience_id: 'exp', project_id: null, state: 'draft', verified_at: null, archived_at: '2026-10-29T12:00:00', skill_ids: [], metrics: [], bullet_variants: [] }
function card(lookup: SourceLookup, busy = false) {
  return renderToStaticMarkup(<EvidenceSourceCard lookup={lookup} busy={busy} onRefresh={() => {}} onOpenArchive={() => {}} onRetry={() => {}} />)
}
afterEach(() => vi.unstubAllGlobals())

describe('historical evidence source links', () => {
  it('does not turn an unresolved source ID into a new-record form', () => {
    const html = renderToStaticMarkup(<EvidenceEditor rows={[]} experiences={[]} projects={[]} skills={[]} selectedId="missing" busy={false} onSelect={() => {}} onRefresh={() => {}} onOpenArchive={() => {}} run={async () => false} />)
    expect(html).toContain('Loading the current source record')
    expect(html).not.toContain('New achievement')
    expect(html).not.toContain('Save achievement')
    expect(html).not.toContain('<form')
  })
  it('retains an explicit new-record form when the user chooses New', () => {
    const html = renderToStaticMarkup(<EvidenceEditor rows={[]} experiences={[]} projects={[]} skills={[]} selectedId={null} busy={false} onSelect={() => {}} onRefresh={() => {}} onOpenArchive={() => {}} run={async () => false} />)
    expect(html).toContain('New achievement')
    expect(html).toContain('Save achievement')
  })
  it('shows archived sources read-only and distinguishes current records from snapshots', () => {
    const html = card({ status: 'found', source })
    expect(html).toContain('Archived achievement source')
    expect(html).toContain('not the historical snapshot')
    expect(html).toContain('Current library state: draft')
    expect(html).toContain('Current note')
    expect(html).toContain('&lt;script&gt;Current claim&lt;/script&gt;')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<form')
    expect(html).not.toContain('>Verify<')
    expect(html).toContain('Open Archive')
  })
  it('explains active but uncached sources without silently enabling editing', () => {
    const html = card({ status: 'found', source: { ...source, archived_at: null } })
    expect(html).toContain('Refresh the career library before editing')
    expect(html).not.toContain('Archived achievement source')
    expect(html).not.toContain('<textarea')
  })
  it('keeps errors retryable without claiming that a missing source was archived', () => {
    const html = card({ status: 'failed', message: 'Not found' })
    expect(html).toContain('role="alert"')
    expect(html).toContain('may be missing')
    expect(html).toContain('Retry source lookup')
    expect(html).not.toContain('Archived achievement source')
    expect(card({ status: 'loading' }, true)).toContain('disabled=""')
  })
  it('loads only the requested source through an encoded read-only URL', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(source)))
    vi.stubGlobal('fetch', fetch)
    expect(await loadEvidenceSource('source/id?')).toEqual(source)
    expect(fetch).toHaveBeenCalledExactlyOnceWith(`${API_ROOT}/evidence/source%2Fid%3F`, { headers: { 'Content-Type': 'application/json' } })
  })
})
