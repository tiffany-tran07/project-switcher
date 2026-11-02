import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_ROOT, uploadSource, type SourceAttachmentRef } from './api'
import EvidenceAttachments, { AttachmentLinks } from './EvidenceAttachments'

afterEach(() => vi.unstubAllGlobals())
describe('supporting source files', () => {
  it('uploads explicitly selected files without transforming their bytes', async () => {
    const file = new File(['Private benchmark log'], 'review notes.txt')
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'saved' })))
    vi.stubGlobal('fetch', fetch)
    expect(await uploadSource('evidence/id', file)).toEqual({ id: 'saved' })
    expect(fetch).toHaveBeenCalledWith(`${API_ROOT}/evidence/evidence%2Fid/attachments?filename=review%20notes.txt`, {
      method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
    })
  })
  it('rejects unsupported, empty, and oversized files before networking', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await expect(uploadSource('id', new File(['PDF'], 'source.pdf'))).rejects.toThrow('UTF-8 .txt')
    await expect(uploadSource('id', new File([], 'empty.txt'))).rejects.toThrow('empty')
    await expect(uploadSource('id', new File([new Uint8Array(1024 * 1024 + 1)], 'large.txt'))).rejects.toThrow('1 MB')
    expect(fetch).not.toHaveBeenCalled()
  })
  it('reports failed saves rather than claiming that a source was attached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Storage failed' }), { status: 409 })))
    await expect(uploadSource('id', new File(['Notes'], 'notes.txt'))).rejects.toThrow('Storage failed')
  })
  it('escapes filenames and pins download links to the API', () => {
    const source: SourceAttachmentRef = { id: 'id/with?path', original_name: '<script>source.txt</script>', checksum: 'abc', size: 12, media_type: 'text/plain' }
    const html = renderToStaticMarkup(<AttachmentLinks sources={[source]} />)
    expect(html).toContain('&lt;script&gt;source.txt&lt;/script&gt;')
    expect(html).toContain(`${API_ROOT}/attachments/id%2Fwith%3Fpath/download`)
    expect(html).toContain('SHA-256 abc')
    expect(html).not.toContain('<script>')
  })
  it('makes privacy, verification invalidation, and retention limits explicit', () => {
    const html = renderToStaticMarkup(<EvidenceAttachments evidenceId="id" blocked onPendingChange={() => {}} run={async () => false} />)
    expect(html).toContain('not interpreted or sent to AI')
    expect(html).toContain('returns the evidence to draft')
    expect(html).toContain('replacement and deletion are not available')
    expect(html).toContain('disabled=""')
  })
})
