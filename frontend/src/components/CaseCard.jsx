import { Link } from 'react-router-dom'

const STATUS_LABELS = {
  awaiting_response: 'Awaiting response',
  response_received: 'Response received',
  resolved: 'Resolved',
  needs_follow_up: 'Follow-up needed',
  human_intervention: 'Human intervention required',
}

function formatDate(isoString) {
  if (!isoString) return ''

  const date = new Date(isoString)

  if (Number.isNaN(date.getTime())) return ''

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function getStatusDescription(status) {
  const descriptions = {
    awaiting_response: 'Waiting for the company',
    response_received: 'A response is ready to review',
    resolved: 'This dispute has been resolved',
    needs_follow_up: 'Your next step is ready',
    human_intervention: 'Needs your attention',
  }

  return descriptions[status] || 'Dispute in progress'
}

function getStatusIcon(status) {
  if (status === 'resolved') {
    return (
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="m5 12 4 4L19 6" />
      </svg>
    )
  }

  if (status === 'needs_follow_up') {
    return (
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 8v4l2.5 2.5" />
        <circle cx="12" cy="12" r="8.5" />
      </svg>
    )
  }

  if (status === 'human_intervention') {
    return (
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
        <path d="M10.3 4.8 3.7 16.2a2 2 0 0 0 1.7 3h13.2a2 2 0 0 0 1.7-3L13.7 4.8a2 2 0 0 0-3.4 0Z" />
      </svg>
    )
  }

  if (status === 'response_received') {
    return (
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M20 11.5a7.5 7.5 0 0 1-8 7.4 7.7 7.7 0 0 1-3.1-.7L4 20l1.8-4.1A7.5 7.5 0 1 1 20 11.5Z" />
      </svg>
    )
  }

  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3 2" />
    </svg>
  )
}

function CaseCard({ caseData }) {
  const status = caseData.status || 'new'
  const statusLabel = STATUS_LABELS[status] || status || 'New'
  const title = caseData.title || caseData.product || 'Untitled dispute'
  const meta = [caseData.product, caseData.seller].filter(Boolean).join(' · ')

  return (
    <article className="case-card">
      <Link
        to={`/cases/${encodeURIComponent(caseData.id)}`}
        className="case-card-main"
        aria-label={`Open case: ${title}`}
      >
        <div className="case-card-top">
          <span className={`case-card-status status-${status}`}>
            <span className="case-card-status-icon">
              {getStatusIcon(status)}
            </span>
            {statusLabel}
          </span>

          {caseData.updated_at && (
            <span className="case-card-date">
              {formatDate(caseData.updated_at)}
            </span>
          )}
        </div>

        <div className="case-card-content">
          <h3 className="case-card-title">
            {title}
          </h3>

          {meta && (
            <p className="case-card-meta">
              {meta}
            </p>
          )}

          <p className="case-card-description">
            {getStatusDescription(status)}
          </p>
        </div>

        <div className="case-card-footer">
          {caseData.followup_count > 0 ? (
            <span className="case-card-followup">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M21 12a9 9 0 1 1-3-6.7" />
                <path d="M21 3v6h-6" />
              </svg>
              Follow-up {caseData.followup_count}
            </span>
          ) : (
            <span className="case-card-footer-label">
              Dispute case
            </span>
          )}

          <span className="case-card-link">
            View case
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M5 12h14" />
              <path d="m13 6 6 6-6 6" />
            </svg>
          </span>
        </div>
      </Link>
    </article>
  )
}

export default CaseCard