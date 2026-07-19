<template>
  <section
    class="knowledge-document-pane"
    data-testid="document-grid"
    @dragenter.prevent="$emit('drag-active', true)"
    @dragover.prevent
    @dragleave.prevent="$emit('drag-active', false)"
    @drop.prevent="$emit('drop', $event)"
  >
    <div v-if="!documents.length" class="document-empty">
      <span>{{ t('components.documentGrid.empty') }}</span>
      <strong>{{ t('components.documentGrid.notes') }}</strong>
    </div>
    <div v-else class="document-grid">
      <article
        v-for="item in documents"
        :key="item.id"
        class="document-card"
        :class="{ selected: selectedId === item.id, checked: selectedIds.includes(item.id) }"
      >
        <div class="card-controls">
          <button
            type="button"
            class="check-control"
            role="checkbox"
            :aria-checked="selectedIds.includes(item.id)"
            :aria-label="t('components.documentGrid.select', { name: item.display_name })"
            :data-testid="`document-checkbox-${item.id}`"
            @click="$emit('toggle-selection', item.id)"
          >{{ selectedIds.includes(item.id) ? '✓' : '' }}</button>
          <button
            type="button"
            class="favorite-control"
            :class="{ active: item.favorite }"
            :disabled="favoritePendingIds.includes(item.id)"
            :aria-busy="favoritePendingIds.includes(item.id)"
            :aria-label="t(item.favorite ? 'components.documentGrid.unfavorite' : 'components.documentGrid.favorite', { name: item.display_name })"
            :data-testid="`favorite-document-${item.id}`"
            @click="$emit('toggle-favorite', item.id, !item.favorite)"
          >{{ item.favorite ? '★' : '☆' }}</button>
        </div>
        <button
          type="button"
          class="document-select"
          :aria-label="t('components.documentGrid.view', { name: item.display_name })"
          @click="$emit('select', item.id)"
          @keydown.enter.prevent="$emit('select', item.id)"
          @keydown.space.prevent="$emit('select', item.id)"
        >
          <span class="file-mark">{{ item.extension.replace('.', '').toUpperCase() }}</span>
          <span class="file-copy">
            <strong>{{ item.display_name }}</strong>
            <small>{{ statusLabel(item.status) }} · {{ sizeLabel(item.byte_size) }}</small>
          </span>
        </button>
        <div v-if="item.tags?.length" class="document-tags" :aria-label="t('components.documentGrid.documentTag')">
          <span v-for="tag in item.tags" :key="tag">{{ tag }}</span>
        </div>
        <div v-if="activeJobFor(item.id)" class="import-progress">
          <div
            role="progressbar"
            :aria-label="t('components.documentGrid.importProgressLabel', { name: item.display_name })"
            aria-valuemin="0"
            aria-valuemax="100"
            :aria-valuenow="activeJobFor(item.id)!.progress"
          ><i :style="{ width: `${activeJobFor(item.id)!.progress}%` }" /></div>
          <span>{{ progressLabel(activeJobFor(item.id)!) }}</span>
          <small v-if="activeJobFor(item.id)!.safe_error_code">{{ failureReason(activeJobFor(item.id)!.safe_error_code) }}</small>
          <button type="button" :aria-label="t('components.documentGrid.cancelImport', { name: item.display_name })" @click="cancelJob(activeJobFor(item.id)!.id)">{{ t('common.actions.cancel') }}</button>
        </div>
        <div v-else-if="failedOcrJobFor(item.id)" class="ocr-failure" role="status">
          <span>{{ failedOcrLabel(failedOcrJobFor(item.id)!) }}</span>
          <small>{{ etaLabel(failedOcrJobFor(item.id)!) }} · {{ t('components.documentGrid.failedPages', { pages: failedOcrJobFor(item.id)!.failed_pages.join('、') }) }}</small>
          <small>{{ failureReason(failedOcrJobFor(item.id)!.safe_error_code) }}</small>
          <button type="button" :aria-label="t('components.documentGrid.pageFailure', { name: item.display_name })" @click="retryJob?.(failedOcrJobFor(item.id)!.id)">{{ t('components.documentGrid.retryOcr') }}</button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { KnowledgeDocument, KnowledgeImportJob } from '@/api'
import { KNOWLEDGE_IMPORT_STATUSES } from '@/api/types'
import { useI18n } from 'vue-i18n'
import { BackendApiError } from '@/api/transport'
import { importStatusKey } from '@/i18n/display-maps'
import { errorMessage } from '@/i18n/errors'
import { formatNumber, formatPercent } from '@/i18n/formatters'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  documents: KnowledgeDocument[]
  jobs: KnowledgeImportJob[]
  selectedId: number | null
  selectedIds?: number[]
  favoritePendingIds?: number[]
  cancelJob: (id: number) => unknown
  retryJob?: (id: number) => unknown
}>(), { selectedIds: () => [], favoritePendingIds: () => [] })

defineEmits<{
  (event: 'select', id: number): void
  (event: 'toggle-selection', id: number): void
  (event: 'toggle-favorite', id: number, favorite: boolean): void
  (event: 'drop', value: DragEvent): void
  (event: 'drag-active', value: boolean): void
}>()

