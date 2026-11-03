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
export type SourceAttachment = { id: string; evidence_id: string; original_name: string; media_type: string; checksum: string; size: number; created_at: string }
export type SourceAttachmentRef = Pick<SourceAttachment, 'id' | 'original_name' | 'media_type' | 'checksum' | 'size'>
export type SearchResult = { type: 'experience' | 'project' | 'skill' | 'evidence'; id: string; title: string }
export type Requirement = { id?: string; text: string; supporting_span?: string | null; normalized_term: string; kind: 'skill' | 'tool' | 'responsibility' | 'experience' | 'education' | 'certification'; priority: 'required' | 'preferred' | 'unclear'; confirmed: boolean }
export type AnalysisOutcome = { requested_method: 'deterministic' | 'ollama'; method_used: 'deterministic' | 'ollama' | 'preserved'; fallback: boolean; note: string }
export type LocalAIConfig = { endpoint: string | null; model: string; allowed: boolean; message: string }
export type LocalAICheck = { runtime_available: boolean; model_available: boolean | null; message: string }
export type Job = { id: string; company: string; title: string; url: string; raw_description: string; source: string; created_at: string; requirements: Requirement[]; analysis?: AnalysisOutcome | null }
export type ResumeEvidenceStatus = { evidence_id: string; eligible: boolean; problem: string | null }
export type DraftValidation = { valid: boolean; issues: { evidence_id: string; position: number; code: 'duplicate' | 'unavailable_evidence' | 'section_context' | 'unsafe_wording'; message: string }[] }
export type DashboardData = {
  today_utc: string
  counts: { jobs: number; resumes: number; applications: number; ready_evidence: number; evidence_needing_review: number; follow_ups_due: number }
  recent_jobs: { id: string; company: string; title: string }[]
  recent_resumes: { id: string; name: string; latest_version: number | null; latest_approved_version: number | null }[]
  recent_applications: { id: string; company: string; title: string; status: string; follow_up_date: string | null }[]
  due_follow_ups: { id: string; company: string; title: string; status: string; follow_up_date: string | null }[]
  evidence_needing_review: { id: string; claim: string; reason: string }[]
}
export type ApplicationStatus = 'planned' | 'applied' | 'interview' | 'offer' | 'rejected' | 'withdrawn'
export type ApplicationEvent = { id: string; event_type: string; previous_status: ApplicationStatus | null; status: ApplicationStatus | null; note: string; created_at: string }
export type Application = { id: string; job_id: string; resume_version_id: string; company: string; title: string; url: string; status: ApplicationStatus; applied_date: string | null; follow_up_date: string | null; notes: string; created_at: string; updated_at: string; events: ApplicationEvent[] }
export type AtsStatus = 'present_exact' | 'present_alias' | 'supported_but_missing_from_resume' | 'no_verified_evidence'
export type AtsReport = {
  version_id: string; export_id: string; format: 'docx' | 'pdf'; page_count: number | null; page_target: number; extracted_text: string; notes: string[]
  requirements: { requirement_id: string; text: string; status: AtsStatus; evidence_ids: string[]; reason: string }[]
  formatting: { name: string; status: 'passed' | 'warning' | 'not_checked'; message: string }[]
}
export type ExportFile = { id: string; version_id: string; format: 'docx' | 'pdf'; checksum: string; extracted_text: string; page_count: number | null; created_at: string }
export type Resume = { id: string; job_id: string; name: string; status: string; created_at: string }
export type ResumeBullet = { id: string; evidence_id: string; text: string; position: number; evidence_snapshot: { claim: string; source_note: string; attachments?: SourceAttachmentRef[]; metrics: { name: string; value: string; unit: string }[]; experience: { organization: string; title: string; start_date?: string | null; end_date?: string | null; location?: string } | null; project: { name: string; start_date?: string | null; end_date?: string | null; url?: string } | null } }
export type ResumeVersion = { id: string; resume_id: string; version_number: number; content: { profile: Partial<Profile>; sections: { heading: string; evidence_ids: string[] }[] }; template: string; approved_at: string | null; created_at: string; bullets: ResumeBullet[] }
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

export function loadEvidenceSource(id: string): Promise<Evidence> {
  return api<Evidence>(`/evidence/${encodeURIComponent(id)}`)
}

export type ResumeIntakePreview = { filename: string; format: string; text: string; warnings: string[] }

export async function previewResume(file: File, signal?: AbortSignal): Promise<ResumeIntakePreview> {
  if (!/\.(docx|txt)$/i.test(file.name)) throw new Error('Choose a DOCX or UTF-8 text file. PDF intake is not available yet.')
  if (file.size === 0) throw new Error('Resume file is empty')
  if (file.size > 5 * 1024 * 1024) throw new Error('Resume file exceeds the 5 MB limit')
  return api<ResumeIntakePreview>(`/resume-intake/preview?filename=${encodeURIComponent(file.name)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file, signal,
  })
}

export async function uploadSource(evidenceId: string, file: File): Promise<SourceAttachment> {
  if (!/\.txt$/i.test(file.name)) throw new Error('Choose a UTF-8 .txt source file. PDF and image attachments are not available yet.')
  if (file.size === 0) throw new Error('Source file is empty')
  if (file.size > 1024 * 1024) throw new Error('Source file exceeds the 1 MB limit')
  return api<SourceAttachment>(`/evidence/${encodeURIComponent(evidenceId)}/attachments?filename=${encodeURIComponent(file.name)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
  })
}

export async function downloadBackup(): Promise<Blob> {
  const response = await fetch(`${API_ROOT}/backup/export`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ acknowledge_personal_data: true }),
  })
  if (!response.ok) {
    let body: unknown
    try { body = await response.json() } catch { body = null }
    throw new Error(errorMessage(body))
  }
  return response.blob()
}

export function save<T>(path: string, method: 'POST' | 'PUT' | 'PATCH', data: unknown): Promise<T> {
  return api<T>(path, { method, body: JSON.stringify(data) })
}
