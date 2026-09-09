import { useRef, useState } from 'react'
import ActionReview from './ActionReview.jsx'

const STATUS_LABELS = {
  awaiting_response: 'Awaiting response',
  response_received: 'Response received',
  resolved: 'Resolved',
  needs_follow_up: 'Follow-up needed',
  human_intervention: 'Human intervention required',
  in_progress: 'In progress',
}

const CASE_FIELDS = [
  ['title', 'Title'],
  ['category', 'Category'],
  ['description', 'Description'],
  ['product', 'Product'],
  ['amount', 'Amount'],
  ['purchase_date', 'Purchase date'],
  ['seller', 'Seller'],
  ['warranty_expiry', 'Warranty expiry'],
  ['rejection_reason', 'Rejection reason'],
  ['status', 'Status'],
  ['next_action', 'Next action'],
]

function CaseDetails({ caseData }) {
  if (!caseData) {
    return (
      <div className="case-panel">
        <div className="panel-heading">
          <h2>Active Case</h2>
        </div>
        <p className="empty-hint">
          No case yet. RESOLVE will create a structured case as soon as it has
          enough details about your problem.
        </p>
      </div>
    )
  }

  return (
    <div className="case-panel">
      <div className="panel-heading">
        <h2>Active Case</h2>
      </div>
      <dl className="case-fields">
        {CASE_FIELDS.map(([key, label]) => {
          const value = caseData[key]
          if (value === null || value === undefined || value === '') {
            return null
          }
          const display = key === 'status' ? STATUS_LABELS[value] || value : String(value)
          return (
            <div className="case-field" key={key}>
              <dt>{label}</dt>
              <dd>{display}</dd>
            </div>
          )
        })}
        {CASE_FIELDS.every(([key]) => {
          const value = caseData[key]
          return value === null || value === undefined || value === ''
        }) ? (
          <p className="empty-hint">No case details have been recorded yet.</p>
        ) : null}
      </dl>
    </div>
  )
}