function activeJobFor(documentId: number) {
  return props.jobs.find(job => job.document_id === documentId && ['QUEUED', 'VALIDATING', 'PARSING', 'OCR_RUNNING', 'INDEXING'].includes(job.status))
}

function failedOcrJobFor(documentId: number) {
  return props.jobs.find(job => job.document_id === documentId && job.status === 'FAILED' && job.retryable && job.failed_pages.length > 0)
}

function progressLabel(job: KnowledgeImportJob) {
  const page = job.current_page && job.page_count ? `${t('components.documentGrid.pageProgress', { currentPage: formatNumber(job.current_page), pageCount: formatNumber(job.page_count) })} ` : ''
  return `${page}${formatPercent(job.progress / 100, { maximumFractionDigits: 0 })} · ${etaLabel(job)}`
}

function etaLabel(job: KnowledgeImportJob) {
  return job.eta_seconds === null ? t('components.documentGrid.etaCalculating') : t('components.documentGrid.estimatedSeconds', { etaSeconds: formatNumber(job.eta_seconds) })
}

function failedOcrLabel(job: KnowledgeImportJob) {
  return job.current_page && job.page_count ? t('components.documentGrid.recognition', { currentPage: formatNumber(job.current_page), pageCount: formatNumber(job.page_count) }) : t('components.documentGrid.pageRecognitionFailure')
}

function failureReason(code: string | null) {
  if (!code) return ''
  return errorMessage(new BackendApiError(0, code, '', true))
}

function sizeLabel(bytes: number) {
  if (bytes < 1024 * 1024) return `${formatNumber(Math.max(1, Math.round(bytes / 1024)))} KB`
  return `${formatNumber(bytes / 1024 / 1024, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB`
}

function statusLabel(status: KnowledgeDocument['status']) {
  return (KNOWLEDGE_IMPORT_STATUSES as readonly string[]).includes(status)
    ? t(importStatusKey(status as KnowledgeImportJob['status']))
    : status
}
</script>

<style scoped lang="scss">
.knowledge-document-pane{min-width:0;padding:18px}.document-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:11px}.document-card{position:relative;padding:10px;background:rgba(255,253,249,.88);border:1px solid #e7ddd1;border-radius:13px;transition:.18s}.document-card:hover,.document-card.selected,.document-card.checked{border-color:#9db7b5;box-shadow:0 10px 22px rgba(88,72,53,.06);transform:translateY(-1px)}.document-card.checked{background:#f7fbf8}.card-controls{display:flex;justify-content:space-between;margin-bottom:5px}.card-controls button{width:27px;height:27px;padding:0;background:#fffaf4;border:1px solid #e4d9cc;border-radius:8px;cursor:pointer}.check-control[aria-checked=true]{color:#fff;background:#678f92;border-color:#678f92}.favorite-control{color:#a79072;font-size:17px}.favorite-control.active{color:#d09a38}.document-select{display:flex;align-items:center;gap:11px;width:100%;padding:2px;color:inherit;text-align:left;background:transparent;border:0;cursor:pointer}.document-select:focus-visible{outline:3px solid rgba(107,151,155,.3);outline-offset:4px}.file-mark{width:42px;height:52px;display:grid;place-items:center;flex:none;color:#fff;background:linear-gradient(145deg,#7fa3a1,#587f84);border-radius:8px 8px 8px 3px;font-size:8px;letter-spacing:.08em}.file-copy{min-width:0}.file-copy strong,.file-copy small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file-copy strong{font-size:12px}.file-copy small{margin-top:6px;color:var(--muted);font-size:9px}.document-tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:9px}.document-tags span{padding:3px 6px;color:#6d8581;background:#edf5f1;border-radius:99px;font-size:8px}.import-progress{display:grid;grid-template-columns:1fr auto;align-items:center;gap:7px;margin-top:10px;color:#9b8d80;font-size:9px}.import-progress [role=progressbar]{height:5px;overflow:hidden;background:#eee5da;border-radius:9px}.import-progress i{display:block;height:100%;background:#7ca49c;transition:width .2s}.import-progress small{grid-column:1/-1;color:#a06d62}.import-progress button{padding:0;color:#ad6670;background:transparent;border:0;cursor:pointer}.document-empty{min-height:330px;display:grid;place-content:center;text-align:center;color:#aa9d90}.document-empty span,.document-empty strong{display:block}.document-empty strong{margin-top:8px;color:#7e7266;font-family:Georgia,"Songti SC",serif;font-size:17px;font-weight:500}.ocr-failure{display:grid;gap:4px;margin-top:10px;padding:8px;color:#8a6536;background:#fff4df;border-radius:8px;font-size:9px}.ocr-failure small{color:#9b7d57}.ocr-failure button{justify-self:start;padding:0;color:#8b5b45;background:transparent;border:0;text-decoration:underline;cursor:pointer}@media(max-width:760px){.document-grid{grid-template-columns:1fr}.knowledge-document-pane{padding:12px}}@media(prefers-reduced-motion:reduce){.document-card,.import-progress i{transition:none}.document-card:hover{transform:none}}
</style>
