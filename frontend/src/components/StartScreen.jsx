import { useState } from 'react'
import BrandMark from '../components/BrandMark.jsx'

const EXAMPLES = [
  {
    title: 'Warranty rejected',
    text: 'My laptop warranty claim was rejected after two months of normal use.',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="13" rx="2" />
        <path d="M8 21h8M12 17v4" />
      </svg>
    ),
  },
  {
    title: 'Subscription issue',
    text: 'A subscription keeps charging my card after I cancelled.',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M20 11a8 8 0 1 0 1 4" />
        <path d="M20 4v7h-7" />
        <path d="M8 13h8M8 9h5" />
      </svg>
    ),
  },
  {
    title: 'Refund denied',
    text: 'The product I received was damaged and the seller refuses a refund.',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M20 12a8 8 0 1 1-2.34-5.66" />
        <path d="M20 4v6h-6" />
        <path d="M8 12h8M12 8v8" />
      </svg>
    ),
  },
]

function StartScreen({ onStart, busy, error }) {
  const [problem, setProblem] = useState('')

  function handleSubmit(event) {
    event.preventDefault()
    const text = problem.trim()
    if (!text) return
    onStart(text)
  }

  function fillExample(example) {
    setProblem(example)
  }

  return (
    <main className="start-screen">
      <div className="start-container">
        <section className="start-hero" aria-labelledby="start-heading">
          <div className="start-hero-badge">
            <span className="start-hero-badge-dot" />
            AI-guided. Human-controlled.
          </div>

          <div className="start-brand-mobile">
            <BrandMark size="lg" />
          </div>

          <h1 id="start-heading">
            Turn a frustrating dispute
            <span> into progress.</span>
          </h1>

          <p className="start-lede">
            Tell us what happened. RESOLVE analyzes your situation, helps
            build the right case, and guides you through the next step.
          </p>

          <div className="start-trust">
            <div className="start-trust-item">
              <span className="start-trust-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 3 5 6v5c0 4.42 2.99 8.56 7 10 4.01-1.44 7-5.58 7-10V6l-7-3Z" />
                  <path d="m9 12 2 2 4-4" />
                </svg>
              </span>
              <span>Guided analysis</span>
            </div>

            <div className="start-trust-item">
              <span className="start-trust-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M8 12h8M8 8h5M8 16h6" />
                  <rect x="4" y="3" width="16" height="18" rx="2" />
                </svg>
              </span>
              <span>Evidence-aware</span>
            </div>

            <div className="start-trust-item">
              <span className="start-trust-icon">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="12" r="8" />
                  <path d="m9 12 2 2 4-4" />
                </svg>
              </span>
              <span>You stay in control</span>
            </div>
          </div>
        </section>

        <section className="start-workspace">
          <div className="start-form-card">
            <div className="start-form-header">
              <div>
                <span className="start-form-eyebrow">Start a new case</span>
                <h2>What happened?</h2>
              </div>

              <span className="start-step">01</span>
            </div>

            <p className="start-form-description">
              Give us the situation in your own words. You don't need to
              organize everything first — we'll help with that.
            </p>

            <form className="start-form" onSubmit={handleSubmit}>
              <div className="start-input-wrap">
                <label htmlFor="problem">Describe your problem</label>

                <textarea
                  id="problem"
                  value={problem}
                  onChange={(event) => setProblem(event.target.value)}
                  placeholder="For example: I bought a laptop two months ago and it has started shutting down randomly. The warranty claim was rejected..."
                  rows={6}
                  disabled={busy}
                  autoFocus
                />

                <div className="start-input-footer">
                  <span>Start with whatever you know.</span>
                  <span>{problem.length > 0 ? `${problem.length} characters` : 'Your story'}</span>
                </div>
              </div>

              {error ? (
                <div className="start-error" role="alert">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M12 8v5M12 16h.01" />
                  </svg>
                  <span>{error}</span>
                </div>
              ) : null}

              <button
                className="start-submit"
                type="submit"
                disabled={busy || !problem.trim()}
              >
                <span>{busy ? 'Starting your case…' : 'Start my case'}</span>

                {!busy && (
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M5 12h13M13 6l6 6-6 6" />
                  </svg>
                )}

                {busy && <span className="start-spinner" aria-hidden="true" />}
              </button>
            </form>
          </div>

          <div className="start-examples-section">
            <div className="start-examples-header">
              <div>
                <span className="start-examples-eyebrow">Need a starting point?</span>
                <h2>Try an example</h2>
              </div>
              <span className="start-examples-hint">Select one to use it</span>
            </div>

            <div className="start-examples">
              {EXAMPLES.map((example) => (
                <button
                  key={example.title}
                  type="button"
                  className="start-example-card"
                  onClick={() => fillExample(example.text)}
                  disabled={busy}
                >
                  <span className="start-example-icon">
                    {example.icon}
                  </span>

                  <span className="start-example-content">
                    <strong>{example.title}</strong>
                    <span>{example.text}</span>
                  </span>

                  <svg
                    className="start-example-arrow"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path d="M5 12h13M13 6l6 6-6 6" />
                  </svg>
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}

export default StartScreen