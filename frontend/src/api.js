export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function readError(response) {
  try {
    const body = await response.json()
    return body.detail || `Request failed (${response.status})`
  } catch {
    return `Request failed (${response.status})`
  }
}

async function handle(response) {
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status)
  }
  return response.json()
}

export async function postChat(message, sessionId) {
  return handle(
    await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sessionId ? { session_id: sessionId, message } : { message }),
    }),
  )
}

export async function getCase(caseId) {
  return handle(await fetch(`/api/cases/${encodeURIComponent(caseId)}`))
}

export async function getActions(caseId) {
  return handle(await fetch(`/api/cases/${encodeURIComponent(caseId)}/actions`))
}

export async function uploadDocument(caseId, file) {
  const form = new FormData()
  form.append('file', file)
  return handle(
    await fetch(`/api/cases/${encodeURIComponent(caseId)}/documents`, {
      method: 'POST',
      body: form,
    }),
  )
}

export async function decideAction(actionId, decision) {
  return handle(
    await fetch(`/api/actions/${encodeURIComponent(actionId)}/${decision}`, {
      method: 'POST',
    }),
  )
}

export async function executeAction(actionId) {
  return handle(
    await fetch(`/api/actions/${encodeURIComponent(actionId)}/execute`, {
      method: 'POST',
    }),
  )
}