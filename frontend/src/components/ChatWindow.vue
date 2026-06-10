<script setup>
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { nextTick, ref, watch } from 'vue'
import {
  createConversation,
  getChunk,
  getConversationMessages,
  streamChat,
  transcribeAudio,
} from '../api'

const props = defineProps({
  docIds: { type: Array, default: null },
  model: { type: String, default: null },
  conversationId: { type: String, default: null },
  suggestions: { type: Array, default: () => [] },
})
const emit = defineEmits(['conversation-created'])

const sourceView = ref(null) // { filename, chunk_index, text } | null

async function openSource(s) {
  sourceView.value = { filename: s.filename, chunk_index: s.chunk_index, text: '…' }
  try {
    const chunk = await getChunk(s.doc_id, s.chunk_index)
    sourceView.value = { ...sourceView.value, text: chunk.text }
  } catch {
    sourceView.value = { ...sourceView.value, text: s.snippet }
  }
}

async function copyMessage(msg) {
  try {
    await navigator.clipboard.writeText(msg.content)
  } catch {}
}

function regenerate() {
  if (busy.value || messages.value.length < 2) return
  const last = messages.value[messages.value.length - 1]
  if (last.role !== 'assistant') return
  const userMsg = messages.value[messages.value.length - 2]
  if (userMsg?.role !== 'user') return
  messages.value.pop()
  ask(userMsg.content, { skipUserPush: true, saveQuestion: false })
}

const messages = ref([])
const input = ref('')
const busy = ref(false)
const error = ref(null)
const scroller = ref(null)
let controller = null
// conversation we created ourselves on first send; switching to it must not
// abort the in-flight stream or clear the messages on screen
let selfCreatedCid = null

function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text, { breaks: true }))
}

watch(
  () => props.conversationId,
  async (cid) => {
    if (cid && cid === selfCreatedCid) return
    if (busy.value) stop()
    error.value = null
    if (!cid) {
      messages.value = []
      return
    }
    try {
      messages.value = await getConversationMessages(cid)
      await scrollDown()
    } catch {
      messages.value = []
    }
  },
  { immediate: true },
)

async function scrollDown() {
  await nextTick()
  scroller.value?.scrollTo({ top: scroller.value.scrollHeight })
}

function stop() {
  controller?.abort()
}

async function ask(question, { skipUserPush = false, saveQuestion = true } = {}) {
  if (!question || busy.value) return
  error.value = null
  busy.value = true
  controller = new AbortController()

  let cid = props.conversationId
  if (!cid) {
    try {
      cid = (await createConversation()).id
      selfCreatedCid = cid
      emit('conversation-created', cid)
    } catch {
      cid = null // chat still works without persistence
    }
  }

  const history = messages.value
    .slice(0, skipUserPush ? -1 : undefined)
    .map(({ role, content }) => ({ role, content }))
  if (!skipUserPush) messages.value.push({ role: 'user', content: question })
  messages.value.push({ role: 'assistant', content: '', sources: [] })
  const last = messages.value[messages.value.length - 1]
  await scrollDown()

  try {
    for await (const event of streamChat({
      question,
      docIds: props.docIds,
      history,
      model: props.model,
      conversationId: cid,
      saveQuestion,
      signal: controller.signal,
    })) {
      if (event.sources) last.sources = event.sources
      if (event.content) last.content += event.content
      await scrollDown()
    }
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message
    if (!last.content) messages.value.splice(messages.value.length - 1, 1)
  } finally {
    busy.value = false
    controller = null
    // the watcher has already skipped the self-initiated switch by now;
    // re-opening this conversation later must load it from the server
    selfCreatedCid = null
  }
}

async function send() {
  const question = input.value.trim()
  if (!question) return
  input.value = ''
  await ask(question)
}

// Voice input: Web Speech API where available (Chrome/Edge), otherwise
// record with MediaRecorder and transcribe server-side (Whisper).
const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition
const voiceSupported = Boolean(
  SpeechRecognition || (navigator.mediaDevices && window.MediaRecorder),
)
const listening = ref(false)
const transcribing = ref(false)
let recognition = null
let recorder = null

function startNativeRecognition() {
  recognition = new SpeechRecognition()
  recognition.lang = navigator.language || 'en-US'
  recognition.interimResults = true
  recognition.onresult = (e) => {
    input.value = [...e.results].map((r) => r[0].transcript).join('')
  }
  recognition.onend = () => {
    listening.value = false
  }
  recognition.onerror = () => {
    listening.value = false
  }
  listening.value = true
  recognition.start()
}

async function startRecorderFallback() {
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    error.value = 'Microphone access denied'
    return
  }
  const chunks = []
  recorder = new MediaRecorder(stream)
  recorder.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data)
  }
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop())
    listening.value = false
    if (!chunks.length) return
    transcribing.value = true
    try {
      const { text } = await transcribeAudio(
        new Blob(chunks, { type: recorder.mimeType }),
      )
      if (text) input.value = input.value ? `${input.value} ${text}` : text
    } catch (e) {
      error.value = e.message
    } finally {
      transcribing.value = false
    }
  }
  listening.value = true
  recorder.start()
}

