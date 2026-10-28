import type { ApplicationEvent } from './api'

export default function ApplicationHistory({ events }: { events: ApplicationEvent[] }) {
  return <section aria-label="Application history"><h3>History</h3><ol className="application-history">
    {events.map((event) => <li key={event.id}>
      <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
      <strong>{event.event_type.replaceAll('_', ' ')}{event.status && ` · ${event.previous_status ? `${event.previous_status} → ` : ''}${event.status}`}</strong>
      {event.note && <p>{event.note}</p>}
    </li>)}
  </ol></section>
}
