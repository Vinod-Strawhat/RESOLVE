import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ApiError,
  decideAction,
  evaluateCase,
  evaluateResponseAI,
  executeAction,
  getActions,
  getCase,
  getExecutionConfig,
  getFollowupStatus,
  getHistory,
  getResponses,
  postChat,
  prepareFollowup,
  recordResponse,
  uploadDocument,
} from '../api.js'
import ChatPanel from './ChatPanel.jsx'
import CasePanel from './CasePanel.jsx'
import StartScreen from './StartScreen.jsx'

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

function WorkflowScreen() {
  const { caseId: urlCaseId } = useParams()
  const navigate = useNavigate()

  const [screen, setScreen] = useState(urlCaseId ? 'working' : 'start')
  const loadedCaseIdRef = useRef(null)

  const [sessionId, setSessionId] = useState(null)
  const [caseId, setCaseId] = useState(null)
  const [messages, setMessages] = useState([])
  const [caseData, setCaseData] = useState(null)
  const [documents, setDocuments] = useState([])
  const [actions, setActions] = useState([])

  const [chatBusy, setChatBusy] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [decideBusy, setDecideBusy] = useState(false)
  const [executeBusy, setExecuteBusy] = useState(false)

  const [responses, setResponses] = useState([])
  const [responseBusy, setResponseBusy] = useState(false)
  const [evaluateBusy, setEvaluateBusy] = useState(false)
  const [aiEvaluateBusy, setAiEvaluateBusy] = useState(false)
  const [aiEvaluation, setAiEvaluation] = useState(null)

  const [followupStatus, setFollowupStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState(null)
  const [prepareFollowupBusy, setPrepareFollowupBusy] = useState(false)

  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  const [executionConfig, setExecutionConfig] = useState({
    channel: 'simulated',
    real_sending_enabled: false,
  })

  useEffect(() => {
    getExecutionConfig()
      .then(setExecutionConfig)
      .catch(() => {
        setExecutionConfig({
          channel: 'simulated',
          real_sending_enabled: false,
        })
      })
  }, [])

  useEffect(() => {
    if (urlCaseId === undefined) {
      if (loadedCaseIdRef.current !== null) {
        loadedCaseIdRef.current = null
        startOver()
      }
      return
    }

    if (urlCaseId === loadedCaseIdRef.current) return

    loadedCaseIdRef.current = urlCaseId
    setScreen('working')
    setError(null)
    setNotice(null)

    refreshCaseData(urlCaseId).catch((err) => {
      setError(friendlyMessage(err))
    })

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlCaseId])

  async function refreshCaseData(id) {
    const caseResponse = await getCase(id)

    setCaseId(id)
    setSessionId(caseResponse.case.session_id || null)
    setCaseData(caseResponse.case)
    setDocuments(caseResponse.documents)

    const actionsResponse = await getActions(id)
    setActions(actionsResponse.actions)

    const responsesResponse = await getResponses(id)
    setResponses(responsesResponse.responses)

    const followupResponse = await getFollowupStatus(id)
    setFollowupStatus(followupResponse)

    await refreshHistory(id)
  }

  async function refreshHistory(id) {
    if (!id) return

    setHistoryLoading(true)
    setHistoryError(null)

    try {
      const body = await getHistory(id)
      setHistory(body.events)
    } catch {
      setHistory([])
      setHistoryError('Could not load the case history.')
    } finally {
      setHistoryLoading(false)
    }
  }

  async function startCase(problem) {
    setError(null)
    setNotice(null)
    setChatBusy(true)

    try {
      const body = await postChat(problem)

      setSessionId(body.session_id)

      setMessages([
        {
          role: 'user',
          content: problem,
        },
        {
          role: 'assistant',
          content: body.response,
        },
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

    setMessages((current) => [
      ...current,
      {
        role: 'user',
        content: text,
      },
    ])

    setChatBusy(true)

    try {
      const body = await postChat(text, sessionId)

      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: body.response,
        },
      ])

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
      setError(
        'No active case yet. An action cannot be prepared until a case exists.',
      )
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
          {
            role: 'assistant',
            content: body.analysis.response,
          },
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
        current.map((action) =>
          action.id === actionId ? body.action : action,
        ),
      )

      setNotice(
        decision === 'approve'
          ? 'Action approved — ready for execution.'
          : 'Action rejected.',
      )

      if (caseId) {
        await refreshHistory(caseId)
      }
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setDecideBusy(false)
    }
  }

  async function handleExecute(actionId) {
    setError(null)
    setNotice(null)
    setExecuteBusy(true)

    try {
      const body = await executeAction(actionId)

      setActions((current) =>
        current.map((action) =>
          action.id === actionId ? body.action : action,
        ),
      )

      if (caseId) {
        const caseResponse = await getCase(caseId)
        setCaseData(caseResponse.case)
      }

      setNotice('Action executed.')

      if (caseId) {
        await refreshHistory(caseId)
      }
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setExecuteBusy(false)
    }
  }

  async function handleRecordResponse(source, content) {
    if (!caseId) return

    setError(null)
    setNotice(null)
    setResponseBusy(true)

    try {
      const body = await recordResponse(caseId, {
        source,
        content,
      })

      setCaseData(body.case)

      const responsesResponse = await getResponses(caseId)
      setResponses(responsesResponse.responses)

      setNotice(
        `Simulated response recorded (${source}). Case status: ${body.case.status}.`,
      )

      await refreshHistory(caseId)
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setResponseBusy(false)
    }
  }

  async function handleEvaluate(outcome) {
    if (!caseId) return

    setError(null)
    setNotice(null)
    setEvaluateBusy(true)

    try {
      const body = await evaluateCase(caseId, outcome)

      setCaseData(body.case)

      setNotice(`Case marked: ${body.case.status}.`)

      await refreshHistory(caseId)
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setEvaluateBusy(false)
    }
  }

  async function handleEvaluateAI() {
    if (!caseId) return

    setError(null)
    setNotice(null)
    setAiEvaluation(null)
    setAiEvaluateBusy(true)

    try {
      const body = await evaluateResponseAI(caseId)

      setAiEvaluation(body.evaluation)

      await refreshCaseData(caseId)

      setNotice(
        body.followup && body.followup.overflowed_to_human_intervention
          ? 'Maximum follow-up attempts reached. Human intervention required.'
          : `AI evaluation applied: ${body.evaluation.outcome}.`,
      )
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setAiEvaluateBusy(false)
    }
  }

  async function handlePrepareFollowup() {
    if (!caseId) return

    setError(null)
    setNotice(null)
    setPrepareFollowupBusy(true)

    try {
      await prepareFollowup(caseId)

      await refreshCaseData(caseId)

      setNotice('Follow-up action prepared and awaiting approval.')
    } catch (err) {
      setError(friendlyMessage(err))
    } finally {
      setPrepareFollowupBusy(false)
    }
  }

  function startOver() {
    setSessionId(null)
    setCaseId(null)
    setMessages([])
    setCaseData(null)
    setDocuments([])
    setActions([])
    setResponses([])
    setAiEvaluation(null)
    setFollowupStatus(null)
    setHistory([])
    setHistoryLoading(false)
    setHistoryError(null)
    setError(null)
    setNotice(null)
    setScreen('start')

    navigate('/')
  }

  if (screen === 'start') {
    return (
      <main className="app">
        <StartScreen
          onStart={startCase}
          busy={chatBusy}
          error={error}
        />
      </main>
    )
  }

  const status = caseData?.status || 'new'

  const statusLabel =
    status === 'awaiting_response'
      ? 'Awaiting response'
      : status === 'response_received'
        ? 'Response received'
        : status === 'resolved'
          ? 'Resolved'
          : status === 'needs_follow_up'
            ? 'Follow-up needed'
            : status === 'human_intervention'
              ? 'Human intervention required'
              : status === 'in_progress'
                ? 'In progress'
                : 'In progress'

  const category =
    caseData?.category
      ? String(caseData.category).toUpperCase()
      : 'CONSUMER DISPUTE'

  const caseTitle = caseData?.title || 'Your dispute'

  const caseSubtitle =
    caseData?.product || caseData?.seller
      ? [caseData?.product, caseData?.seller]
          .filter(Boolean)
          .join(' · ')
      : 'RESOLVE is helping you work toward a resolution.'

  return (
    <main className="case-workspace-page">
      <div className="case-workspace-container">

        <div className="case-workspace-back">
          <Link to="/cases" className="case-back-link">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M19 12H5"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
              <path
                d="m11 18-6-6 6-6"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>My Cases</span>
          </Link>
        </div>

        <header className="case-workspace-header">
          <div className="case-workspace-header-main">
            <span className="case-workspace-category">
              {category}
            </span>

            <h1>{caseTitle}</h1>

            <p className="case-workspace-subtitle">
              {caseSubtitle}
            </p>
          </div>

          <div
            className={`case-workspace-status status-${status}`}
            aria-label={`Case status: ${statusLabel}`}
          >
            <span className="case-workspace-status-dot" />
            <span>{statusLabel}</span>
          </div>
        </header>

        {error ? (
          <p
            className="error banner"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {notice ? (
          <p className="notice banner">
            {notice}
          </p>
        ) : null}

        <div className="case-workspace-layout">

          <div className="case-workspace-main">

            <ChatPanel
              messages={messages}
              onSend={sendMessage}
              busy={chatBusy}
            />

            <CasePanel
              caseData={caseData}
              documents={documents}
              actions={actions}
              onUpload={handleUpload}
              onDecide={handleDecide}
              onExecute={handleExecute}
              onRecordResponse={handleRecordResponse}
              onEvaluate={handleEvaluate}
              onEvaluateAI={handleEvaluateAI}
              onPrepareFollowup={handlePrepareFollowup}
              responses={responses}
              uploadBusy={uploadBusy}
              decideBusy={decideBusy}
              executeBusy={executeBusy}
              responseBusy={responseBusy}
              evaluateBusy={evaluateBusy}
              aiEvaluateBusy={aiEvaluateBusy}
              aiEvaluation={aiEvaluation}
              followupStatus={followupStatus}
              prepareFollowupBusy={prepareFollowupBusy}
              executionConfig={executionConfig}
              history={history}
              historyLoading={historyLoading}
              historyError={historyError}
              onRetryHistory={refreshHistory}
            />

          </div>

          <aside className="case-workspace-sidebar">

            <section className="case-summary-card">
              <span className="section-eyebrow">
                AT A GLANCE
              </span>

              <h2>Case overview</h2>

              <div className="case-summary-list">

                {caseData?.product ? (
                  <div className="case-summary-item">
                    <span>Product</span>
                    <strong>{caseData.product}</strong>
                  </div>
                ) : null}

                {caseData?.seller ? (
                  <div className="case-summary-item">
                    <span>Seller</span>
                    <strong>{caseData.seller}</strong>
                  </div>
                ) : null}

                {caseData?.category ? (
                  <div className="case-summary-item">
                    <span>Category</span>
                    <strong>{caseData.category}</strong>
                  </div>
                ) : null}

                {caseData?.amount ? (
                  <div className="case-summary-item">
                    <span>Amount</span>
                    <strong>{caseData.amount}</strong>
                  </div>
                ) : null}

                {caseData?.purchase_date ? (
                  <div className="case-summary-item">
                    <span>Purchase date</span>
                    <strong>{caseData.purchase_date}</strong>
                  </div>
                ) : null}

                {!caseData?.product &&
                !caseData?.seller &&
                !caseData?.category &&
                !caseData?.amount &&
                !caseData?.purchase_date ? (
                  <p className="case-summary-empty">
                    Case details will appear here as RESOLVE learns more.
                  </p>
                ) : null}

              </div>
            </section>

            <section className="control-card">
              <div className="control-card-icon">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M12 3 5 6v5c0 4.6 2.8 8.5 7 10 4.2-1.5 7-5.4 7-10V6l-7-3Z"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinejoin="round"
                  />
                  <path
                    d="m9 12 2 2 4-4"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>

              <div>
                <strong>You&apos;re in control</strong>

                <p>
                  RESOLVE can recommend actions, but nothing is
                  sent without your approval.
                </p>
              </div>
            </section>

          </aside>

        </div>
      </div>
    </main>
  )
}

export default WorkflowScreen