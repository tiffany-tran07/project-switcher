import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Evidence, Experience, Project, Skill } from './api'
import { archiveItems, evidenceRestoreBlock, loadArchive, projectRestoreBlock, type ArchiveData } from './archiveRecords'
import { ArchiveRecords } from './ArchiveWorkspace'

const archived = '2026-10-28T12:00:00Z'
function fixtures(): ArchiveData {
  const experience: Experience = { id: 'exp', organization: 'Example', title: 'Engineer', start_date: null, end_date: null, location: '', description: '', archived_at: archived }
  const project: Project = { id: 'project', experience_id: 'exp', name: 'Pipeline', summary: '', start_date: null, end_date: null, url: '', archived_at: archived }
  const skill: Skill = { id: 'skill', name: 'PostgreSQL', canonical_name: 'postgresql', category: 'Database', aliases: ['Postgres'], archived_at: archived }
  const evidence: Evidence = { id: 'evidence', claim: 'Built Python services', source_note: 'Notes', experience_id: null, project_id: 'project', state: 'draft', archived_at: archived, verified_at: null, skill_ids: [], metrics: [], bullet_variants: [] }
  return { experiences: [experience], projects: [project], skills: [skill], evidence: [evidence] }
}
afterEach(() => vi.unstubAllGlobals())

describe('archive recovery', () => {
  it('requires parent experiences and projects before evidence recovery', () => {
    const data = fixtures()
    expect(projectRestoreBlock(data.projects[0], data)).toContain('experience first')
    expect(evidenceRestoreBlock(data.evidence[0], data)).toContain('project first')
    data.projects[0].archived_at = null
    expect(evidenceRestoreBlock(data.evidence[0], data)).toContain("project's linked experience")
    data.experiences[0].archived_at = null
    expect(projectRestoreBlock(data.projects[0], data)).toBeNull()
    expect(evidenceRestoreBlock(data.evidence[0], data)).toBeNull()
  })

  it('permits independent projects but blocks missing or conflicting source links', () => {
    const data = fixtures()
    data.projects[0].experience_id = null; data.projects[0].archived_at = null
    expect(evidenceRestoreBlock(data.evidence[0], data)).toBeNull()
    expect(evidenceRestoreBlock({ ...data.evidence[0], project_id: 'missing' }, data)).toContain('project first')
    expect(evidenceRestoreBlock({ ...data.evidence[0], project_id: null }, data)).toContain('needs a linked')
    data.experiences[0].archived_at = null
    data.experiences.push({ ...data.experiences[0], id: 'other' })
    data.projects[0].experience_id = 'other'
    expect(evidenceRestoreBlock({ ...data.evidence[0], experience_id: 'exp' }, data)).toContain('sources disagree')
  })

  it('lists archived records without mutating evidence or alias state', () => {
    const data = fixtures()
    const before = JSON.stringify(data)
    const rows = archiveItems(data)
    expect(rows).toHaveLength(4)
    expect(rows.find((row) => row.kind === 'skills')?.detail).toContain('Postgres')
    expect(rows.find((row) => row.kind === 'evidence')?.detail).toContain('State: draft')
    expect(JSON.stringify(data)).toBe(before)
    data.skills[0].archived_at = null
    expect(archiveItems(data)).toHaveLength(3)
  })

  it('renders blocked recovery and search results safely', () => {
    const rows = archiveItems(fixtures())
    rows.find((row) => row.kind === 'evidence')!.label = '<script>claim</script>'
    const html = renderToStaticMarkup(<ArchiveRecords items={rows} query="claim" busy={false} onRestore={() => {}} />)
    expect(html).toContain('&lt;script&gt;')
    expect(html).not.toContain('<script>')
    expect(html).toContain('Restore the linked project first.')
    expect(html).toContain('disabled=""')
    expect(html).toContain('No archived records match this search.')
  })

  it('loads archived and active contexts through read-only requests', async () => {
    const data = fixtures()
    const fetch = vi.fn().mockImplementation(async (url: string) => {
      const key = Object.keys(data).find((name) => url.includes(`/${name}?`)) as keyof ArchiveData
      return new Response(JSON.stringify(data[key]))
    })
    vi.stubGlobal('fetch', fetch)
    expect(await loadArchive()).toEqual(data)
    expect(fetch).toHaveBeenCalledTimes(4)
    for (const [url, options] of fetch.mock.calls) {
      expect(url).toContain('include_archived=true')
      expect(options.method).toBeUndefined()
    }
  })
})
