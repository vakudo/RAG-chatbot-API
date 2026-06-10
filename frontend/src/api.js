// dev: Vite on 5173 talks to the backend on 8000; production build is
// served by FastAPI itself, so the API is same-origin
export const API = import.meta.env.DEV ? 'http://localhost:8000' : ''

function apiFetch(path, options = {}) {
  const headers = { ...(options.headers ?? {}) }
  const token = localStorage.getItem('api_token')
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch(`${API}${path}`, { ...options, headers })
}

export async function getDocuments() {
  const resp = await apiFetch(`/documents`)
  if (!resp.ok) throw new Error(`GET /documents failed: ${resp.status}`)
  return resp.json()
}

export async function getModels() {
  const resp = await apiFetch(`/models`)
  if (!resp.ok) throw new Error(`GET /models failed: ${resp.status}`)
  return resp.json()
}

export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const resp = await apiFetch(`/upload`, { method: 'POST', body: form })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail ?? `Upload failed: ${resp.status}`)
  }
  return resp.json()
}

export async function deleteDocument(docId) {
  const resp = await apiFetch(`/documents/${docId}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`DELETE /documents failed: ${resp.status}`)
  return resp.json()
}

export async function uploadUrl(url) {
  const resp = await apiFetch(`/upload-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail ?? `URL upload failed: ${resp.status}`)
  }
  return resp.json()
}

export async function getChunk(docId, chunkIndex) {
  const resp = await apiFetch(`/chunks/${docId}/${chunkIndex}`)
  if (!resp.ok) throw new Error(`GET /chunks failed: ${resp.status}`)
  return resp.json()
}

export async function suggestQuestions(docId) {
  const resp = await apiFetch(`/documents/${docId}/suggest`, { method: 'POST' })
  if (!resp.ok) throw new Error(`POST /suggest failed: ${resp.status}`)
  return resp.json()
}

export async function transcribeAudio(blob) {
  const form = new FormData()
  form.append('file', blob, 'voice.webm')
  const resp = await apiFetch(`/transcribe`, { method: 'POST', body: form })
  if (!resp.ok) throw new Error(`POST /transcribe failed: ${resp.status}`)
  return resp.json()
}

export async function listConversations() {
  const resp = await apiFetch(`/conversations`)
  if (!resp.ok) throw new Error(`GET /conversations failed: ${resp.status}`)
  return resp.json()
}

export async function createConversation() {
  const resp = await apiFetch(`/conversations`, { method: 'POST' })
  if (!resp.ok) throw new Error(`POST /conversations failed: ${resp.status}`)
  return resp.json()
}

export async function getConversationMessages(cid) {
  const resp = await apiFetch(`/conversations/${cid}/messages`)
  if (!resp.ok) throw new Error(`GET messages failed: ${resp.status}`)
  return resp.json()
}

export async function renameConversation(cid, title) {
  const resp = await apiFetch(`/conversations/${cid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!resp.ok) throw new Error(`PATCH /conversations failed: ${resp.status}`)
  return resp.json()
}

export async function deleteConversation(cid) {
  const resp = await apiFetch(`/conversations/${cid}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`DELETE /conversations failed: ${resp.status}`)
  return resp.json()
}

/**
 * Async generator over SSE `data:` payloads of POST /chat.
 * Yields `{ sources: [...] }` once, then `{ content: "..." }` chunks.
 */
export async function* streamChat({
  question,
  docIds,
  history,
  model,
  conversationId,
  saveQuestion = true,
  signal,
}) {
  const resp = await apiFetch(`/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      doc_ids: docIds,
      history,
      model,
      conversation_id: conversationId,
      save_question: saveQuestion,
    }),
    signal,
  })
  if (!resp.ok) throw new Error(`POST /chat failed: ${resp.status}`)

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop()
    for (const event of events) {
      const line = event.trim()
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (payload === '[DONE]') return
      yield JSON.parse(payload)
    }
  }
}

/** Async generator over NDJSON progress lines of POST /models/pull. */
export async function* streamPull(model) {
  const resp = await apiFetch(`/models/pull`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  })
  if (!resp.ok) throw new Error(`POST /models/pull failed: ${resp.status}`)

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (line.trim()) yield JSON.parse(line)
    }
  }
}
