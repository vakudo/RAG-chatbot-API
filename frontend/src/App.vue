<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getDocuments, getModels, uploadFile } from './api'
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
const selectedDocId = ref(null)
const models = ref([])
const selectedModel = ref(null)
const backendDown = ref(false)

const fileInput = ref(null)
const uploading = ref(false)
const uploadMessage = ref(null)
const uploadError = ref(null)

const docOptions = computed(() => [
  { id: null, label: 'All documents' },
  ...docs.value.map((d) => ({ id: d.doc_id, label: `${d.filename} (${d.chunks_count} chunks)` })),
])

const currentModel = computed(
  () => models.value.find((m) => m.name === selectedModel.value) ?? null,
)

async function refresh() {
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
  const file = fileInput.value?.files?.[0]
  if (!file) return
  uploading.value = true
  uploadMessage.value = null
  uploadError.value = null
  try {
    const result = await uploadFile(file)
    uploadMessage.value = `Ingested ${result.filename} (${result.chunks_count} chunks)`
    fileInput.value.value = ''
    await refresh()
    selectedDocId.value = result.doc_id
  } catch (e) {
    uploadError.value = e.message
  } finally {
    uploading.value = false
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
            accept=".pdf,.txt"
            :disabled="uploading"
            @change="onUpload"
          />
          {{ uploading ? 'Ingesting…' : '＋ Upload PDF or TXT' }}
        </label>
        <p v-if="uploadMessage" class="ok">{{ uploadMessage }}</p>
        <p v-if="uploadError" class="warn">{{ uploadError }}</p>

        <select v-model="selectedDocId">
          <option v-for="opt in docOptions" :key="opt.id ?? 'all'" :value="opt.id">
            {{ opt.label }}
          </option>
        </select>
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
      <ChatWindow :doc-id="selectedDocId" :model="selectedModel" />
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

select {
  width: 100%;
  margin-top: 10px;
  padding: 8px;
  font: inherit;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
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
