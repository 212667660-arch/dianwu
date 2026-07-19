<template>
  <section class="knowledge-page">
    <header class="knowledge-header"><div><span class="knowledge-kicker">LOCAL LIBRARY</span><h1>{{ t('views.knowledge.heroTitle') }}</h1><p>{{ t('views.knowledge.modelDocument') }}</p></div><div class="knowledge-toolbar"><span class="mode-badge">{{ backend.knowledgeStatus?.semantic_pack.available?t('views.knowledge.search'):t('views.knowledge.searchTitle') }}</span><button data-testid="import-knowledge-files" type="button" :disabled="!desktopAvailable||!activeCollectionId" @click="importFiles">{{ desktopAvailable?t('views.knowledge.documentImport'):t('views.knowledge.desktopImportAvailable') }}</button></div></header>
    <TextbookCatalog :items="textbookItems" :desktop-available="desktopAvailable" @open="openOfficialTextbook" />
    <div v-if="backend.knowledgeError" class="knowledge-error" role="alert">{{ backend.knowledgeError }}</div>
    <div class="knowledge-mobile-tools"><button type="button" @click="collectionDrawer=true">{{ t('views.knowledge.collection') }}</button><button type="button" :disabled="!selectedDocument" @click="inspectorDrawer=true">{{ t('views.knowledge.documentDetails') }}</button></div>
    <div class="knowledge-workspace" :class="{ 'is-drop-active': dropActive }">
      <CollectionRail :collections="backend.knowledgeCollections" :selected-id="activeCollectionId" @select="selectCollection" @create="createCollection" @rename="renameCollection" @delete="deleteCollection" />
      <div class="knowledge-center">
        <div class="center-heading">
          <div><strong>{{ trashOnly ? t('views.knowledge.trash') : (activeCollection?.name||t('views.knowledge.allDocuments')) }}</strong><span>{{ filteredDocuments.length }} {{ t('views.knowledge.document') }}</span></div>
          <input v-model="filter" :aria-label="t('views.knowledge.documentFilterAriaLabel')" :placeholder="t('views.knowledge.documentTitle')">
        </div>
        <div class="advanced-filters" :aria-label="t('views.knowledge.advancedFilterAriaLabel')">
          <label><input v-model="trashOnly" data-testid="trash-filter" type="checkbox"> {{ t('views.knowledge.trash') }}</label>
          <label><input v-model="favoriteOnly" type="checkbox"> {{ t('views.knowledge.favorite') }}</label>
          <input v-model="tagFilter" :aria-label="t('views.knowledge.tagFilter')" :placeholder="t('views.knowledge.tag')">
          <select v-model="statusFilter" :aria-label="t('views.knowledge.statusFilter')"><option value="">{{ t('views.knowledge.statusAll') }}</option><option value="COMPLETED">{{ t('views.knowledge.completed') }}</option><option value="PARSING">{{ t('views.knowledge.parse') }}</option><option value="OCR_RUNNING">{{ t('views.knowledge.ocrInProgress') }}</option><option value="FAILED">{{ t('views.knowledge.failure') }}</option></select>
          <select v-model="sortFilter" data-testid="sort-filter" :aria-label="t('views.knowledge.documentSort')"><option value="created">{{ t('views.knowledge.importTime') }}</option><option value="updated">{{ t('views.knowledge.updateTime') }}</option><option value="name">{{ t('views.knowledge.name') }}</option><option value="size">{{ t('views.knowledge.size') }}</option></select>
          <select v-model="directionFilter" :aria-label="t('views.knowledge.sortTitle')"><option value="desc">{{ t('views.knowledge.descending') }}</option><option value="asc">{{ t('views.knowledge.ascending') }}</option></select>
        </div>
        <div class="bulk-toolbar" :aria-label="t('views.knowledge.documentBulk')">
          <button data-testid="select-all-documents" type="button" @click="toggleSelectAll">{{ allVisibleSelected ? t('views.knowledge.cancel') : t('views.knowledge.resultCurrent') }}</button>
          <span data-testid="bulk-selection-count">{{ t('views.knowledge.selectedLabel') }} {{ selectedDocumentIds.length }} {{ t('views.knowledge.itemUnit') }}</span>
          <select v-model.number="targetCollectionId" :aria-label="t('views.knowledge.collectionBulkGoal')"><option :value="null">{{ t('views.knowledge.collectionSelect') }}</option><option v-for="collection in backend.knowledgeCollections" :key="collection.id" :value="collection.id">{{ collection.name }}</option></select>
          <button type="button" :disabled="!canMutateSelection||!targetCollectionId" @click="bulkCollections('add_to_collections')">{{ t('views.knowledge.collectionTitle') }}</button>
          <button type="button" :disabled="!canMutateSelection||!targetCollectionId" @click="bulkCollections('remove_from_collections')">{{ t('views.knowledge.collectionDescription') }}</button>
          <input v-model="tagEditor" :aria-label="t('views.knowledge.settingsTagBulk')" :placeholder="t('views.knowledge.tagTitle')">
          <button type="button" :disabled="!canMutateSelection" @click="bulkSetTags">{{ t('views.knowledge.settingsTag') }}</button>
          <button type="button" :disabled="!canMutateSelection" @click="bulkFavorite(true)">{{ t('views.knowledge.favorites') }}</button>
          <button v-if="!trashOnly" data-testid="bulk-trash" type="button" :disabled="!canMutateSelection" @click="bulkTrash">{{ t('views.knowledge.recycleBin') }}</button>
          <button v-else data-testid="bulk-restore" type="button" :disabled="!canMutateSelection" @click="runBulk('restore')">{{ t('views.knowledge.restoreTitle') }}</button>
          <button v-if="trashOnly" data-testid="bulk-purge" class="danger" type="button" :disabled="!canMutateSelection" @click="bulkPurge">{{ t('views.knowledge.purge') }}</button>
        </div>
        <DocumentGrid :documents="filteredDocuments" :jobs="backend.knowledgeJobs" :selected-id="selectedDocumentId" :selected-ids="selectedDocumentIds" :favorite-pending-ids="favoritePendingIds" :cancel-job="backend.cancelKnowledgeJob" :retry-job="backend.retryKnowledgeJob" @select="selectDocument" @toggle-selection="toggleDocumentSelection" @toggle-favorite="toggleFavorite" @drag-active="dropActive=$event" @drop="handleDrop" />
      </div>
      <DocumentInspector :document="selectedDocument" :desktop-available="desktopAvailable" @summarize="summarizeDocument" @worked-example="workedExampleDocument" @open="openDocument" @rebuild="rebuildDocument" @delete="deleteDocument" />
    </div>
    <el-drawer v-model="collectionDrawer" direction="ltr" size="280px" :title="t('views.knowledge.collections')"><CollectionRail :collections="backend.knowledgeCollections" :selected-id="activeCollectionId" @select="selectCollection" @create="createCollection" @rename="renameCollection" @delete="deleteCollection" /></el-drawer>
    <el-drawer v-model="inspectorDrawer" direction="rtl" size="330px" :title="t('views.knowledge.documentDetails')"><DocumentInspector :document="selectedDocument" :desktop-available="desktopAvailable" @summarize="summarizeDocument" @worked-example="workedExampleDocument" @open="openDocument" @rebuild="rebuildDocument" @delete="deleteDocument" /></el-drawer>
  </section>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { routeLocationKey, routerKey } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  backendApi,
  errorMessage,
  type KnowledgeCollection,
  type KnowledgeDocument,
  type KnowledgeBulkAction,
  type KnowledgeBulkRequest,
  type KnowledgeImportBatch,
  type KnowledgeImportJob,
  type KnowledgeLocator,
  type TextbookCatalogItem,
} from '@/api'
import { useBackendStore } from '@/stores/backend'
import { PEOPLE_EDUCATION_PRESS_PUBLISHER, TEXTBOOK_MATH_SUBJECT } from '@/utils/protocol'
import CollectionRail from '@/components/knowledge/CollectionRail.vue'
import DocumentGrid from '@/components/knowledge/DocumentGrid.vue'
import DocumentInspector from '@/components/knowledge/DocumentInspector.vue'
import TextbookCatalog from '@/components/knowledge/TextbookCatalog.vue'

