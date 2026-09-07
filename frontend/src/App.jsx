import { useState } from 'react'
import {
  ApiError,
  decideAction,
  getActions,
  getCase,
  postChat,
  uploadDocument,
} from './api.js'
import ChatPanel from './components/ChatPanel.jsx'
import CasePanel from './components/CasePanel.jsx'
import StartScreen from './components/StartScreen.jsx'
import './App.css'

function friendlyMessage(error) {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 404:
        return 'That item no longer exists. Please start a new case.'
      case 409:
        return error.message
      default:
        return error.message
    }
  }
  return 'Could not reach RESOLVE. Please check that the backend is running.'
}

function App() {
  const [screen, setScreen] = useState('start')
  const [sessionId, setSessionId] = useState(null)
  const [caseId, setCaseId] = useState(null)
  const [messages, setMessages] = useState([])
  const [caseData, setCaseData] = useState(null)
  const [documents, setDocuments] = useState([])
  const [actions, setActions] = useState([])
  const [chatBusy, setChatBusy] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [decideBusy, setDecideBusy] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  async function refreshCaseData(id) {
    const caseResponse = await getCase(id)
    setCaseData(caseResponse.case)
    setDocuments(caseResponse.documents)

    const actionsResponse = await getActions(id)
    setActions(actionsResponse.actions)
  }

  async function startCase(problem) {
    setError(null)
    setNotice(null)
    setChatBusy(true)
    try {
      const body = await postChat(problem)
      setSessionId(body.session_id)
      setMessages([
        { role: 'user', content: problem },
        { role: 'assistant', content: body.response },
      ])
      if (body.case_id) {
        setCaseId(body.case_id)
        await refreshCaseData(body.case_id)
      }
      setScreen('working')
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setChatBusy(false)
    }
  }

  async function sendMessage(text) {
    setError(null)
    setNotice(null)
    setMessages((current) => [...current, { role: 'user', content: text }])
    setChatBusy(true)
    try {
      const body = await postChat(text, sessionId)
      setMessages((current) => [...current, { role: 'assistant', content: body.response }])
      const activeCaseId = body.case_id || caseId
      if (activeCaseId) {
        setCaseId(activeCaseId)
        await refreshCaseData(activeCaseId)
      }
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setChatBusy(false)
    }
  }

  async function handleUpload(file) {
    if (!caseId) {
      setError('No active case yet. An action cannot be prepared until a case exists.')
      return
    }
    setError(null)
    setNotice(null)
    setUploadBusy(true)
    try {
      const body = await uploadDocument(caseId, file)
      setCaseData(body.case)
      const caseResponse = await getCase(caseId)
      setDocuments(caseResponse.documents)
      const actionsResponse = await getActions(caseId)
      setActions(actionsResponse.actions)
      if (body.analysis && body.analysis.response) {
        setMessages((current) => [
          ...current,
          { role: 'assistant', content: body.analysis.response },
        ])
      }
      setNotice(`Evidence added: ${file.name}.`)
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setUploadBusy(false)
    }
  }

  async function handleDecide(decision, actionId) {
    setError(null)
    setNotice(null)
    setDecideBusy(true)
    try {
      const body = await decideAction(actionId, decision)
      setActions((current) =>
        current.map((action) => (action.id === actionId ? body.action : action)),
      )
      setNotice(
        decision === 'approve'
          ? 'Action approved — ready for execution.'
          : 'Action rejected.',
      )
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setDecideBusy(false)
    }
  }

  function startOver() {
    setSessionId(null)
    setCaseId(null)
    setMessages([])
    setCaseData(null)
    setDocuments([])
    setActions([])
    setError(null)
    setNotice(null)
    setScreen('start')
  }

  if (screen === 'start') {
    return (
      <main className="app">
        <StartScreen onStart={startCase} busy={chatBusy} error={error} />
      </main>
    )
  }

  return (
    <main className="app">
      <header className="app-header">
        <h1>RESOLVE</h1>
        <p className="tagline">
          Don&apos;t just tell me what to do. Work toward resolving the problem.
        </p>
        <button className="restart" onClick={startOver}>
          Start over
        </button>
      </header>

      {error ? <p className="error banner">{error}</p> : null}
      {notice ? <p className="notice banner">{notice}</p> : null}

      <div className="layout">
        <div className="conversation-column">
          <ChatPanel messages={messages} onSend={sendMessage} busy={chatBusy} />
        </div>
        <CasePanel
          caseData={caseData}
          documents={documents}
          actions={actions}
          onUpload={handleUpload}
          onDecide={handleDecide}
          uploadBusy={uploadBusy}
          decideBusy={decideBusy}
        />
      </div>
    </main>
  )
}

export default App