function EvidencePanel({ documents, onUpload, busy }) {
  const fileInput = useRef(null)

  function handleChange(event) {
    const [file] = event.target.files
    if (!file) return
    onUpload(file)
    event.target.value = ''
  }

  return (
    <div className="evidence-panel">
      <div className="panel-heading">
        <h2>Evidence</h2>
      </div>
      <form
        className="upload-form"
        onSubmit={(event) => {
          event.preventDefault()
          fileInput.current?.click()
        }}
      >
        <input
          ref={fileInput}
          type="file"
          accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
          onChange={handleChange}
          aria-label="Add evidence"
        />
        <button type="submit" disabled={busy}>
          {busy ? 'Uploading…' : 'Add evidence'}
        </button>
      </form>
      {documents.length === 0 ? (
        <p className="empty-hint">
          Upload a document to let RESOLVE extract evidence. Supported: txt, md, pdf.
        </p>
      ) : (
        <ul className="document-list">
          {documents.map((doc) => (
            <li key={doc.id}>
              <span className="document-name">{doc.filename}</span>
              <span className="document-meta">
                {doc.content_type ? `${doc.content_type} · ` : ''}
                {formatBytes(doc.size_bytes)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(0)} KB`
}

function ResponseTestingPanel({
  caseData,
  responses,
  onRecordResponse,
  onEvaluate,
  onEvaluateAI,
  onPrepareFollowup,
  responseBusy,
  evaluateBusy,
  aiEvaluateBusy,
  aiEvaluation,
  followupStatus,
  prepareFollowupBusy,
}) {
  const [source, setSource] = useState('simulated_support')
  const [content, setContent] = useState('')
  const canRespond =
    caseData &&
    (caseData.status === 'awaiting_response' ||
      caseData.status === 'needs_follow_up')
  const canEvaluate = caseData && caseData.status === 'response_received'
  const followupCount = followupStatus ? followupStatus.followup_count : 0
  const maxFollowups = followupStatus ? followupStatus.max_followups : 3

  if (!caseData) return null

  return (
    <div className="response-testing-panel">
      <div className="panel-heading">
        <h2>Resolution</h2>
        <p className="simulate-note">Simulated / manual testing only.</p>
      </div>

      <dl className="case-fields">
        <div className="case-field">
          <dt>Case status</dt>
          <dd className={`status-label status-${caseData.status || 'none'}`}>
            {STATUS_LABELS[caseData.status] || caseData.status || 'New'}
          </dd>
        </div>
      </dl>

      <form
        className="response-form"
        onSubmit={(event) => {
          event.preventDefault()
          if (content.trim()) onRecordResponse(source.trim(), content.trim())
        }}
      >
        <label>
          Source
          <input
            value={source}
            onChange={(e) => setSource(e.target.value)}
            disabled={!canRespond || responseBusy}
          />
        </label>
        <label>
          Response text
          <textarea
            rows={3}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={!canRespond || responseBusy}
            aria-label="Response text"
            placeholder="Enter the company's simulated response"
          />
        </label>
        <button type="submit" disabled={!canRespond || responseBusy || !content.trim()}>
          {responseBusy ? 'Recording…' : 'Record simulated response'}
        </button>
      </form>

      {!canRespond && (
        <p className="empty-hint">
          {caseData.status === 'resolved' || caseData.status === 'human_intervention'
            ? `Case is ${STATUS_LABELS[caseData.status]}. No further actions available.`
            : 'A response can be recorded once an action has been executed and the case is awaiting a response or needs a follow-up.'}
        </p>
      )}

      {responses.length > 0 && (
        <ul className="response-list">
          {responses.map((r) => (
            <li key={r.id} className="response-item">
              <p className="response-content">{r.content}</p>
              <span className="response-meta">
                {r.source} · {new Date(r.received_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}

      {caseData.status === 'needs_follow_up' && (
        <div className="followup-section">
          <h3>Follow-up required</h3>
          <p className="simulate-note">
            Follow-up attempt: {followupCount} / {maxFollowups}
          </p>
          {followupStatus && followupStatus.can_prepare_action ? (
            <button
              className="followup-button"
              onClick={onPrepareFollowup}
              disabled={prepareFollowupBusy}
            >
              {prepareFollowupBusy
                ? 'Preparing follow-up…'
                : 'Prepare Follow-up Action'}
            </button>
          ) : (
            <p className="empty-hint">
              {followupCount >= maxFollowups
                ? 'Maximum follow-up attempts reached. Human intervention required.'
                : 'An AI follow-up action is already being prepared or awaiting approval.'}
            </p>
          )}
        </div>
      )}

      {caseData.status === 'human_intervention' && (
        <div className="human-intervention-box">
          <h3>Human intervention required</h3>
          <p>
            RESOLVE cannot safely continue this case automatically. A human
            should review the case history and take over.
          </p>
        </div>
      )}

      {caseData.status === 'resolved' && (
        <div className="resolved-box">
          <h3>Resolved</h3>
          <p>This case has been resolved. No further actions are available.</p>
        </div>
      )}

      {canEvaluate && (
        <div className="action-buttons evaluate-buttons">
          <button
            className="resolved"
            onClick={() => onEvaluate('resolved')}
            disabled={evaluateBusy}
          >
            Mark resolved
          </button>
          <button
            className="needs-follow-up"
            onClick={() => onEvaluate('needs_follow_up')}
            disabled={evaluateBusy}
          >
            Needs follow-up
          </button>
          <button
            className="human-intervention"
            onClick={() => onEvaluate('human_intervention')}
            disabled={evaluateBusy}
          >
            Human intervention
          </button>
        </div>
      )}

      {canEvaluate && (
        <div className="ai-eval-section">
          <div className="ai-eval-divider">
            <span>or</span>
          </div>
          <button
            className="ai-eval-button"
            onClick={onEvaluateAI}
            disabled={aiEvaluateBusy}
          >
            {aiEvaluateBusy ? 'Analyzing response…' : 'Analyze Response with AI'}
          </button>
        </div>
      )}

      {aiEvaluation && (
        <div className="ai-evaluation-result">
          <h3>AI Evaluation</h3>
          <dl className="eval-meta">
            <div>
              <dt>Outcome</dt>
              <dd className={`eval-outcome eval-${aiEvaluation.outcome}`}>
                {STATUS_LABELS[aiEvaluation.outcome] || aiEvaluation.outcome}
              </dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{Math.round(aiEvaluation.confidence * 100)}%</dd>
            </div>
          </dl>
          <div className="eval-field">
            <dt>Reason</dt>
            <dd>{aiEvaluation.reason}</dd>
          </div>
          <div className="eval-field">
            <dt>Next step</dt>
            <dd>{aiEvaluation.next_step}</dd>
          </div>
        </div>
      )}

      {!canEvaluate && caseData.status === 'response_received' && (
        <p className="empty-hint">Evaluate the latest response to continue.</p>
      )}
    </div>
  )
}

function CasePanel({
  caseData,
  documents,
  actions,
  responses,
  onUpload,
  onDecide,
  onExecute,
  onRecordResponse,
  onEvaluate,
  onEvaluateAI,
  onPrepareFollowup,
  uploadBusy,
  decideBusy,
  executeBusy,
  responseBusy,
  evaluateBusy,
  aiEvaluateBusy,
  aiEvaluation,
  followupStatus,
  prepareFollowupBusy,
}) {
  return (
    <div className="case-column">
      <CaseDetails caseData={caseData} />
      <EvidencePanel
        documents={documents}
        onUpload={onUpload}
        busy={uploadBusy}
      />
      <ActionReview
        actions={actions}
        onDecide={onDecide}
        onExecute={onExecute}
        busy={decideBusy}
        executeBusy={executeBusy}
      />
      <ResponseTestingPanel
        caseData={caseData}
        responses={responses}
        onRecordResponse={onRecordResponse}
        onEvaluate={onEvaluate}
        onEvaluateAI={onEvaluateAI}
        onPrepareFollowup={onPrepareFollowup}
        responseBusy={responseBusy}
        evaluateBusy={evaluateBusy}
        aiEvaluateBusy={aiEvaluateBusy}
        aiEvaluation={aiEvaluation}
        followupStatus={followupStatus}
        prepareFollowupBusy={prepareFollowupBusy}
      />
    </div>
  )
}

export default CasePanel