const { t } = useI18n()

const activeJobStatuses = new Set(['QUEUED', 'VALIDATING', 'PARSING', 'OCR_RUNNING', 'INDEXING'])
const locatorTypes = new Set<KnowledgeLocator['type']>(['page', 'slide', 'sheet_rows', 'paragraph'])
const backend = useBackendStore()
const route = inject(routeLocationKey, null)
const router = inject(routerKey, null)
const activeCollectionId = ref<number | null>(null)
const pendingCollectionId = ref<number | null>(null)
const selectedDocumentId = ref<number | null>(null)
const selectedDocumentIds = ref<number[]>([])
const favoritePendingIds = ref<number[]>([])
const favoriteOverrides = ref<Record<number, boolean>>({})
const filter = ref('')
const trashOnly = ref(false)
const favoriteOnly = ref(false)
const tagFilter = ref('')
const statusFilter = ref('')
const sortFilter = ref<'created' | 'updated' | 'name' | 'size'>('created')
const directionFilter = ref<'asc' | 'desc'>('desc')
const targetCollectionId = ref<number | null>(null)
const tagEditor = ref('')
const dropActive = ref(false)
const collectionDrawer = ref(false)
const inspectorDrawer = ref(false)
const textbookItems = ref<TextbookCatalogItem[]>([])
let disposeImportProgress: (() => void) | undefined
let documentRequestVersion = 0
let favoriteInvalidatedThroughVersion = 0

