import { useRef } from 'react'
import ActionReview from './ActionReview.jsx'

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
          return (
            <div className="case-field" key={key}>
              <dt>{label}</dt>
              <dd>{String(value)}</dd>
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

function CasePanel({
  caseData,
  documents,
  actions,
  onUpload,
  onDecide,
  onExecute,
  uploadBusy,
  decideBusy,
  executeBusy,
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
    </div>
  )
}

export default CasePanel