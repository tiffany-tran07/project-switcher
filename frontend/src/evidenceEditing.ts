import type { Evidence } from './api'

export type EvidenceForm = {
  claim: string; source_note: string; experience_id: string; project_id: string; skill_ids: string[]
}

export function evidenceForm(row?: Evidence): EvidenceForm {
  return {
    claim: row?.claim ?? '', source_note: row?.source_note ?? '',
    experience_id: row?.experience_id ?? '', project_id: row?.project_id ?? '',
    skill_ids: [...(row?.skill_ids ?? [])],
  }
}

export function hasEvidenceEdits(form: EvidenceForm, row?: Evidence): boolean {
  const saved = evidenceForm(row)
  return form.claim !== saved.claim || form.source_note !== saved.source_note
    || form.experience_id !== saved.experience_id || form.project_id !== saved.project_id
    || JSON.stringify([...form.skill_ids].sort()) !== JSON.stringify([...saved.skill_ids].sort())
}
