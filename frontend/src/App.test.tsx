import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import App from './App'

describe('career library shell', () => {
  it('opens with source-backed evidence entry', () => {
    const html = renderToStaticMarkup(<App />)
    expect(html).toContain('Source note')
    expect(html).toContain('Save evidence')
    expect(html).toContain('Export JSON')
  })
})
