<script setup>
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { nextTick, ref, watch } from 'vue'
import { createConversation, getConversationMessages, streamChat } from '../api'

const props = defineProps({
  docIds: { type: Array, default: null },
  model: { type: String, default: null },
  conversationId: { type: String, default: null },
})
const emit = defineEmits(['conversation-created'])

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

async function send() {
  const question = input.value.trim()
  if (!question || busy.value) return
  input.value = ''
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

  const history = messages.value.map(({ role, content }) => ({ role, content }))
  messages.value.push({ role: 'user', content: question })
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
  }
}
</script>

<template>
  <div class="chat">
    <div ref="scroller" class="messages">
      <div v-if="!messages.length" class="empty">
        Upload a document and ask a question about it.
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
            <span
              v-for="s in msg.sources"
              :key="`${s.doc_id}-${s.chunk_index}`"
              class="source-chip"
              :title="s.snippet"
            >
              📄 {{ s.filename }} · #{{ s.chunk_index }}
            </span>
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
      <button v-if="busy" type="button" class="stop" @click="stop">⬛ Stop</button>
      <button v-else type="submit" :disabled="!input.trim()">Send</button>
    </form>
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

.composer button:disabled {
  opacity: 0.5;
  cursor: default;
}

.error {
  color: var(--error);
  font-size: 13px;
}
</style>
