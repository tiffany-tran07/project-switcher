export type Heading = 'Experience' | 'Projects' | 'Selected evidence'
export const defaultHeadingOrder: Heading[] = ['Experience', 'Projects', 'Selected evidence']
export type WorkingResumeDraft = {
  selected: string[]; headingOrder: Heading[]; headings: Record<string, Heading>; wording: Record<string, string>
}
export type WorkingDraftUpdate = (current: WorkingResumeDraft) => WorkingResumeDraft
export type WorkingDrafts = Record<string, WorkingResumeDraft>

export function emptyWorkingDraft(): WorkingResumeDraft {
  return { selected: [], headingOrder: [...defaultHeadingOrder], headings: {}, wording: {} }
}

export function updateWorkingDraft(drafts: WorkingDrafts, resumeId: string, update: WorkingDraftUpdate): WorkingDrafts {
  if (!resumeId) return drafts
  return { ...drafts, [resumeId]: update(drafts[resumeId] ?? emptyWorkingDraft()) }
}

export function buildSections(
  order: Heading[], selected: string[], headings: Record<string, Heading>, wording: Record<string, string>,
) {
  return order.map((heading) => ({
    heading,
    bullets: selected.filter((id) => (headings[id] ?? 'Selected evidence') === heading)
      .map((id) => ({ evidence_id: id, text: wording[id] ?? '' })),
  })).filter((section) => section.bullets.length > 0)
}

export function moveWithinSection(
  selected: string[], headings: Record<string, Heading>, id: string, offset: -1 | 1,
): string[] {
  const heading = headings[id] ?? 'Selected evidence'
  const peers = selected.filter((entry) => (headings[entry] ?? 'Selected evidence') === heading)
  const index = peers.indexOf(id)
  const target = peers[index + offset]
  if (index < 0 || target === undefined) return selected
  const next = [...selected]
  const fromIndex = next.indexOf(id)
  const toIndex = next.indexOf(target)
  next[fromIndex] = target
  next[toIndex] = id
  return next
}