function toggleVoice() {
  if (listening.value) {
    recognition?.stop()
    if (recorder?.state === 'recording') recorder.stop()
    return
  }
  if (transcribing.value) return
  if (SpeechRecognition) startNativeRecognition()
  else startRecorderFallback()
}
</script>

<template>
  <div class="chat">
    <div ref="scroller" class="messages">
      <div v-if="!messages.length" class="empty">
        <p>Upload a document and ask a question about it.</p>
        <div v-if="suggestions.length" class="suggestions">
          <button
            v-for="q in suggestions"
            :key="q"
            class="suggestion"
            @click="ask(q)"
          >
            {{ q }}
          </button>
        </div>
      </div>
      <div v-for="(msg, i) in messages" :key="i" class="row" :class="msg.role">
        <div class="bubble">
          <div
            v-if="msg.role === 'assistant'"
            class="md"
            v-html="renderMarkdown(msg.content)"
          ></div>
          <template v-else>{{ msg.content }}</template>
          <span
            v-if="msg.role === 'assistant' && busy && i === messages.length - 1"
            class="cursor"
            >▍</span
          >
          <div v-if="msg.sources?.length && msg.content" class="sources">
            <button
              v-for="s in msg.sources"
              :key="`${s.doc_id}-${s.chunk_index}`"
              class="source-chip"
              :title="s.snippet"
              @click="openSource(s)"
            >
              📄 {{ s.filename }} · #{{ s.chunk_index }}
            </button>
          </div>
          <div
            v-if="msg.role === 'assistant' && msg.content && !(busy && i === messages.length - 1)"
            class="actions"
          >
            <button title="Copy answer" @click="copyMessage(msg)">📋</button>
            <button
              v-if="i === messages.length - 1"
              title="Regenerate answer"
              @click="regenerate"
            >
              🔄
            </button>
          </div>
        </div>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </div>

    <form class="composer" @submit.prevent="send">
      <input
        v-model="input"
        :disabled="busy"
        placeholder="Ask a question about your documents…"
        autofocus
      />
      <button
        v-if="voiceSupported && !busy"
        type="button"
        class="mic"
        :class="{ listening }"
        :disabled="transcribing"
        :title="transcribing ? 'Transcribing…' : listening ? 'Stop recording' : 'Voice input'"
        @click="toggleVoice"
      >
        {{ transcribing ? '⏳' : listening ? '⏹' : '🎤' }}
      </button>
      <button v-if="busy" type="button" class="stop" @click="stop">⬛ Stop</button>
      <button v-else type="submit" :disabled="!input.trim()">Send</button>
    </form>

    <div v-if="sourceView" class="modal-backdrop" @click.self="sourceView = null">
      <div class="modal">
        <div class="modal-header">
          <strong>📄 {{ sourceView.filename }} · chunk #{{ sourceView.chunk_index }}</strong>
          <button class="modal-close" @click="sourceView = null">✕</button>
        </div>
        <pre class="modal-body">{{ sourceView.text }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty {
  margin: auto;
  color: var(--muted);
  text-align: center;
}

.suggestions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.suggestion {
  padding: 8px 14px;
  font-size: 13px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  text-align: left;
}

.suggestion:hover {
  border-color: var(--accent);
}

.actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
}

.actions button {
  background: none;
  border: none;
  padding: 2px 4px;
  font-size: 13px;
  opacity: 0.55;
}

.actions button:hover {
  opacity: 1;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.modal {
  width: min(640px, 90vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.modal-close {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 14px;
}

.modal-body {
  margin: 0;
  padding: 16px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.row {
  display: flex;
}

.row.user {
  justify-content: flex-end;
}

.bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--panel);
  border: 1px solid var(--border);
}

.row.assistant .bubble {
  white-space: normal;
}

.md :first-child {
  margin-top: 0;
}

.md :last-child {
  margin-bottom: 0;
}

.md :deep(pre) {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  overflow-x: auto;
}

.md :deep(code) {
  background: var(--bg);
  border-radius: 4px;
  padding: 1px 4px;
  font-size: 13px;
}

.md :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
}

.md :deep(th),
.md :deep(td) {
  border: 1px solid var(--border);
  padding: 4px 10px;
}

.row.user .bubble {
  background: var(--accent);
  color: #fff;
  border: none;
}

.sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.source-chip {
  font-size: 11px;
  color: var(--muted);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 10px;
  cursor: help;
}

.cursor {
  animation: blink 1s step-start infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.composer {
  display: flex;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  background: var(--panel);
}

.composer input {
  flex: 1;
  padding: 10px 14px;
  font: inherit;
  border: 1px solid var(--border);
  border-radius: 8px;
  outline: none;
  background: var(--bg);
  color: var(--text);
}

.composer input::placeholder {
  color: var(--muted);
}

.composer input:focus {
  border-color: var(--accent);
}

.composer button {
  padding: 10px 20px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 8px;
}

.composer button.stop {
  background: var(--error);
}

.composer button.mic {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 10px 12px;
}

.composer button.mic.listening {
  border-color: var(--error);
  animation: blink 1.2s step-start infinite;
}

.composer button:disabled {
  opacity: 0.5;
  cursor: default;
}

.error {
  color: var(--error);
  font-size: 13px;
}
</style>
