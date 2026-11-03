import type { Evidence, ResumeEvidenceStatus } from './api'

export function eligibleEvidence(evidence: Evidence[], statuses: ResumeEvidenceStatus[] | null): Evidence[] {
  const eligible = new Set(statuses?.filter((row) => row.eligible === true).map((row) => row.evidence_id))
  return evidence.filter((row) => eligible.has(row.id))
}
