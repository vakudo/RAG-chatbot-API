<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  deleteConversation,
  deleteDocument,
  getDocuments,
  getModels,
  getConversationMessages,
  listConversations,
  renameConversation,
  suggestQuestions,
  uploadFile,
  uploadUrl,
} from './api'
import { logoFor } from './logos'
import ChatWindow from './components/ChatWindow.vue'
import ModelPicker from './components/ModelPicker.vue'

const theme = ref(
  localStorage.getItem('theme') ??
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
)
watch(
  theme,
  (t) => {
    document.documentElement.dataset.theme = t
    localStorage.setItem('theme', t)
  },
  { immediate: true },
)

const modelMenuOpen = ref(false)

const docs = ref([])
const selectedDocIds = ref([]) // empty = search across all documents
const models = ref([])
const selectedModel = ref(null)
const backendDown = ref(false)

const chats = ref([])
const activeChatId = ref(null)
const chatFilter = ref('')

const filteredChats = computed(() => {
  const q = chatFilter.value.trim().toLowerCase()
  if (!q) return chats.value
  return chats.value.filter((c) => c.title.toLowerCase().includes(q))
})

async function onRenameChat(chat) {
  const title = window.prompt('Chat name:', chat.title)
  if (!title?.trim() || title === chat.title) return
  try {
    await renameConversation(chat.id, title.trim())
    await refreshChats()
  } catch (e) {
    uploadError.value = e.message
  }
}