function firstQueryValue(value: string | null | (string | null)[] | undefined) {
  return Array.isArray(value) ? value[0] : value
}

const desktopAvailable = computed(() => Boolean(window.a3Desktop?.knowledgeChooseFiles))
const activeCollection = computed(() => backend.knowledgeCollections.find(item => item.id === activeCollectionId.value))
const filteredDocuments = computed(() => backend.knowledgeDocuments.map(item => (
  Object.hasOwn(favoriteOverrides.value, item.id)
    ? { ...item, favorite: favoriteOverrides.value[item.id] }
    : item
)))
const canMutateSelection = computed(() => selectedDocumentIds.value.length > 0)
const allVisibleSelected = computed(() => filteredDocuments.value.length > 0 && filteredDocuments.value.every(item => selectedDocumentIds.value.includes(item.id)))
const selectedDocument = computed(() => backend.knowledgeDocuments.find(item => item.id === selectedDocumentId.value) || null)
const routedDocumentId = computed(() => Number(firstQueryValue(route?.query.document)))
const routedLocator = computed<KnowledgeLocator | null>(() => {
  const type = firstQueryValue(route?.query.type)
  const start = Number(firstQueryValue(route?.query.start))
  const end = Number(firstQueryValue(route?.query.end))
  if (
    routedDocumentId.value !== selectedDocumentId.value
    || !locatorTypes.has(type as KnowledgeLocator['type'])
    || !Number.isInteger(start)
    || !Number.isInteger(end)
    || start < 1
    || end < start
  ) return null
  const sheet = firstQueryValue(route?.query.sheet)
  return {
    type: type as KnowledgeLocator['type'],
    start,
    end,
    ...(typeof sheet === 'string' && sheet.length <= 128 ? { sheet_name: sheet } : {}),
  }
})

function applyFavoriteOverrides(documents: KnowledgeDocument[]) {
  return documents.map(item => (
    Object.hasOwn(favoriteOverrides.value, item.id)
      ? { ...item, favorite: favoriteOverrides.value[item.id] }
      : item
  ))
}

function canApplyDocumentRequest(requestVersion: number, requestCollectionId: number | null) {
  return requestVersion === documentRequestVersion && (
    requestVersion > favoriteInvalidatedThroughVersion
    || (requestCollectionId !== null && pendingCollectionId.value === requestCollectionId)
  )
}

async function selectCollection(id: number) {
  pendingCollectionId.value = id
  const requestVersion = ++documentRequestVersion
  try {
    const documents = await backendApi.knowledgeDocuments(documentFilters(id))
    if (!canApplyDocumentRequest(requestVersion, id)) return
    activeCollectionId.value = id
    if (pendingCollectionId.value === id) pendingCollectionId.value = null
    collectionDrawer.value = false
    backend.knowledgeDocuments = applyFavoriteOverrides(documents)
    selectedDocumentIds.value = []
    selectedDocumentId.value = backend.knowledgeDocuments[0]?.id || null
  } catch (error) {
    if (canApplyDocumentRequest(requestVersion, id)) {
      if (pendingCollectionId.value === id) pendingCollectionId.value = null
      ElMessage.error(errorMessage(error))
    }
  }
}

