<script setup>
import { ref } from 'vue'
import { streamPull } from '../api'
import { logoFor } from '../logos'

const props = defineProps({
  models: { type: Array, required: true },
  selected: { type: String, default: null },
})
const emit = defineEmits(['select', 'installed'])

const pulling = ref(null) // model name being downloaded
const progress = ref(0)
const status = ref('')
const error = ref(null)

async function download(model) {
  pulling.value = model.name
  progress.value = 0
  status.value = 'Starting…'
  error.value = null
  try {
    for await (const line of streamPull(model.name)) {
      if (line.error) throw new Error(line.error)
      status.value = line.status ?? ''
      if (line.total && line.completed) {
        progress.value = Math.min(line.completed / line.total, 1)
      }
    }
    emit('installed', model.name)
  } catch (e) {
    error.value = e.message
  } finally {
    pulling.value = null
  }
}
</script>

<template>
  <div class="picker">
    <div
      v-for="model in models"
      :key="model.name"
      class="card"
      :class="{ active: model.name === selected, disabled: !model.installed }"
      @click="model.installed && emit('select', model.name)"
    >
      <img class="logo" :src="logoFor(model)" :alt="model.vendor" loading="lazy" />
      <div class="info">
        <div class="name">{{ model.display_name }}</div>
        <div class="meta">
          {{ model.vendor }}
          <span v-if="model.size"> · {{ model.size }}</span>
        </div>
        <div v-if="model.description" class="desc">{{ model.description }}</div>

        <div v-if="pulling === model.name" class="progress">
          <div class="bar">
            <div class="fill" :style="{ width: progress * 100 + '%' }"></div>
          </div>
          <span class="status">{{ status }} {{ Math.round(progress * 100) }}%</span>
        </div>
        <button
          v-else-if="!model.installed"
          class="download"
          :disabled="pulling !== null"
          @click.stop="download(model)"
        >
          ⬇ Download {{ model.size }}
        </button>
      </div>
      <span v-if="model.installed" class="badge" :class="{ current: model.name === selected }">
        {{ model.name === selected ? 'selected' : 'installed' }}
      </span>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.card:hover:not(.disabled) {
  border-color: var(--accent);
}

.card.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.card.disabled {
  cursor: default;
}

.logo {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  margin-top: 2px;
}

.info {
  flex: 1;
  min-width: 0;
}

.name {
  font-weight: 600;
  font-size: 14px;
}

.meta {
  font-size: 12px;
  color: var(--muted);
}

.desc {
  font-size: 12px;
  color: var(--muted);
  margin-top: 4px;
}

.badge {
  font-size: 11px;
  color: var(--green);
  border: 1px solid currentColor;
  border-radius: 999px;
  padding: 1px 8px;
  flex-shrink: 0;
}

.badge.current {
  color: var(--accent);
  background: var(--accent-soft);
}

.download {
  margin-top: 8px;
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--accent);
  color: var(--accent);
  background: none;
  border-radius: 6px;
}

.download:hover:not(:disabled) {
  background: var(--accent-soft);
}

.download:disabled {
  opacity: 0.5;
  cursor: default;
}

.progress {
  margin-top: 8px;
}

.bar {
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}

.fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.2s;
}

.status {
  font-size: 11px;
  color: var(--muted);
}

.error {
  color: var(--error);
  font-size: 12px;
}
</style>