async function onExportChat(chat) {
  try {
    const msgs = await getConversationMessages(chat.id)
    const md = [
      `# ${chat.title}`,
      '',
      ...msgs.flatMap((m) => [
        `**${m.role === 'user' ? 'You' : 'Assistant'}:**`,
        '',
        m.content,
        '',
      ]),
    ].join('\n')
    const blob = new Blob([md], { type: 'text/markdown' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${chat.title.replace(/[^\w\s-]/g, '').slice(0, 40) || 'chat'}.md`
    a.click()
    URL.revokeObjectURL(a.href)
  } catch (e) {
    uploadError.value = e.message
  }
}

const fileInput = ref(null)
const uploading = ref(false)
const uploadMessage = ref(null)
const uploadError = ref(null)
const suggestions = ref([])

async function loadSuggestions(docId) {
  try {
    suggestions.value = (await suggestQuestions(docId)).questions
  } catch {
    suggestions.value = []
  }
}

const currentModel = computed(
  () => models.value.find((m) => m.name === selectedModel.value) ?? null,
)

async function refreshChats() {
  try {
    chats.value = await listConversations()
  } catch {
    chats.value = []
  }
}

async function onNewChat() {
  activeChatId.value = null
}

async function onDeleteChat(cid) {
  try {
    await deleteConversation(cid)
    if (activeChatId.value === cid) activeChatId.value = null
    await refreshChats()
  } catch (e) {
    uploadError.value = e.message
  }
}

function onConversationCreated(cid) {
  activeChatId.value = cid
  refreshChats()
}

async function refresh() {
  refreshChats()
  try {
    docs.value = await getDocuments()
    const info = await getModels()
    models.value = info.models
    if (!selectedModel.value) {
      const fallback = models.value.find((m) => m.installed)
      const preferred = models.value.find((m) => m.name === info.default && m.installed)
      selectedModel.value = (preferred ?? fallback)?.name ?? null
    }
    backendDown.value = false
  } catch {
    backendDown.value = true
  }
}

async function onUpload() {
  const files = [...(fileInput.value?.files ?? [])]
  if (!files.length) return
  uploading.value = true
  uploadMessage.value = null
  uploadError.value = null
  let lastDocId = null
  const done = []
  try {
    for (const file of files) {
      const result = await uploadFile(file)
      done.push(`${result.filename} (${result.chunks_count})`)
      lastDocId = result.doc_id
      uploadMessage.value = `Ingested ${done.length}/${files.length}: ${done.join(', ')}`
    }
    fileInput.value.value = ''
    await refresh()
    if (lastDocId) loadSuggestions(lastDocId)
  } catch (e) {
    uploadError.value = e.message
  } finally {
    uploading.value = false
  }
}

const urlInput = ref('')

async function onUploadUrl() {
  const url = urlInput.value.trim()
  if (!url) return
  uploading.value = true
  uploadMessage.value = null
  uploadError.value = null
  try {
    const result = await uploadUrl(url)
    uploadMessage.value = `Ingested ${result.filename} (${result.chunks_count} chunks)`
    urlInput.value = ''
    await refresh()
    loadSuggestions(result.doc_id)
  } catch (e) {
    uploadError.value = e.message
  } finally {
    uploading.value = false
  }
}

async function onDeleteDoc(docId) {
  try {
    await deleteDocument(docId)
    selectedDocIds.value = selectedDocIds.value.filter((id) => id !== docId)
    await refresh()
  } catch (e) {
    uploadError.value = e.message
  }
}

function onModelSelect(name) {
  selectedModel.value = name
  modelMenuOpen.value = false
}

function onModelInstalled(name) {
  refresh().then(() => {
    selectedModel.value = name
  })
}

onMounted(refresh)
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="header">
        <h1>📄 RAG Chatbot</h1>
        <button
          class="theme-toggle"
          :title="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
          @click="theme = theme === 'dark' ? 'light' : 'dark'"
        >
          {{ theme === 'dark' ? '☀️' : '🌙' }}
        </button>
      </div>

      <p v-if="backendDown" class="warn">
        Backend is not reachable at http://localhost:8000
      </p>

      <section>
        <h2>Document</h2>
        <label class="upload" :class="{ disabled: uploading }">
          <input
            ref="fileInput"
            type="file"
            multiple
            accept=".pdf,.txt,.md,.csv,.docx,.xlsx,.xlsm,.html,.htm"
            :disabled="uploading"
            @change="onUpload"
          />
          {{ uploading ? 'Ingesting…' : '＋ Upload documents' }}
        </label>

        <form class="url-form" @submit.prevent="onUploadUrl">
          <input
            v-model="urlInput"
            type="url"
            placeholder="…or paste a URL"
            :disabled="uploading"
          />
          <button type="submit" :disabled="uploading || !urlInput.trim()">Add</button>
        </form>

        <p v-if="uploadMessage" class="ok">{{ uploadMessage }}</p>
        <p v-if="uploadError" class="warn">{{ uploadError }}</p>

        <p class="hint">
          {{ selectedDocIds.length ? `Searching ${selectedDocIds.length} selected` : 'Searching all documents' }}
        </p>

        <ul v-if="docs.length" class="doc-list">
          <li v-for="d in docs" :key="d.doc_id">
            <label class="doc-check">
              <input type="checkbox" :value="d.doc_id" v-model="selectedDocIds" />
              <span class="doc-name" :title="d.filename">{{ d.filename }}</span>
            </label>
            <button class="doc-delete" title="Delete document" @click="onDeleteDoc(d.doc_id)">
              🗑
            </button>
          </li>
        </ul>
      </section>

      <section>
        <div class="chats-header">
          <h2>Chats</h2>
          <button class="new-chat" @click="onNewChat">＋ New</button>
        </div>
        <input
          v-if="chats.length > 3"
          v-model="chatFilter"
          class="chat-search"
          type="search"
          placeholder="Search chats…"
        />
        <ul class="chat-list">
          <li
            v-for="c in filteredChats"
            :key="c.id"
            :class="{ active: c.id === activeChatId }"
            @click="activeChatId = c.id"
            @dblclick="onRenameChat(c)"
          >
            <span class="doc-name" :title="c.title + ' (double-click to rename)'">{{ c.title }}</span>
            <button class="doc-delete" title="Export to Markdown" @click.stop="onExportChat(c)">
              ⬇
            </button>
            <button class="doc-delete" title="Delete chat" @click.stop="onDeleteChat(c.id)">
              🗑
            </button>
          </li>
        </ul>
      </section>

      <section class="models">
        <h2>Model</h2>
        <button class="model-current" @click="modelMenuOpen = !modelMenuOpen">
          <template v-if="currentModel">
            <img class="model-logo" :src="logoFor(currentModel)" :alt="currentModel.vendor" />
            <span class="model-name">{{ currentModel.display_name }}</span>
          </template>
          <span v-else class="model-name">Choose a model…</span>
          <span class="chevron" :class="{ open: modelMenuOpen }">▾</span>
        </button>
        <div v-if="modelMenuOpen" class="model-menu">
          <ModelPicker
            :models="models"
            :selected="selectedModel"
            @select="onModelSelect"
            @installed="onModelInstalled"
          />
        </div>
      </section>
    </aside>

    <main class="main">
      <ChatWindow
        :doc-ids="selectedDocIds.length ? selectedDocIds : null"
        :model="selectedModel"
        :conversation-id="activeChatId"
        :suggestions="suggestions"
        @conversation-created="onConversationCreated"
      />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
}

.sidebar {
  width: 340px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: var(--bg);
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar h1 {
  font-size: 18px;
  margin: 0;
}

.theme-toggle {
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 14px;
}

.theme-toggle:hover {
  border-color: var(--accent);
}

.model-current {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  text-align: left;
}

.model-current:hover {
  border-color: var(--accent);
}

.model-logo {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.model-name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chevron {
  color: var(--muted);
  transition: transform 0.15s;
}

.chevron.open {
  transform: rotate(180deg);
}

.model-menu {
  margin-top: 8px;
}

.sidebar h2 {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin: 0 0 8px;
}

.upload {
  display: block;
  text-align: center;
  padding: 10px;
  border: 1px dashed var(--accent);
  border-radius: 8px;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
}

.upload.disabled {
  opacity: 0.6;
}

.upload input {
  display: none;
}

.hint {
  font-size: 11px;
  color: var(--muted);
  margin: 10px 0 0;
}

.doc-check {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.doc-check input {
  accent-color: var(--accent);
}

.chats-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.chats-header h2 {
  margin: 0;
}

.new-chat {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid var(--accent);
  color: var(--accent);
  background: none;
  border-radius: 6px;
}

.new-chat:hover {
  background: var(--accent-soft);
}

.chat-search {
  width: 100%;
  margin-bottom: 8px;
  padding: 6px 10px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  outline: none;
}

.chat-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
}

.chat-list li:hover {
  border-color: var(--accent);
}

.chat-list li.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.url-form {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.url-form input {
  flex: 1;
  min-width: 0;
  padding: 7px 10px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  outline: none;
}

.url-form input:focus {
  border-color: var(--accent);
}

.url-form button {
  padding: 7px 12px;
  font-size: 12px;
  border: 1px solid var(--accent);
  color: var(--accent);
  background: none;
  border-radius: 8px;
}

.url-form button:disabled {
  opacity: 0.5;
  cursor: default;
}

.doc-list {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.doc-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.doc-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-delete {
  background: none;
  border: none;
  padding: 0;
  opacity: 0.6;
}

.doc-delete:hover {
  opacity: 1;
}

.main {
  flex: 1;
  min-width: 0;
}

.ok {
  color: var(--green);
  font-size: 12px;
  margin: 8px 0 0;
}

.warn {
  color: #dc2626;
  font-size: 12px;
  margin: 8px 0 0;
}
</style>