function documentFilters(collectionId: number | null = pendingCollectionId.value ?? activeCollectionId.value) {
  return {
    ...(collectionId ? { collectionId } : {}),
    trash: trashOnly.value,
    ...(favoriteOnly.value ? { favorite: true } : {}),
    ...(tagFilter.value.trim() ? { tag: tagFilter.value.trim() } : {}),
    ...(filter.value.trim() ? { query: filter.value.trim() } : {}),
    ...(statusFilter.value ? { status: statusFilter.value } : {}),
    sort: sortFilter.value,
    direction: directionFilter.value,
  }
}

async function refreshFilteredDocuments() {
  const requestCollectionId = pendingCollectionId.value ?? activeCollectionId.value
  const requestVersion = ++documentRequestVersion
  try {
    const documents = await backendApi.knowledgeDocuments(documentFilters(requestCollectionId))
    if (!canApplyDocumentRequest(requestVersion, requestCollectionId)) return
    backend.knowledgeDocuments = applyFavoriteOverrides(documents)
    if (pendingCollectionId.value !== null && pendingCollectionId.value === requestCollectionId) {
      activeCollectionId.value = requestCollectionId
      pendingCollectionId.value = null
      collectionDrawer.value = false
      selectedDocumentIds.value = []
      selectedDocumentId.value = documents[0]?.id || null
    } else {
      selectedDocumentIds.value = selectedDocumentIds.value.filter(id => documents.some(item => item.id === id))
      if (!documents.some(item => item.id === selectedDocumentId.value)) selectedDocumentId.value = documents[0]?.id || null
    }
  } catch (error) {
    if (canApplyDocumentRequest(requestVersion, requestCollectionId)) {
      if (pendingCollectionId.value === requestCollectionId) pendingCollectionId.value = null
      ElMessage.error(errorMessage(error))
    }
  }
}

function toggleDocumentSelection(id: number) {
  selectedDocumentIds.value = selectedDocumentIds.value.includes(id)
    ? selectedDocumentIds.value.filter(item => item !== id)
    : [...selectedDocumentIds.value, id].sort((a, b) => a - b)
}

function toggleSelectAll() {
  if (allVisibleSelected.value) {
    const visible = new Set(filteredDocuments.value.map(item => item.id))
    selectedDocumentIds.value = selectedDocumentIds.value.filter(id => !visible.has(id))
  } else {
    selectedDocumentIds.value = [...new Set([...selectedDocumentIds.value, ...filteredDocuments.value.map(item => item.id)])].sort((a, b) => a - b)
  }
}

