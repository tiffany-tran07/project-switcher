export const API_ROOT = `${import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'}/api/v1`

export type Profile = { name: string; email: string; phone: string; location: string; links: string[] }
export type Experience = {
  id: string; organization: string; title: string; start_date: string | null; end_date: string | null
  location: string; description: string; archived_at: string | null
}
export type Project = {
  id: string; experience_id: string | null; name: string; summary: string; start_date: string | null
  end_date: string | null; url: string; archived_at: string | null
}
export type Skill = {
  id: string; name: string; canonical_name: string; category: string; aliases: string[]; archived_at: string | null
}
export type Metric = {
  id: string; evidence_id: string; name: string; value: string; unit: string; context: string; source_note: string
}
export type Bullet = {
  id: string; evidence_id: string; text: string; tone: string; approved_at: string | null
}
export type Evidence = {
  id: string; claim: string; source_note: string; experience_id: string | null; project_id: string | null
  state: 'draft' | 'verified' | 'rejected'; verified_at: string | null; archived_at: string | null
  skill_ids: string[]; metrics: Metric[]; bullet_variants: Bullet[]
}
export type SearchResult = { type: 'experience' | 'project' | 'skill' | 'evidence'; id: string; title: string }
export type Requirement = { id?: string; text: string; supporting_span?: string | null; normalized_term: string; kind: 'skill' | 'tool' | 'responsibility' | 'experience' | 'education' | 'certification'; priority: 'required' | 'preferred' | 'unclear'; confirmed: boolean }
export type Job = { id: string; company: string; title: string; url: string; raw_description: string; source: string; created_at: string; requirements: Requirement[] }
export type DraftValidation = { valid: boolean; issues: { evidence_id: string; position: number; code: 'duplicate' | 'unavailable_evidence' | 'section_context' | 'unsafe_wording'; message: string }[] }
export type Resume = { id: string; job_id: string; name: string; status: string; created_at: string }
export type ResumeBullet = { id: string; evidence_id: string; text: string; position: number; evidence_snapshot: { claim: string; source_note: string; metrics: { name: string; value: string; unit: string }[]; experience: { organization: string; title: string } | null; project: { name: string } | null } }
export type ResumeVersion = { id: string; resume_id: string; version_number: number; content: { profile: Profile; sections: { heading: string; evidence_ids: string[] }[] }; template: string; approved_at: string | null; created_at: string; bullets: ResumeBullet[] }
export type RequirementMatch = { requirement: { id: string; text: string; kind: string; priority: string; confirmed: boolean }; status: 'direct' | 'related' | 'unsupported'; matches: { evidence_id: string; evidence_text: string; state: string; status: 'direct' | 'related'; reason: string }[] }

function errorMessage(body: unknown): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((item) => item.msg ?? 'Invalid value').join('; ')
  }
  return 'Request failed'
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!response.ok) {
    let body: unknown
    try { body = await response.json() } catch { body = null }
    throw new Error(errorMessage(body))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function save<T>(path: string, method: 'POST' | 'PUT' | 'PATCH', data: unknown): Promise<T> {
  return api<T>(path, { method, body: JSON.stringify(data) })
}
