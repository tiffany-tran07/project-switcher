import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ResumeIntake from './ResumeIntake'
import { previewResume } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('resume intake preview', () => {
  it('explains preview-only behavior, supported formats, and manual verification', () => {
    const html = renderToStaticMarkup(<ResumeIntake />)
    expect(html).toContain('Preview an existing resume')
    expect(html).toContain('accept=".pdf,.docx,.txt"')
    expect(html).toContain('No AI is called')
    expect(html).toContain('files are not saved')
    expect(html).toContain('no career records are created or verified')
    expect(html).toContain('scanned/image-only PDFs require local OCR first')
    expect(html).toContain('Resume drop zone')
    expect(html).toContain('up to 20 pages')
    expect(html).toContain('An existing resume is a starting point, not independent proof')
    expect(html).toContain('Save as draft achievement')
    expect(html).toContain('Highlight an accomplishment')
    expect(html).toContain('Create an experience or project below without leaving your resume preview')
    expect(html).toContain('Create experience or project here')
    expect(html).toContain('disabled=""')
  })

  it('sends a bounded file to the preview endpoint without creating evidence', async () => {
    const result = { filename: 'My resume.txt', format: 'txt', text: 'Built Python services', warnings: [] }
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(result)))
    vi.stubGlobal('fetch', fetch)
    const file = new File(['Built Python services'], 'My resume.txt')
    const controller = new AbortController()
    expect(await previewResume(file, controller.signal)).toEqual(result)
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, options] = fetch.mock.calls[0]
    expect(url).toContain('/resume-intake/preview?filename=My%20resume.txt')
    expect(options.method).toBe('POST')
    expect(options.body).toBe(file)
    expect(options.headers['Content-Type']).toBe('application/octet-stream')
    expect(options.signal).toBe(controller.signal)
  })

  it('rejects unsupported or oversized files before any request', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await expect(previewResume(new File(['macro'], 'resume.docm'))).rejects.toThrow('Choose a PDF')
    await expect(previewResume(new File([], 'resume.txt'))).rejects.toThrow('empty')
    await expect(previewResume(new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'resume.docx'))).rejects.toThrow('5 MB')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('sends PDF bytes unchanged to the same local preview endpoint', async () => {
    const result = { filename: 'resume.PDF', format: 'pdf', text: 'Built tools', warnings: ['Review reading order'] }
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(result)))
    vi.stubGlobal('fetch', fetch)
    const file = new File(['%PDF-fixture'], 'resume.PDF', { type: 'application/pdf' })
    expect(await previewResume(file)).toEqual(result)
    expect(fetch.mock.calls[0][1].body).toBe(file)
    expect(fetch.mock.calls[0][1].headers['Content-Type']).toBe('application/octet-stream')
  })

  it('surfaces parse failures rather than treating them as resume text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Macros and embedded objects are not supported' }), { status: 422 },
    )))
    await expect(previewResume(new File(['bad'], 'resume.docx'))).rejects.toThrow('Macros')
  })
})
