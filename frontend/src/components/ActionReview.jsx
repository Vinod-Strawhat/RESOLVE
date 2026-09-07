function ActionCard({ action, onDecide, busy }) {
  const isPending = action.status === 'pending_approval'
  const isApproved = action.status === 'approved'
  const isRejected = action.status === 'rejected'

  return (
    <article className="action-card">
      <div className="action-heading">
        <h3>{action.title}</h3>
        <span className={`status status-${action.status}`}>{action.status}</span>
      </div>
      <dl className="action-meta">
        <div>
          <dt>Type</dt>
          <dd>{action.type}</dd>
        </div>
        {action.target ? (
          <div>
            <dt>Target</dt>
            <dd>{action.target}</dd>
          </div>
        ) : null}
      </dl>
      <p className="action-reason">
        <strong>Reason:</strong> {action.reason}
      </p>
      <p className="action-content">
        <strong>Prepared content:</strong>
      </p>
      <blockquote className="action-content-box">{action.content}</blockquote>

      {isPending ? (
        <div className="approval-banner">
          This action has been prepared by RESOLVE and requires your approval.
        </div>
      ) : null}

      {isApproved ? (
        <div className="approval-result approved">Approved — ready for execution.</div>
      ) : null}

      {isRejected ? (
        <div className="approval-result rejected">Action rejected.</div>
      ) : null}

      {isPending ? (
        <div className="action-buttons">
          <button
            className="approve"
            onClick={() => onDecide('approve', action.id)}
            disabled={busy}
          >
            Approve
          </button>
          <button
            className="reject"
            onClick={() => onDecide('reject', action.id)}
            disabled={busy}
          >
            Reject
          </button>
        </div>
      ) : null}
    </article>
  )
}

function ActionReview({ actions, onDecide, busy }) {
  const relevant = actions.filter((action) => action.status !== 'draft')
  const pending = relevant.find((action) => action.status === 'pending_approval')

  if (relevant.length === 0) {
    return (
      <div className="action-review">
        <div className="panel-heading">
          <h2>Recommended Action</h2>
        </div>
        <p className="empty-hint">
          RESOLVE may prepare a recommended action once the case has enough evidence.
        </p>
      </div>
    )
  }

  return (
    <div className="action-review">
      <div className="panel-heading">
        <h2>Recommended Action</h2>
        <p className="panel-hint">
          {pending ? 'Waiting for your decision.' : 'No action currently waiting for approval.'}
        </p>
      </div>
      {relevant.map((action) => (
        <ActionCard key={action.id} action={action} onDecide={onDecide} busy={busy} />
      ))}
    </div>
  )
}

export default ActionReview