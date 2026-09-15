export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

let unauthorizedHandler = null

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
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
    if (response.status === 401 && unauthorizedHandler) {
      unauthorizedHandler()
    }
    throw new ApiError(await readError(response), response.status)
  }
  return response.json()
}

async function request(path, options = {}) {
  const init = {
    credentials: 'include',
    referrerPolicy: 'strict-origin-when-cross-origin',
    headers: {},
    ...options,
  }
  if (options.body && !(options.body instanceof FormData) && typeof options.body !== 'string') {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(options.body)
  }
  return handle(await fetch(path, init))
}

export async function signup(payload) {
  return request('/api/auth/signup', { method: 'POST', body: payload })
}

export async function login(payload) {
  return request('/api/auth/login', { method: 'POST', body: payload })
}

export async function logout() {
  return request('/api/auth/logout', { method: 'POST' })
}

export async function getCurrentUser() {
  const response = await fetch('/api/auth/me', { credentials: 'include' })
  if (response.status === 401) {
    throw new ApiError(await readError(response), 401)
  }
  return handle(response)
}

export async function postChat(message, sessionId) {
  return request('/api/agent/chat', {
    method: 'POST',
    body: sessionId ? { session_id: sessionId, message } : { message },
  })
}

export async function getCase(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}`)
}

export async function listMyCases() {
  return request('/api/cases')
}

export async function getActions(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/actions`)
}

export async function uploadDocument(caseId, file) {
  const form = new FormData()
  form.append('file', file)
  return request(`/api/cases/${encodeURIComponent(caseId)}/documents`, {
    method: 'POST',
    body: form,
  })
}

export async function decideAction(actionId, decision) {
  return request(`/api/actions/${encodeURIComponent(actionId)}/${decision}`, {
    method: 'POST',
  })
}

export async function executeAction(actionId) {
  return request(`/api/actions/${encodeURIComponent(actionId)}/execute`, {
    method: 'POST',
  })
}

export async function recordResponse(caseId, body) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/responses`, {
    method: 'POST',
    body,
  })
}

export async function getResponses(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/responses`)
}

export async function evaluateCase(caseId, outcome) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/evaluate`, {
    method: 'POST',
    body: { outcome },
  })
}

export async function evaluateResponseAI(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/evaluate-response`, {
    method: 'POST',
  })
}

export async function getFollowupStatus(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/followup-status`)
}

export async function getHistory(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/history`)
}

export async function prepareFollowup(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/prepare-followup`, {
    method: 'POST',
  })
}

export async function getExecutionConfig() {
  return request('/api/config/execution')
}