export const API = 'http://localhost:8000'

export async function getDocuments() {
  const resp = await fetch(`${API}/documents`)
  if (!resp.ok) throw new Error(`GET /documents failed: ${resp.status}`)
  return resp.json()
}

export async function getModels() {
  const resp = await fetch(`${API}/models`)
  if (!resp.ok) throw new Error(`GET /models failed: ${resp.status}`)
  return resp.json()
}

export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(`${API}/upload`, { method: 'POST', body: form })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail ?? `Upload failed: ${resp.status}`)
  }
  return resp.json()
}

export async function deleteDocument(docId) {
  const resp = await fetch(`${API}/documents/${docId}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`DELETE /documents failed: ${resp.status}`)
  return resp.json()
}

export async function uploadUrl(url) {
  const resp = await fetch(`${API}/upload-url`, {
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

export async function listConversations() {
  const resp = await fetch(`${API}/conversations`)
  if (!resp.ok) throw new Error(`GET /conversations failed: ${resp.status}`)
  return resp.json()
}

export async function createConversation() {
  const resp = await fetch(`${API}/conversations`, { method: 'POST' })
  if (!resp.ok) throw new Error(`POST /conversations failed: ${resp.status}`)
  return resp.json()
}

export async function getConversationMessages(cid) {
  const resp = await fetch(`${API}/conversations/${cid}/messages`)
  if (!resp.ok) throw new Error(`GET messages failed: ${resp.status}`)
  return resp.json()
}

export async function deleteConversation(cid) {
  const resp = await fetch(`${API}/conversations/${cid}`, { method: 'DELETE' })
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
  signal,
}) {
  const resp = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      doc_ids: docIds,
      history,
      model,
      conversation_id: conversationId,
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
  const resp = await fetch(`${API}/models/pull`, {
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
