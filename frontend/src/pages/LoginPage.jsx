import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth.js'
import BrandMark from '../components/BrandMark.jsx'

function LoginPage() {
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [showPassword, setShowPassword] = useState(false)

  const from = location.state?.from?.pathname || '/'

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)

    try {
      await login(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-page auth-page-login">
      <div className="auth-shell auth-shell-login">
        <section className="auth-showcase">
          <div className="auth-showcase-top">
            <Link to="/login" className="auth-brand" aria-label="RESOLVE home">
              <BrandMark size="lg" />
            </Link>

            <span className="auth-eyebrow">
              Consumer resolution, simplified
            </span>
          </div>

          <div className="auth-showcase-content">
            <div className="auth-pill">
              <span className="auth-pill-dot" />
              AI-guided. Human-controlled.
            </div>

            <h1>
              Turn frustrating
              <span> disputes into progress.</span>
            </h1>

            <p className="auth-showcase-lede">
              RESOLVE helps you organize evidence, understand responses,
              prepare the right next step, and keep your case moving forward.
            </p>

            <div className="auth-benefits">
              <div className="auth-benefit">
                <span className="auth-benefit-icon">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M12 3v18" />
                    <path d="M3 12h18" />
                    <path d="M5.5 7.5h13" />
                    <path d="M5.5 16.5h13" />
                  </svg>
                </span>
                <span>
                  <strong>Everything in one place</strong>
                  <small>Evidence, messages, responses and case history.</small>
                </span>
              </div>

              <div className="auth-benefit">
                <span className="auth-benefit-icon">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M12 3a7 7 0 0 0-7 7v3a4 4 0 0 1-1 2h16a4 4 0 0 1-1-2v-3a7 7 0 0 0-7-7Z" />
                    <path d="M9 19a3 3 0 0 0 6 0" />
                  </svg>
                </span>
                <span>
                  <strong>AI that keeps you informed</strong>
                  <small>Clear recommendations without taking control away.</small>
                </span>
              </div>

              <div className="auth-benefit">
                <span className="auth-benefit-icon">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M12 3 5 6v5c0 4.6 2.9 8.4 7 10 4.1-1.6 7-5.4 7-10V6l-7-3Z" />
                    <path d="m9 12 2 2 4-4" />
                  </svg>
                </span>
                <span>
                  <strong>You stay in control</strong>
                  <small>Review and approve actions before they are sent.</small>
                </span>
              </div>
            </div>
          </div>

          <div className="auth-showcase-footer">
            <span>Built for everyday consumer problems.</span>
            <span className="auth-footer-line" />
            <span>Resolve. Move forward.</span>
          </div>
        </section>

        <section className="auth-form-panel">
          <div className="auth-mobile-brand">
            <Link to="/login" className="auth-brand" aria-label="RESOLVE home">
              <BrandMark size="lg" />
            </Link>
          </div>

          <div className="auth-card auth-card-login">
            <div className="auth-card-heading">
              <span className="auth-card-kicker">Welcome back</span>
              <h2>Sign in to RESOLVE</h2>
              <p>
                Pick up where you left off and keep your dispute moving.
              </p>
            </div>

            <form
              className="auth-form"
              onSubmit={handleSubmit}
              aria-busy={busy}
            >
              <div className="field">
                <label htmlFor="email">Email address</label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  autoFocus
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  disabled={busy}
                  required
                  placeholder="you@example.com"
                />
              </div>

              <div className="field">
                <div className="field-label-row">
                  <label htmlFor="password">Password</label>
                </div>

                <div className="field-password">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    disabled={busy}
                    required
                  />

                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword((value) => !value)}
                    disabled={busy}
                    aria-label={
                      showPassword ? 'Hide password' : 'Show password'
                    }
                  >
                    {showPassword ? (
                      <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                        <path d="M9.88 9.88a3 3 0 0 0 4.24 4.24" />
                      </svg>
                    ) : (
                      <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {error ? (
                <p className="auth-error" role="alert">
                  {error}
                </p>
              ) : null}

              <button
                type="submit"
                className="auth-submit"
                disabled={busy || !email.trim() || !password}
              >
                <span>{busy ? 'Signing in…' : 'Sign in'}</span>

                {!busy ? (
                  <svg
                    width="17"
                    height="17"
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
                ) : null}
              </button>
            </form>

            <div className="auth-trust">
              <span className="auth-trust-icon">
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <rect x="5" y="10" width="14" height="10" rx="2" />
                  <path d="M8 10V7a4 4 0 0 1 8 0v3" />
                </svg>
              </span>
              <span>
                Your cases and evidence are private to your account.
              </span>
            </div>

            <div className="auth-divider">
              <span>New to RESOLVE?</span>
            </div>

            <Link to="/signup" className="auth-secondary-action">
              Create your account
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M5 12h14" />
                <path d="m13 6 6 6-6 6" />
              </svg>
            </Link>
          </div>

          <p className="auth-form-footer">
            RESOLVE helps consumers pursue refunds, returns and warranty
            claims with AI guidance and human approval.
          </p>
        </section>
      </div>
    </main>
  )
}

export default LoginPage