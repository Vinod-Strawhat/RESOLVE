function ActionCard({ action, onDecide, onExecute, busy, executeBusy }) {
  const isPending = action.status === 'pending_approval'
  const isApproved = action.status === 'approved'
  const isExecuting = action.status === 'executing'
  const isExecuted = action.status === 'executed'
  const isFailed = action.status === 'failed'
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
        <div className="approval-result approved">
          Approved — ready for execution.
        </div>
      ) : null}

      {isExecuting ? (
        <div className="approval-result">Executing…</div>
      ) : null}

      {isExecuted ? (
        <div className="approval-result approved">Executed.</div>
      ) : null}

      {isFailed ? (
        <div className="approval-result rejected">Execution failed.</div>
      ) : null}

      {isRejected ? (
        <div className="approval-result rejected">Action rejected.</div>
      ) : null}

      {isExecuted ? (
        <dl className="execution-meta">
          {action.execution_reference ? (
            <div>
              <dt>Execution reference</dt>
              <dd>{action.execution_reference}</dd>
            </div>
          ) : null}
          {action.executed_at ? (
            <div>
              <dt>Executed at</dt>
              <dd>{new Date(action.executed_at).toLocaleString()}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {isExecuted && action.execution_result ? (
        <p className="execution-result">{action.execution_result}</p>
      ) : null}

      {isFailed && action.execution_error ? (
        <p className="execution-result error">{action.execution_error}</p>
      ) : null}

      {isExecuted ? (
        <p className="empty-hint">Case status is now: Awaiting response.</p>
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

      {isApproved ? (
        <div className="action-buttons">
          <button
            className="execute"
            onClick={() => onExecute(action.id)}
            disabled={executeBusy}
          >
            {executeBusy ? 'Executing…' : 'Execute Action'}
          </button>
        </div>
      ) : null}
    </article>
  )
}

function ActionReview({ actions, onDecide, onExecute, busy, executeBusy }) {
  const relevant = actions.filter((action) => action.status !== 'draft')
  const waiting = relevant.find(
    (action) =>
      action.status === 'pending_approval' ||
      action.status === 'approved' ||
      action.status === 'executing',
  )

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
          {waiting ? 'Awaiting your decision or execution.' : 'No action currently waiting for approval.'}
        </p>
      </div>
      {relevant.map((action) => (
        <ActionCard
          key={action.id}
          action={action}
          onDecide={onDecide}
          onExecute={onExecute}
          busy={busy}
          executeBusy={executeBusy}
        />
      ))}
    </div>
  )
}

export default ActionReview