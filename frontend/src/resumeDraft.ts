export type Heading = 'Experience' | 'Projects' | 'Selected evidence'
export const defaultHeadingOrder: Heading[] = ['Experience', 'Projects', 'Selected evidence']

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
