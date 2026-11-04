export function selectedClaim(text: string, start: number, end: number): string {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end > text.length || end <= start) {
    throw new Error('Highlight one accomplishment in the resume text first.')
  }
  const claim = text.slice(start, end).trim()
  if (!claim) throw new Error('Select an accomplishment, not just whitespace.')
  if (claim.length > 2000) throw new Error('Select one accomplishment of at most 2,000 characters.')
  return claim
}

export function intakeDraftPayload(text: string, claim: string, context: string, name: string, note: string, sourceEdited = false) {
  if (!claim || !text.includes(claim)) throw new Error('Select an exact excerpt from the current resume text.')
  const separator = context.indexOf(':')
  const type = context.slice(0, separator)
  const id = context.slice(separator + 1)
  if (!id || !['experience', 'project'].includes(type) || separator < 0) {
    throw new Error('Choose an experience or project for this claim.')
  }
  return {
    source_text: text, source_name: name || 'Pasted resume', claim,
    experience_id: type === 'experience' ? id : null,
    project_id: type === 'project' ? id : null,
    source_note: note,
    ...(sourceEdited ? { source_edited: true } : {}),
  }
}
