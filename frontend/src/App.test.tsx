import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import App from './App'

describe('workspace shell', () => {
  it('uses the 60–30–10 theme by default without prototype controls', () => {
    const html = renderToStaticMarkup(<App />)
    expect(html).toContain('app-shell color-study')
    expect(html).toContain('Local-first workspace')
    expect(html).not.toContain('Original design')
    expect(html).not.toContain('prototype-switch')
    expect(html).not.toContain('palette-study')
  })

  it('opens with the dashboard and core navigation', () => {
    const html = renderToStaticMarkup(<App />)
    expect(html).toContain('Your resume workspace.')
    expect(html).toContain('Loading workspace overview')
    expect(html).toContain('Applications')
    expect(html).toContain('Achievements')
    expect(html).toContain('Settings')
    expect(html).toContain('aria-current="page"')
    expect(html).toContain('href="#workspace-content"')
    expect(html).toContain('id="workspace-content"')
    expect(html).toContain('Private by design')
  })
})
