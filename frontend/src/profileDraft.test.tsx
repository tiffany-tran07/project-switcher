import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Profile } from './api'
import ProfileEditor from './ProfileEditor'
import { profileDraft, profilePayload } from './profileDraft'

const profile: Profile = { name: 'Fixture', email: 'fixture@example.test', phone: '', location: 'Remote', links: ['https://portfolio.example.test'] }

describe('profile link drafts', () => {
  it('keeps raw blank lines until payload construction without mutating the draft', () => {
    const draft = { ...profileDraft(profile), linksText: 'https://one.example.test\n\nhttps://two.example.test\n' }
    const raw = draft.linksText
    expect(profilePayload(draft).links).toEqual(['https://one.example.test', 'https://two.example.test'])
    expect(draft.linksText).toBe(raw)
    expect(profile.links).toEqual(['https://portfolio.example.test'])
  })
  it('normalizes line endings and surrounding whitespace only on save', () => {
    const payload = profilePayload({ ...profileDraft(profile), linksText: '  https://one.example.test\r\n\t\rhttps://two.example.test \n' })
    expect(payload.links).toEqual(['https://one.example.test', 'https://two.example.test'])
    expect(payload.name).toBe(profile.name)
    expect(payload).not.toHaveProperty('linksText')
  })
  it('preserves link order, encoding, capitalization, and duplicates', () => {
    const link = 'https://portfolio.example.test/C%2B%2B?tag=A+B#Overview'
    expect(profilePayload({ ...profileDraft(profile), linksText: `${link}\nhttps://two.example.test\n${link}` }).links).toEqual([link, 'https://two.example.test', link])
    expect(profilePayload({ ...profileDraft(profile), linksText: ' \n\t\r\n' }).links).toEqual([])
  })
  it('locks profile fields during writes and escapes display text', () => {
    const html = renderToStaticMarkup(<ProfileEditor profile={{ ...profile, links: ['<script>not executed</script>'] }} busy onSave={() => {}} />)
    expect(html).toContain('<fieldset class="evidence-fields" disabled=""')
    expect(html).toContain('&lt;script&gt;not executed&lt;/script&gt;')
    expect(html).not.toContain('<script>')
  })
  it('renders saved links as separate editable lines with clear save semantics', () => {
    const html = renderToStaticMarkup(<ProfileEditor profile={{ ...profile, links: ['first', 'second'] }} busy={false} onSave={() => {}} />)
    expect(html).toContain('first\nsecond')
    expect(html).toContain('removed only when saving')
    expect(html).toContain('do not change existing resume snapshots')
  })
})