async function runBulk(action: KnowledgeBulkAction, fields: Partial<KnowledgeBulkRequest> = {}) {
  if (!selectedDocumentIds.value.length) return
  const input: KnowledgeBulkRequest = {
    action,
    document_ids: [...selectedDocumentIds.value].sort((a, b) => a - b),
    collection_ids: fields.collection_ids || [],
    tags: fields.tags || [],
    ...(fields.favorite === undefined ? {} : { favorite: fields.favorite }),
  }
  try {
    const result = await backend.bulkKnowledgeDocuments(input)
    const failures = result.items.filter(item => !item.ok)
    if (failures.length) ElMessage.warning(t('views.knowledge.bulkOperationFailure', { length: failures.length }))
    if (action === 'favorite' && typeof fields.favorite === 'boolean') {
      const nextOverrides = { ...favoriteOverrides.value }
      for (const item of result.items) {
        if (item.ok) nextOverrides[item.document_id] = fields.favorite
      }
      favoriteOverrides.value = nextOverrides
    }
    selectedDocumentIds.value = []
    await refreshFilteredDocuments()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function bulkCollections(action: 'add_to_collections' | 'remove_from_collections') {
  if (targetCollectionId.value) void runBulk(action, { collection_ids: [targetCollectionId.value] })
}

function bulkSetTags() {
  const tags = [...new Set(tagEditor.value.split(/[，,]/).map(item => item.trim()).filter(Boolean))].sort()
  void runBulk('set_tags', { tags })
}

function bulkFavorite(favorite: boolean) { void runBulk('favorite', { favorite }) }

async function toggleFavorite(id: number, favorite: boolean) {
  if (favoritePendingIds.value.includes(id)) return
  const index = backend.knowledgeDocuments.findIndex(item => item.id === id)
  if (index < 0) return
  const hadPreviousOverride = Object.hasOwn(favoriteOverrides.value, id)
  const previousFavorite = hadPreviousOverride
    ? favoriteOverrides.value[id]
    : Boolean(backend.knowledgeDocuments[index].favorite)
  const favoriteReadCutoff = documentRequestVersion
  let saved = false
  favoritePendingIds.value = [...favoritePendingIds.value, id]
  favoriteOverrides.value = { ...favoriteOverrides.value, [id]: favorite }
  backend.knowledgeDocuments[index] = { ...backend.knowledgeDocuments[index], favorite }
  try {
    const result = await backend.bulkKnowledgeDocuments({
      action: 'favorite',
      document_ids: [id],
      collection_ids: [],
      tags: [],
      favorite,
    }, { refresh: false })
    if (!result.items.some(item => item.document_id === id && item.ok)) {
      throw new Error(t('views.knowledge.favoriteSaveFailure'))
    }
    saved = true
    favoriteInvalidatedThroughVersion = Math.max(favoriteInvalidatedThroughVersion, favoriteReadCutoff)
    const currentIndex = backend.knowledgeDocuments.findIndex(item => item.id === id)
    if (currentIndex >= 0) {
      backend.knowledgeDocuments[currentIndex] = { ...backend.knowledgeDocuments[currentIndex], favorite }
    }
    if (favoriteOnly.value && !favorite) {
      backend.knowledgeDocuments = backend.knowledgeDocuments.filter(item => item.id !== id)
      if (selectedDocumentId.value === id) selectedDocumentId.value = backend.knowledgeDocuments[0]?.id || null
    }
    if (pendingCollectionId.value !== null && favoriteOnly.value) {
      void refreshFilteredDocuments()
    }
  } catch (error) {
    const rollbackIndex = backend.knowledgeDocuments.findIndex(item => item.id === id)
    if (rollbackIndex >= 0) {
      backend.knowledgeDocuments[rollbackIndex] = {
        ...backend.knowledgeDocuments[rollbackIndex],
        favorite: previousFavorite,
      }
    }
    ElMessage.error(errorMessage(error))
  } finally {
    if (!saved) {
      const remainingOverrides = { ...favoriteOverrides.value }
      if (hadPreviousOverride) remainingOverrides[id] = previousFavorite
      else delete remainingOverrides[id]
      favoriteOverrides.value = remainingOverrides
    }
    favoritePendingIds.value = favoritePendingIds.value.filter(item => item !== id)
  }
}

async function bulkTrash() {
  try {
    await ElMessageBox.confirm(t('views.knowledge.moveToTrashNotice'), t('views.knowledge.recycleBin'), { type: 'warning' })
    await runBulk('move_to_trash')
  } catch (error) { reportMutationError(error) }
}

async function bulkPurge() {
  try {
    await ElMessageBox.confirm(t('views.knowledge.permanentDeleteWarning'), t('views.knowledge.purge'), { type: 'warning' })
    await runBulk('purge')
  } catch (error) { reportMutationError(error) }
}

function reportDuplicates(result: KnowledgeImportBatch) {
  const duplicates = result.duplicates || []
  if (!duplicates.length) return
  const names = duplicates.slice(0, 3).map(item => `《${item.display_name}》`).join('、')
  const linked = duplicates.filter(item => item.action === 'linked_existing').length
  const suffix = duplicates.length > 3 ? t('views.knowledge.documentDescription', { length: duplicates.length }) : names
  const duplicateNotice = linked ? t('views.knowledge.collectionCurrent', { linked }) : ''
  ElMessage.warning(t('views.knowledge.parseTitle', { suffix, duplicateNotice }))
}

function selectDocument(id: number) {
  selectedDocumentId.value = id
  if (window.innerWidth < 1060) inspectorDrawer.value = true
}

async function importFiles() {
  if (!activeCollectionId.value) return
  try {
    const result = await backend.chooseKnowledgeFiles(activeCollectionId.value)
    reportDuplicates(result)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function handleDrop(event: DragEvent) {
  dropActive.value = false
  if (!activeCollectionId.value || !event.dataTransfer?.files.length) return
  try {
    const result = await backend.importDroppedKnowledgeFiles(event.dataTransfer.files, activeCollectionId.value)
    reportDuplicates(result)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function createCollection() {
  const name = window.prompt(t('views.knowledge.documentCollection'))
  if (!name?.trim()) return
  try {
    await backendApi.createKnowledgeCollection({ name: name.trim(), description: '', color: '#c98f65' })
    await backend.refreshKnowledge()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function renameCollection(item: KnowledgeCollection) {
  const name = window.prompt(t('views.knowledge.collectionLabel'), item.name)
  if (!name?.trim() || name.trim() === item.name) return
  try {
    await backendApi.updateKnowledgeCollection(item.id, { name: name.trim() })
    await backend.refreshKnowledge()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function reportMutationError(error: unknown) {
  if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
}

async function deleteCollection(item: KnowledgeCollection) {
  try {
    await ElMessageBox.confirm(t('views.knowledge.documentCollectionDelete', { name: item.name }), t('views.knowledge.deleteCollection'), { type: 'warning' })
    await backendApi.deleteKnowledgeCollection(item.id)
    if (activeCollectionId.value === item.id) activeCollectionId.value = null
    await backend.refreshKnowledge()
  } catch (error) {
    reportMutationError(error)
  }
}

async function openDocument(id: number) {
  try {
    await backendApi.openKnowledgeSource(id, routedLocator.value || { type: 'paragraph', start: 1, end: 1 })
    ElMessage.success(t('views.knowledge.openLocalReading'))
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function openOfficialTextbook(item: TextbookCatalogItem) {
  try {
    await backendApi.openOfficialTextbook(item.source_id)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function launchDocumentLearning(id: number, mode: 'summary' | 'worked-example') {
  const document = backend.knowledgeDocuments.find(item => item.id === id)
  if (!document) return
  if (!activeCollectionId.value) {
    ElMessage.warning(t('views.knowledge.collectionRequiredForTutor'))
    return
  }
  if (!router) {
    ElMessage.error(t('views.knowledge.tutorRouteUnavailable'))
    return
  }
  const prompt = mode === 'summary'
    ? t('views.knowledge.knowledgeSummaryPrompt', { name: document.display_name })
    : t('views.knowledge.workedExamplePrompt', { name: document.display_name })
  void router.push({
    name: 'SmartTutor',
    query: { knowledge_collection: String(activeCollectionId.value), prompt },
  })
}

function summarizeDocument(id: number) { launchDocumentLearning(id, 'summary') }
function workedExampleDocument(id: number) { launchDocumentLearning(id, 'worked-example') }

async function rebuildDocument(id: number) {
  try {
    await ElMessageBox.confirm(t('views.knowledge.reparseNotice'), t('views.knowledge.reparse'))
    await backend.rebuildKnowledgeDocument(id)
  } catch (error) {
    reportMutationError(error)
  }
}

async function deleteDocument(id: number) {
  try {
    await ElMessageBox.confirm(t('views.knowledge.trashRetentionNotice'), t('views.knowledge.recycleBin'), { type: 'warning' })
    await backend.deleteKnowledgeDocument(id)
    selectedDocumentId.value = null
  } catch (error) {
    reportMutationError(error)
  }
}

watch([filter, trashOnly, favoriteOnly, tagFilter, statusFilter, sortFilter, directionFilter], () => {
  void refreshFilteredDocuments()
})

async function applyImportProgress(jobs: KnowledgeImportJob[]) {
  const hadActive = backend.knowledgeJobs.some(job => activeJobStatuses.has(job.status))
  backend.knowledgeJobs = [...jobs]
  if (hadActive && !jobs.some(job => activeJobStatuses.has(job.status))) {
    await backend.refreshKnowledge()
    if (activeCollectionId.value) await selectCollection(activeCollectionId.value)
  }
}

onMounted(async () => {
  disposeImportProgress = window.a3Desktop?.knowledgeOnImportProgress?.(jobs => { void applyImportProgress(jobs) })
  try {
    textbookItems.value = (await backendApi.textbookCatalog({ subject: TEXTBOOK_MATH_SUBJECT, publisher: PEOPLE_EDUCATION_PRESS_PUBLISHER })).items
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
  await backend.refreshKnowledge()
  if (
    Number.isInteger(routedDocumentId.value)
    && backend.knowledgeDocuments.some(item => item.id === routedDocumentId.value)
  ) {
    activeCollectionId.value = null
    selectedDocumentId.value = routedDocumentId.value
    return
  }
  const firstCollection = backend.knowledgeCollections[0]
  if (firstCollection) await selectCollection(firstCollection.id)
  else selectedDocumentId.value = backend.knowledgeDocuments[0]?.id || null
})

onBeforeUnmount(() => {
  documentRequestVersion += 1
  disposeImportProgress?.()
})
</script>
<style scoped lang="scss">
.knowledge-page{max-width:1500px;margin:0 auto}.knowledge-header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:18px}.knowledge-kicker{color:#789b98;font-size:9px;letter-spacing:.18em}.knowledge-header h1{margin:5px 0 0;font-family:Georgia,"Songti SC",serif;font-size:24px;font-weight:500}.knowledge-header p{margin:7px 0 0;color:var(--muted);font-size:11px}.knowledge-toolbar{display:flex;align-items:center;gap:8px}.knowledge-toolbar button,.knowledge-mobile-tools button{min-height:34px;padding:0 13px;color:#fff;background:#678f92;border:0;border-radius:9px;cursor:pointer}.knowledge-toolbar button:disabled{color:#a39789;background:#e8dfd4}.mode-badge{padding:5px 9px;color:#6f918d;background:#e8f2ee;border-radius:99px;font-size:9px}.knowledge-workspace{min-height:560px;display:grid;grid-template-columns:240px minmax(340px,1fr) 320px;overflow:hidden;background:rgba(255,253,249,.8);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow-soft)}.knowledge-workspace.is-drop-active{box-shadow:inset 0 0 0 3px rgba(107,151,155,.35)}.knowledge-center{min-width:0}.center-heading{display:flex;align-items:center;justify-content:space-between;padding:15px 18px;border-bottom:1px solid var(--line)}.center-heading strong,.center-heading span{display:block}.center-heading strong{font-size:13px}.center-heading span{margin-top:3px;color:var(--muted);font-size:9px}.center-heading input{width:min(230px,45%);height:32px;padding:0 10px;color:#70655a;background:#fffaf4;border:1px solid #e4d9cc;border-radius:9px;outline:0}.center-heading input:focus{border-color:#8faeac;box-shadow:0 0 0 3px rgba(107,151,155,.1)}.knowledge-error{margin-bottom:10px;padding:10px;color:#a05561;background:#fff1f2;border-radius:9px}.knowledge-mobile-tools{display:none;gap:7px;margin-bottom:8px}@media(max-width:1060px){.knowledge-workspace{grid-template-columns:240px minmax(0,1fr)}.knowledge-workspace>.document-inspector{display:none}.knowledge-mobile-tools{display:flex}}@media(max-width:760px){.knowledge-header{align-items:stretch;flex-direction:column}.knowledge-workspace{display:block;min-height:480px}.knowledge-workspace>.knowledge-collection-rail{display:none}.knowledge-header h1{font-size:20px}.knowledge-toolbar{justify-content:space-between}.center-heading{align-items:stretch;flex-direction:column;gap:8px}.center-heading input{width:100%}}
.advanced-filters,.bulk-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:7px;padding:9px 18px;border-bottom:1px solid var(--line);font-size:9px}.advanced-filters{background:#faf7f1}.advanced-filters input:not([type=checkbox]),.advanced-filters select,.bulk-toolbar input,.bulk-toolbar select{height:30px;max-width:150px;padding:0 8px;color:#70655a;background:#fff;border:1px solid #e4d9cc;border-radius:8px}.bulk-toolbar{background:#f4f8f5}.bulk-toolbar button{min-height:29px;padding:0 9px;color:#5f8588;background:#fff;border:1px solid #d4e3dd;border-radius:8px;cursor:pointer}.bulk-toolbar button:disabled{opacity:.45;cursor:not-allowed}.bulk-toolbar .danger{color:#a05d65;border-color:#edd9d8}.bulk-toolbar span{margin-right:auto;color:#7b8d88}@media(max-width:760px){.advanced-filters,.bulk-toolbar{align-items:stretch;flex-direction:column}.advanced-filters input:not([type=checkbox]),.advanced-filters select,.bulk-toolbar input,.bulk-toolbar select,.bulk-toolbar button{width:100%;max-width:none}}
</style>
