import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext.jsx'
import { useAuth } from './auth/useAuth.js'
import WorkflowScreen from './components/WorkflowScreen.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import BrandMark from './components/BrandMark.jsx'
import LoginPage from './pages/LoginPage.jsx'
import SignupPage from './pages/SignupPage.jsx'
import CasesPage from './pages/CasesPage.jsx'
import './App.css'

function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    try {
      await logout()
    } finally {
      navigate('/login', { replace: true })
    }
  }

  const initials = (user.display_name || user.email || '?')
    .trim()
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <div className="user-menu">
      <div className="user-identity">
        <span
          className="user-avatar"
          title={user.display_name || user.email}
          aria-hidden="true"
        >
          {initials}
        </span>

        <div className="user-details">
          <span className="user-name">
            {user.display_name || user.email}
          </span>
          <span className="user-label">Account</span>
        </div>
      </div>

      <button
        className="logout"
        onClick={handleLogout}
        type="button"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M10 17l5-5-5-5" />
          <path d="M15 12H3" />
          <path d="M21 19V5a2 2 0 0 0-2-2h-5" />
        </svg>
        <span>Sign out</span>
      </button>
    </div>
  )
}

function AppHeader() {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) return null

  const isCasesPage =
    location.pathname === '/cases' ||
    location.pathname.startsWith('/cases/')

  const isNewDisputePage = location.pathname === '/'

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link
          to="/cases"
          className="brand-link"
          aria-label="RESOLVE home"
        >
          <BrandMark size="md" />
        </Link>

        <nav className="app-nav" aria-label="Primary navigation">
          <Link
            to="/cases"
            className={`nav-link ${isCasesPage ? 'nav-link-active' : ''}`}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="4" y="4" width="16" height="16" rx="3" />
              <path d="M8 9h8" />
              <path d="M8 13h5" />
            </svg>
            <span>My Cases</span>
          </Link>

          <Link
            to="/"
            className={`nav-link ${isNewDisputePage ? 'nav-link-active' : ''}`}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 5v14" />
              <path d="M5 12h14" />
            </svg>
            <span>New Dispute</span>
          </Link>
        </nav>

        <UserMenu />
      </div>
    </header>
  )
}

function AuthenticatedLayout() {
  const { isAuthenticated } = useAuth()

  return (
    <>
      {isAuthenticated ? <AppHeader /> : null}

      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<WorkflowScreen />} />
          <Route path="/cases" element={<CasesPage />} />
          <Route path="/cases/:caseId" element={<WorkflowScreen />} />
        </Route>

        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />

        <Route
          path="*"
          element={<Navigate to="/cases" replace />}
        />
      </Routes>
    </>
  )
}

function App() {
  return (
    <AuthProvider>
      <AuthenticatedLayout />
    </AuthProvider>
  )
}

export default App