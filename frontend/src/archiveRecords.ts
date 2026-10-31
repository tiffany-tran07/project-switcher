import { api, type Evidence, type Experience, type Project, type Skill } from './api'

export type ArchiveData = { experiences: Experience[]; projects: Project[]; skills: Skill[]; evidence: Evidence[] }
export type ArchiveKind = keyof ArchiveData
export type ArchiveItem = { kind: ArchiveKind; id: string; label: string; detail: string; archived_at: string; blocked_reason: string | null }

export async function loadArchive(): Promise<ArchiveData> {
  const [experiences, projects, skills, evidence] = await Promise.all([
    api<Experience[]>('/experiences?include_archived=true'), api<Project[]>('/projects?include_archived=true'),
    api<Skill[]>('/skills?include_archived=true'), api<Evidence[]>('/evidence?include_archived=true'),
  ])
  return { experiences, projects, skills, evidence }
}

function experienceLabel(id: string | null, data: ArchiveData): string {
  const row = data.experiences.find((item) => item.id === id)
  return row ? `${row.title} · ${row.organization}` : 'Missing experience'
}

function activeExperience(id: string, data: ArchiveData): boolean {
  return data.experiences.some((row) => row.id === id && !row.archived_at)
}

export function projectRestoreBlock(row: Project, data: ArchiveData): string | null {
  return row.experience_id && !activeExperience(row.experience_id, data)
    ? 'Restore the linked experience first.' : null
}

export function evidenceRestoreBlock(row: Evidence, data: ArchiveData): string | null {
  if (!row.experience_id && !row.project_id) return 'Evidence needs a linked experience or project.'
  if (row.experience_id && !activeExperience(row.experience_id, data)) return 'Restore the linked experience first.'
  if (row.project_id) {
    const project = data.projects.find((item) => item.id === row.project_id)
    if (!project || project.archived_at) return 'Restore the linked project first.'
    if (projectRestoreBlock(project, data)) return "Restore the project's linked experience first."
    if (row.experience_id && project.experience_id && row.experience_id !== project.experience_id) {
      return 'Linked sources disagree; repair the context before restoring.'
    }
  }
  return null
}

export function archiveItems(data: ArchiveData): ArchiveItem[] {
  const items: ArchiveItem[] = []
  for (const row of data.experiences) {
    if (row.archived_at) items.push({ kind: 'experiences', id: row.id,
      label: `${row.title} · ${row.organization}`, archived_at: row.archived_at, blocked_reason: null,
      detail: [row.start_date, row.end_date].filter(Boolean).join(' – ') || 'Dates not recorded',
    })
  }
  for (const row of data.projects) {
    if (row.archived_at) items.push({ kind: 'projects', id: row.id, label: row.name, archived_at: row.archived_at,
      detail: row.experience_id ? experienceLabel(row.experience_id, data) : 'Independent project',
      blocked_reason: projectRestoreBlock(row, data),
    })
  }
  for (const row of data.skills) {
    if (row.archived_at) items.push({ kind: 'skills', id: row.id, label: row.name, archived_at: row.archived_at,
      detail: [row.category, ...row.aliases].filter(Boolean).join(' · '), blocked_reason: null,
    })
  }
  for (const row of data.evidence) {
    if (row.archived_at) items.push({ kind: 'evidence', id: row.id, label: row.claim, archived_at: row.archived_at,
      detail: `State: ${row.state} · ${row.project_id ? data.projects.find((item) => item.id === row.project_id)?.name ?? 'Missing project' : experienceLabel(row.experience_id, data)}`,
      blocked_reason: evidenceRestoreBlock(row, data),
    })
  }
  return items.sort((a, b) => b.archived_at.localeCompare(a.archived_at) || a.label.localeCompare(b.label))
}
