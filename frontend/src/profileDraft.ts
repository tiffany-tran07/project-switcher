import type { Profile } from './api'

export type ProfileDraft = Omit<Profile, 'links'> & { linksText: string }

export function profileDraft(profile: Profile): ProfileDraft {
  const { name, email, phone, location, links } = profile
  return { name, email, phone, location, linksText: links.join('\n') }
}

export function profilePayload(draft: ProfileDraft): Profile {
  const { linksText, ...contact } = draft
  return { ...contact, links: linksText.split(/\r\n|\r|\n/).map((line) => line.trim()).filter(Boolean) }
}
