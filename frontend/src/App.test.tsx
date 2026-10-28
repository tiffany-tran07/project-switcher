import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import App from './App'

describe('workspace shell', () => {
  it('opens with the dashboard and core navigation', () => {
    const html = renderToStaticMarkup(<App />)
    expect(html).toContain('Your resume workspace.')
    expect(html).toContain('Loading workspace overview')
    expect(html).toContain('Applications')
    expect(html).toContain('Evidence')
    expect(html).toContain('Settings')
  })
})
