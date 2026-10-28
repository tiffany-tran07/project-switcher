import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BackupSettings from './BackupSettings'
import { downloadBackup } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('portable backup', () => {
  it('requires acknowledgement and explains privacy and restore limitations', () => {
    const html = renderToStaticMarkup(<BackupSettings />)
    expect(html).toContain('unencrypted personal data')
    expect(html).toContain('They are not encrypted')
    expect(html).toContain('disabled=""')
    expect(html).toContain('--check-only')
    expect(html).toContain('--destination')
    expect(html).toContain('never overwritten')
    expect(html).toContain('not authorship')
    expect(html).toContain('256 MB')
  })

  it('downloads a binary archive using explicit acknowledgement', async () => {
    const blob = new Blob(['archive'], { type: 'application/zip' })
    const fetch = vi.fn().mockResolvedValue(new Response(blob))
    vi.stubGlobal('fetch', fetch)
    const result = await downloadBackup()
    expect(await result.text()).toBe('archive')
    expect(fetch.mock.calls[0][0]).toContain('/api/v1/backup/export')
    expect(fetch.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ acknowledge_personal_data: true })
  })

  it('shows server failures rather than downloading an error as a backup', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Export checksum failed; regenerate the export before backup' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } },
    )))
    await expect(downloadBackup()).rejects.toThrow('Export checksum failed')
  })
})
