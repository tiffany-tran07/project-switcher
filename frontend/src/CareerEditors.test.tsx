import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Experience, Project, Skill } from './api'
import { ExperienceEditor, ProjectEditor, SkillEditor } from './CareerEditors'

const experience: Experience = { id: 'exp', organization: 'Fixture company', title: 'Fixture role', start_date: '2020-01-01', end_date: null, location: 'Remote', description: 'Reviewed context', archived_at: null }
const project: Project = { id: 'project', experience_id: null, name: 'Fixture project', summary: 'Reviewed summary', start_date: null, end_date: null, url: '', archived_at: null }
const skill: Skill = { id: 'skill', name: 'Fixture skill', canonical_name: 'fixture skill', category: 'Tools', aliases: ['Reviewed alias'], archived_at: null }
const handlers = { onSelect: () => {}, onSave: async () => 'saved-id', onArchive: async () => false }
const cases = [
  { name: 'experience', id: experience.id, value: experience.organization, render: (busy: boolean, selectedId: string | null) => <ExperienceEditor {...handlers} rows={[experience]} selectedId={selectedId} busy={busy} /> },
  { name: 'project', id: project.id, value: project.name, render: (busy: boolean, selectedId: string | null) => <ProjectEditor {...handlers} rows={[project]} experiences={[experience]} selectedId={selectedId} busy={busy} /> },
  { name: 'skill', id: skill.id, value: skill.name, render: (busy: boolean, selectedId: string | null) => <SkillEditor {...handlers} rows={[skill]} selectedId={selectedId} busy={busy} /> },
]

describe('career record editors', () => {
  it.each(cases)('locks $name fields and record selection during writes', (entry) => {
    const html = renderToStaticMarkup(entry.render(true, entry.id))
    expect(html).toContain('<fieldset class="evidence-fields" disabled=""')
    expect(html).toContain('<button disabled="">+ New</button>')
    expect(html).toContain('class="selected"')
    expect(html).toContain(`Edit ${entry.name}`)
    expect(html).toContain(`value="${entry.value}"`)
  })
  it.each(cases)('keeps explicit new $name forms separate from saved records', (entry) => {
    const html = renderToStaticMarkup(entry.render(false, null))
    expect(html).toContain(`New ${entry.name}`)
    expect(html).not.toContain('>Archive</button>')
    expect(html).not.toContain(`value="${entry.value}"`)
  })
})
