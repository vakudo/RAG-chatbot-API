<script setup>
import { nextTick, ref } from 'vue'
import { streamChat } from '../api'

const props = defineProps({
  docId: { type: String, default: null },
  model: { type: String, default: null },
})

const messages = ref([])
const input = ref('')
const busy = ref(false)
const error = ref(null)
const scroller = ref(null)

async function scrollDown() {
  await nextTick()
  scroller.value?.scrollTo({ top: scroller.value.scrollHeight })
}

async function send() {
  const question = input.value.trim()
  if (!question || busy.value) return
  input.value = ''
  error.value = null
  busy.value = true

  const history = messages.value.map(({ role, content }) => ({ role, content }))
  messages.value.push({ role: 'user', content: question })
  messages.value.push({ role: 'assistant', content: '' })
  const last = messages.value[messages.value.length - 1]
  await scrollDown()

  try {
    for await (const chunk of streamChat({
      question,
      docId: props.docId,
      history,
      model: props.model,
    })) {
      last.content += chunk
      await scrollDown()
    }
  } catch (e) {
    error.value = e.message
    if (!last.content) messages.value.pop()
  } finally {
    busy.value = false
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
          {{ msg.content }}<span v-if="msg.role === 'assistant' && busy && i === messages.length - 1" class="cursor">▍</span>
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
      <button type="submit" :disabled="busy || !input.trim()">Send</button>
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

.row.user .bubble {
  background: var(--accent);
  color: #fff;
  border: none;
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

.composer button:disabled {
  opacity: 0.5;
  cursor: default;
}

.error {
  color: var(--error);
  font-size: 13px;
}
</style>
