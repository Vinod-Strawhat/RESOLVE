import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listMyCases } from '../api.js'
import CaseCard from '../components/CaseCard.jsx'

function CasesPage() {
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    listMyCases()
      .then((body) => {
        if (!cancelled) setCases(body.cases)
      })
      .catch(() => {
        if (!cancelled) setError('We couldn’t load your cases.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  function handleRetry() {
    setLoading(true)
    setError(null)

    listMyCases()
      .then((body) => setCases(body.cases))
      .catch(() => setError('We couldn’t load your cases.'))
      .finally(() => setLoading(false))
  }

  const activeCases = cases.filter(
    (caseItem) =>
      caseItem.status !== 'resolved'
  ).length

  const resolvedCases = cases.filter(
    (caseItem) =>
      caseItem.status === 'resolved'
  ).length

  return (
    <main className="dashboard-page">
      <div className="dashboard-container">

        {/* Header */}
        <header className="dashboard-header dashboard-header-premium">
          <div className="dashboard-heading">
            <span className="dashboard-kicker">Your resolution space</span>
            <h1 className="dashboard-title">My Cases</h1>
            <p className="dashboard-subtitle">
              Keep track of your disputes and the next step toward resolution.
            </p>
          </div>

          <Link to="/" className="new-dispute-btn">
            <span className="new-dispute-icon" aria-hidden="true">
              <svg
                width="17"
                height="17"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M12 5v14" />
                <path d="M5 12h14" />
              </svg>
            </span>
            New Dispute
          </Link>
        </header>

        {/* Summary */}
        {!loading && !error && (
          <section className="dashboard-stats" aria-label="Case summary">
            <div className="dashboard-stat dashboard-stat-primary">
              <span className="dashboard-stat-label">All cases</span>
              <strong>{cases.length}</strong>
              <span className="dashboard-stat-caption">
                {cases.length === 1 ? 'dispute' : 'disputes'}
              </span>
            </div>

            <div className="dashboard-stat">
              <span className="dashboard-stat-label">Active</span>
              <strong>{activeCases}</strong>
              <span className="dashboard-stat-caption">
                {activeCases === 1 ? 'needs attention' : 'in progress'}
              </span>
            </div>

            <div className="dashboard-stat">
              <span className="dashboard-stat-label">Resolved</span>
              <strong>{resolvedCases}</strong>
              <span className="dashboard-stat-caption">
                {resolvedCases === 1 ? 'case closed' : 'cases closed'}
              </span>
            </div>
          </section>
        )}

        {/* Loading */}
        {loading && (
          <section className="dashboard-state dashboard-loading">
            <div className="dashboard-loading-icon" aria-hidden="true">
              <span />
            </div>
            <div>
              <strong>Loading your cases</strong>
              <p>Getting your latest dispute activity…</p>
            </div>
          </section>
        )}

        {/* Error */}
        {!loading && error && (
          <section className="dashboard-state dashboard-error">
            <div className="dashboard-state-icon dashboard-state-icon-error">
              !
            </div>

            <div className="dashboard-state-content">
              <strong>We couldn’t load your cases</strong>
              <p>{error}</p>
            </div>

            <button
              className="retry-button"
              onClick={handleRetry}
              type="button"
            >
              Try again
            </button>
          </section>
        )}

        {/* Empty */}
        {!loading && !error && cases.length === 0 && (
          <section className="dashboard-empty dashboard-empty-premium">
            <div className="dashboard-empty-icon" aria-hidden="true">
              <svg
                width="30"
                height="30"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M7 3h8l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
                <path d="M15 3v5h4" />
                <path d="M9 13h6" />
                <path d="M9 17h4" />
              </svg>
            </div>

            <span className="dashboard-empty-kicker">
              Your resolution journey starts here
            </span>

            <h2>No disputes yet</h2>

            <p>
              Start your first dispute and let RESOLVE organize the details,
              evidence, responses, and next steps for you.
            </p>

            <Link to="/" className="new-dispute-btn dashboard-empty-action">
              Start a Dispute
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
            </Link>
          </section>
        )}

        {/* Cases */}
        {!loading && !error && cases.length > 0 && (
          <section className="dashboard-cases-section">
            <div className="dashboard-section-heading">
              <div>
                <span className="dashboard-section-kicker">
                  Case activity
                </span>
                <h2>Your disputes</h2>
              </div>

              <span className="dashboard-case-count">
                {cases.length} {cases.length === 1 ? 'case' : 'cases'}
              </span>
            </div>

            <div className="case-grid">
              {cases.map((caseItem) => (
                <CaseCard
                  key={caseItem.id}
                  caseData={caseItem}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  )
}

export default CasesPage