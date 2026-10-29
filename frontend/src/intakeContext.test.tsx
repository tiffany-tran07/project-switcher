import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import IntakeContextCreator from './IntakeContextCreator'
import { contextPayload, type ContextFields } from './intakeContext'

const fields: ContextFields = {
  kind: 'experience', organization: ' Example ', title: ' Engineer ', name: '',
  experience_id: '', start_date: '', end_date: '', description: ' Manual source details ',
}

describe('inline intake context creation', () => {
  it('submits only manually entered role values and does not invent dates', () => {
    expect(contextPayload(fields)).toEqual({ kind: 'experience', data: {
      organization: 'Example', title: 'Engineer', description: 'Manual source details',
      start_date: null, end_date: null,
    } })
  })

  it('creates independent or linked projects explicitly', () => {
    const independent = contextPayload({ ...fields, kind: 'project', name: ' Pipeline ' })
    expect(independent).toEqual({ kind: 'project', data: {
      name: 'Pipeline', experience_id: null, summary: 'Manual source details', start_date: null, end_date: null,
    } })
    const linked = contextPayload({ ...fields, kind: 'project', name: 'Pipeline', experience_id: 'exp1' })
    expect(linked.data).toHaveProperty('experience_id', 'exp1')
  })

  it('rejects blank required fields and reversed dates before making a request', () => {
    expect(() => contextPayload({ ...fields, organization: ' ' })).toThrow('organization')
    expect(() => contextPayload({ ...fields, title: ' ' })).toThrow('role title')
    expect(() => contextPayload({ ...fields, kind: 'project', name: ' ' })).toThrow('project name')
    expect(() => contextPayload({ ...fields, start_date: '2023-01-01', end_date: '2020-01-01' })).toThrow('End date')
  })

  it('explains that context creation keeps the preview and does not infer facts', () => {
    const html = renderToStaticMarkup(<IntakeContextCreator experiences={[]} disabled={false} onBusyChange={() => {}} onExperienceCreated={() => {}} onProjectCreated={() => {}} onCancel={() => {}} />)
    expect(html).toContain('nothing is inferred from the resume')
    expect(html).toContain('selected claim, and notes stay in place')
    expect(html).toContain('Create source and select it')
    expect(html).toContain('Cancel source creation')
  })
})
