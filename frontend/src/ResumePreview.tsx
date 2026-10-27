import type { ResumeBullet, ResumeVersion } from './api'

function dateRange(start?: string | null, end?: string | null) {
  // Missing end dates do not prove that a role is still current.
  return [start, end].filter(Boolean).join(' – ')
}

function contextFor(bullet: ResumeBullet, heading: string) {
  const { experience, project } = bullet.evidence_snapshot
  if (heading === 'Projects' && project) {
    return {
      title: project.name,
      organization: experience?.organization,
      dates: dateRange(project.start_date, project.end_date),
      location: undefined,
      url: project.url,
    }
  }
  return {
    title: experience?.title ?? project?.name,
    organization: experience?.organization,
    dates: experience ? dateRange(experience.start_date, experience.end_date)
      : dateRange(project?.start_date, project?.end_date),
    location: experience?.location,
    url: experience ? undefined : project?.url,
  }
}

export default function ResumePreview({ version }: { version: ResumeVersion }) {
  const profile = version.content.profile
  const contact = [profile.email, profile.phone, profile.location].filter(Boolean)
  return (
    <article className="resume-document" aria-label={`Resume preview version ${version.version_number}`}>
      {(profile.name || contact.length > 0 || profile.links?.length) ? <header>
        {profile.name && <h2>{profile.name}</h2>}
        {contact.length > 0 && <p>{contact.join(' · ')}</p>}
        {profile.links?.map((link, index) => <p key={`${index}-${link}`}>{link}</p>)}
      </header> : null}
      {version.content.sections.map((section) => {
        const groups: { context: ReturnType<typeof contextFor>; bullets: ResumeBullet[] }[] = []
        for (const id of section.evidence_ids) {
          const bullet = version.bullets.find((row) => row.evidence_id === id)
          if (!bullet) continue
          const context = contextFor(bullet, section.heading)
          const previous = groups.at(-1)
          if (previous && JSON.stringify(previous.context) === JSON.stringify(context)) {
            previous.bullets.push(bullet)
          } else {
            groups.push({ context, bullets: [bullet] })
          }
        }
        return <section key={section.heading}>
          <h3>{section.heading}</h3>
          {groups.map(({ context, bullets }) => <div className="resume-role" key={bullets[0].id}>
            {context.title && <h4>{context.title}</h4>}
            {context.organization && <p>{context.organization}</p>}
            {(context.dates || context.location) && <p>{[context.dates, context.location].filter(Boolean).join(' · ')}</p>}
            {context.url && <p>{context.url}</p>}
            <ul>{bullets.map((bullet) => <li key={bullet.id}>{bullet.text}</li>)}</ul>
          </div>)}
        </section>
      })}
    </article>
  )
}
