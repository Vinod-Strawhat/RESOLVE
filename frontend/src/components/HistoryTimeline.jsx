const ACTIVITY_TYPES = new Set(['response', 'evaluation', 'action', 'followup'])

const TYPE_LABELS = {
  case_created: 'Case created',
  case_resolved: 'Case resolved',
  response: 'Response',
  evaluation: 'Evaluation',
  action: 'Action',
  followup: 'Follow-up',
}

function formatTimestamp(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function DetailRow({ label, value }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="timeline-detail-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function EventDetail({ event }) {
  const detail = event.detail || {}
  switch (event.event_type) {
    case 'response':
      return (
        <div className="timeline-body">
          <DetailRow label="Source" value={event.source} />
          {detail.content ? (
            <div className="timeline-detail-row">
              <dt>Content</dt>
              <dd className="timeline-text">{detail.content}</dd>
            </div>
          ) : null}
          <DetailRow label="Received" value={formatTimestamp(detail.received_at)} />
        </div>
      )
    case 'evaluation':
      return (
        <div className="timeline-body">
          <DetailRow label="Source" value={event.source === 'ai' ? 'AI' : 'Manual'} />
          {detail.confidence !== null && detail.confidence !== undefined ? (
            <DetailRow label="Confidence" value={`${Math.round(detail.confidence * 100)}%`} />
          ) : null}
          <DetailRow label="Reason" value={detail.reason} />
          <DetailRow label="Next step" value={detail.next_step} />
        </div>
      )
    case 'action':
      return (
        <div className="timeline-body">
          <DetailRow label="Type" value={detail.type} />
          <DetailRow label="Target" value={detail.target} />
          {detail.execution_channel ? (
            <DetailRow label="Channel" value={detail.execution_channel} />
          ) : null}
          {detail.execution_reference ? (
            <DetailRow label="Reference" value={detail.execution_reference} />
          ) : null}
          {detail.executed_at ? (
            <DetailRow label="Executed" value={formatTimestamp(detail.executed_at)} />
          ) : null}
          <DetailRow label="Reason" value={detail.reason} />
          {detail.content ? (
            <div className="timeline-detail-row">
              <dt>Content</dt>
              <dd className="timeline-text">{detail.content}</dd>
            </div>
          ) : null}
          {detail.execution_result ? (
            <DetailRow label="Result" value={detail.execution_result} />
          ) : null}
          {detail.execution_error ? (
            <DetailRow label="Error" value={detail.execution_error} />
          ) : null}
        </div>
      )
    case 'followup':
      return (
        <div className="timeline-body">
          <DetailRow label="Attempt" value={`#${detail.attempt_number}`} />
          {detail.confidence !== null && detail.confidence !== undefined ? (
            <DetailRow label="Confidence" value={`${Math.round(detail.confidence * 100)}%`} />
          ) : null}
          <DetailRow label="Reason" value={detail.reason} />
        </div>
      )
    default:
      return null
  }
}

function statusPill(event) {
  if (!event.status) return null
  const className =
    event.event_type === 'evaluation'
      ? `eval-outcome eval-${event.status}`
      : `status status-${event.status}`
  return <span className={className}>{event.status.replace(/_/g, ' ')}</span>
}

function TimelineRow({ event }) {
  return (
    <li className={`timeline-event timeline-event-${event.event_type}`}>
      <span className="timeline-dot" aria-hidden="true" />
      <div className="timeline-card">
        <div className="timeline-heading">
          <h3>{event.title}</h3>
          <span className="timeline-meta">
            {TYPE_LABELS[event.event_type] || event.event_type} ·{' '}
            {formatTimestamp(event.occurred_at)}
          </span>
        </div>
        <div className="timeline-badges">
          {statusPill(event)}
          {event.source && event.event_type !== 'evaluation' ? (
            <span className="timeline-source">{event.source}</span>
          ) : null}
        </div>
        <EventDetail event={event} />
      </div>
    </li>
  )
}

function HistoryTimeline({ events, loading, error, onRetry }) {
  const list = events || []
  const activity = list.filter((event) => ACTIVITY_TYPES.has(event.event_type))

  return (
    <div className="history-panel">
      <div className="panel-heading">
        <h2>Resolution Timeline</h2>
        <p className="panel-hint">Full lifecycle of this case in one place.</p>
      </div>

      {loading ? (
        <p className="empty-hint">Loading case history…</p>
      ) : error ? (
        <div className="history-error">
          <p className="error">{error}</p>
          <button type="button" className="retry-button" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : list.length === 0 ? (
        <p className="empty-hint">No history is available for this case yet.</p>
      ) : (
        <>
          {activity.length === 0 ? (
            <p className="empty-hint">
              No lifecycle activity has been recorded for this case yet.
            </p>
          ) : null}
          <ul className="timeline-list">
            {list.map((event) => (
              <TimelineRow key={`${event.event_type}-${event.id}`} event={event} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

export default HistoryTimeline