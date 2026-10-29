export type ContextFields = {
  kind: 'experience' | 'project'; organization: string; title: string; name: string
  experience_id: string; start_date: string; end_date: string; description: string
}

export function contextPayload(fields: ContextFields) {
  if (fields.start_date && fields.end_date && fields.end_date < fields.start_date) {
    throw new Error('End date must be after start date.')
  }
  const dates = { start_date: fields.start_date || null, end_date: fields.end_date || null }
  if (fields.kind === 'experience') {
    if (!fields.organization.trim() || !fields.title.trim()) {
      throw new Error('Enter an organization and role title.')
    }
    return { kind: 'experience' as const, data: {
      organization: fields.organization.trim(), title: fields.title.trim(),
      description: fields.description.trim(), ...dates,
    } }
  }
  if (!fields.name.trim()) throw new Error('Enter a project name.')
  return { kind: 'project' as const, data: {
    name: fields.name.trim(), experience_id: fields.experience_id || null,
    summary: fields.description.trim(), ...dates,
  } }
}
