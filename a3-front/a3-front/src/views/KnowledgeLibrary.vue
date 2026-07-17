<template>
  <section class="knowledge-page">
    <header class="knowledge-header"><div><span class="knowledge-kicker">LOCAL LIBRARY</span><h1>把学过的风，收进一座小书房</h1><p>资料只留在这台设备。需要模型协助时，也只取与你问题相关的少量片段。</p></div><div class="knowledge-toolbar"><span class="mode-badge">{{ backend.knowledgeStatus?.semantic_pack.available?'混合检索':'关键词检索' }}</span><button data-testid="import-knowledge-files" type="button" :disabled="!desktopAvailable||!activeCollectionId" @click="importFiles">{{ desktopAvailable?'导入资料':'导入仅桌面版可用' }}</button></div></header>
    <TextbookCatalog :items="textbookItems" :desktop-available="desktopAvailable" @open="openOfficialTextbook" />
    <div v-if="backend.knowledgeError" class="knowledge-error" role="alert">{{ backend.knowledgeError }}</div>
    <div class="knowledge-mobile-tools"><button type="button" @click="collectionDrawer=true">集合</button><button type="button" :disabled="!selectedDocument" @click="inspectorDrawer=true">资料详情</button></div>
    <div class="knowledge-workspace" :class="{ 'is-drop-active': dropActive }">
      <CollectionRail :collections="backend.knowledgeCollections" :selected-id="activeCollectionId" @select="selectCollection" @create="createCollection" @rename="renameCollection" @delete="deleteCollection" />
      <div class="knowledge-center">
        <div class="center-heading">
          <div><strong>{{ trashOnly ? '回收站' : (activeCollection?.name||'全部资料') }}</strong><span>{{ filteredDocuments.length }} 份资料</span></div>
          <input v-model="filter" aria-label="筛选知识库资料" placeholder="寻找一份记得的资料…">
        </div>
        <div class="advanced-filters" aria-label="知识库高级筛选">
          <label><input v-model="trashOnly" data-testid="trash-filter" type="checkbox"> 回收站</label>
          <label><input v-model="favoriteOnly" type="checkbox"> 仅收藏</label>
          <input v-model="tagFilter" aria-label="按标签筛选" placeholder="标签">
          <select v-model="statusFilter" aria-label="按状态筛选"><option value="">全部状态</option><option value="COMPLETED">已完成</option><option value="PARSING">解析中</option><option value="OCR_RUNNING">OCR 中</option><option value="FAILED">失败</option></select>
          <select v-model="sortFilter" data-testid="sort-filter" aria-label="资料排序"><option value="created">导入时间</option><option value="updated">更新时间</option><option value="name">名称</option><option value="size">大小</option></select>
          <select v-model="directionFilter" aria-label="排序方向"><option value="desc">降序</option><option value="asc">升序</option></select>
        </div>
        <div class="bulk-toolbar" aria-label="批量资料操作">
          <button data-testid="select-all-documents" type="button" @click="toggleSelectAll">{{ allVisibleSelected ? '取消全选' : '全选当前结果' }}</button>
          <span data-testid="bulk-selection-count">已选 {{ selectedDocumentIds.length }} 项</span>
          <select v-model.number="targetCollectionId" aria-label="批量操作目标集合"><option :value="null">选择集合</option><option v-for="collection in backend.knowledgeCollections" :key="collection.id" :value="collection.id">{{ collection.name }}</option></select>
          <button type="button" :disabled="!canMutateSelection||!targetCollectionId" @click="bulkCollections('add_to_collections')">加入集合</button>
          <button type="button" :disabled="!canMutateSelection||!targetCollectionId" @click="bulkCollections('remove_from_collections')">移出集合</button>
          <input v-model="tagEditor" aria-label="批量设置标签" placeholder="标签用逗号分隔">
          <button type="button" :disabled="!canMutateSelection" @click="bulkSetTags">设置标签</button>
          <button type="button" :disabled="!canMutateSelection" @click="bulkFavorite(true)">收藏</button>
          <button v-if="!trashOnly" data-testid="bulk-trash" type="button" :disabled="!canMutateSelection" @click="bulkTrash">移入回收站</button>
          <button v-else data-testid="bulk-restore" type="button" :disabled="!canMutateSelection" @click="runBulk('restore')">恢复</button>
          <button v-if="trashOnly" data-testid="bulk-purge" class="danger" type="button" :disabled="!canMutateSelection" @click="bulkPurge">永久删除</button>
        </div>
        <DocumentGrid :documents="filteredDocuments" :jobs="backend.knowledgeJobs" :selected-id="selectedDocumentId" :selected-ids="selectedDocumentIds" :cancel-job="backend.cancelKnowledgeJob" :retry-job="backend.retryKnowledgeJob" @select="selectDocument" @toggle-selection="toggleDocumentSelection" @toggle-favorite="toggleFavorite" @drag-active="dropActive=$event" @drop="handleDrop" />
      </div>
      <DocumentInspector :document="selectedDocument" :desktop-available="desktopAvailable" @summarize="summarizeDocument" @worked-example="workedExampleDocument" @open="openDocument" @rebuild="rebuildDocument" @delete="deleteDocument" />
    </div>
    <el-drawer v-model="collectionDrawer" direction="ltr" size="280px" title="资料集合"><CollectionRail :collections="backend.knowledgeCollections" :selected-id="activeCollectionId" @select="selectCollection" @create="createCollection" @rename="renameCollection" @delete="deleteCollection" /></el-drawer>
    <el-drawer v-model="inspectorDrawer" direction="rtl" size="330px" title="资料详情"><DocumentInspector :document="selectedDocument" :desktop-available="desktopAvailable" @summarize="summarizeDocument" @worked-example="workedExampleDocument" @open="openDocument" @rebuild="rebuildDocument" @delete="deleteDocument" /></el-drawer>
  </section>
</template>
<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { routeLocationKey, routerKey } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  backendApi,
  errorMessage,
  type KnowledgeCollection,
  type KnowledgeBulkAction,
  type KnowledgeBulkRequest,
  type KnowledgeImportBatch,
  type KnowledgeImportJob,
  type KnowledgeLocator,
  type TextbookCatalogItem,
} from '@/api'
import { useBackendStore } from '@/stores/backend'
import CollectionRail from '@/components/knowledge/CollectionRail.vue'
import DocumentGrid from '@/components/knowledge/DocumentGrid.vue'
import DocumentInspector from '@/components/knowledge/DocumentInspector.vue'
import TextbookCatalog from '@/components/knowledge/TextbookCatalog.vue'

const activeJobStatuses = new Set(['QUEUED', 'VALIDATING', 'PARSING', 'OCR_RUNNING', 'INDEXING'])
const locatorTypes = new Set<KnowledgeLocator['type']>(['page', 'slide', 'sheet_rows', 'paragraph'])
const backend = useBackendStore()
const route = inject(routeLocationKey, null)
const router = inject(routerKey, null)
const activeCollectionId = ref<number | null>(null)
const selectedDocumentId = ref<number | null>(null)
const selectedDocumentIds = ref<number[]>([])
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
let collectionRequestVersion = 0

function firstQueryValue(value: string | null | (string | null)[] | undefined) {
  return Array.isArray(value) ? value[0] : value
}

const desktopAvailable = computed(() => Boolean(window.a3Desktop?.knowledgeChooseFiles))
const activeCollection = computed(() => backend.knowledgeCollections.find(item => item.id === activeCollectionId.value))
const filteredDocuments = computed(() => backend.knowledgeDocuments)
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

async function selectCollection(id: number) {
  const requestVersion = ++collectionRequestVersion
  try {
    const documents = await backendApi.knowledgeDocuments(id)
    if (requestVersion !== collectionRequestVersion) return
    activeCollectionId.value = id
    collectionDrawer.value = false
    backend.knowledgeDocuments = documents
    selectedDocumentIds.value = []
    selectedDocumentId.value = backend.knowledgeDocuments[0]?.id || null
  } catch (error) {
    if (requestVersion === collectionRequestVersion) ElMessage.error(errorMessage(error))
  }
}

function documentFilters() {
  return {
    ...(activeCollectionId.value ? { collectionId: activeCollectionId.value } : {}),
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
  try {
    const documents = await backendApi.knowledgeDocuments(documentFilters())
    backend.knowledgeDocuments = documents
    selectedDocumentIds.value = selectedDocumentIds.value.filter(id => documents.some(item => item.id === id))
    if (!documents.some(item => item.id === selectedDocumentId.value)) selectedDocumentId.value = documents[0]?.id || null
  } catch (error) {
    ElMessage.error(errorMessage(error))
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
    if (failures.length) ElMessage.warning(`${failures.length} 份资料未完成操作，请重试。`)
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

function toggleFavorite(id: number, favorite: boolean) {
  selectedDocumentIds.value = [id]
  void runBulk('favorite', { favorite })
}

async function bulkTrash() {
  try {
    await ElMessageBox.confirm('所选资料将移入回收站，可随时恢复。', '移入回收站', { type: 'warning' })
    await runBulk('move_to_trash')
  } catch (error) { reportMutationError(error) }
}

async function bulkPurge() {
  try {
    await ElMessageBox.confirm('永久删除后无法恢复，原文件副本和索引都会被清理。', '永久删除', { type: 'warning' })
    await runBulk('purge')
  } catch (error) { reportMutationError(error) }
}

function reportDuplicates(result: KnowledgeImportBatch) {
  const duplicates = result.duplicates || []
  if (!duplicates.length) return
  const names = duplicates.slice(0, 3).map(item => `《${item.display_name}》`).join('、')
  const linked = duplicates.filter(item => item.action === 'linked_existing').length
  const suffix = duplicates.length > 3 ? `等 ${duplicates.length} 份资料` : names
  ElMessage.warning(`${suffix} 已存在，${linked ? `${linked} 份已直接加入当前集合，` : ''}没有重复解析。`)
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
  const name = window.prompt('给这个资料集合取一个名字')
  if (!name?.trim()) return
  try {
    await backendApi.createKnowledgeCollection({ name: name.trim(), description: '', color: '#c98f65' })
    await backend.refreshKnowledge()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function renameCollection(item: KnowledgeCollection) {
  const name = window.prompt('给集合换一个名字', item.name)
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
    await ElMessageBox.confirm(`删除集合“${item.name}”？资料仍会保留在其他集合中。`, '删除集合', { type: 'warning' })
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
    ElMessage.success('已用本地阅读器打开只读预览。')
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
    ElMessage.warning('请先选择包含这份资料的知识库集合，再开始总结或例题讲解。')
    return
  }
  if (!router) {
    ElMessage.error('学习助手路由尚未就绪，请稍后重试。')
    return
  }
  const prompt = mode === 'summary'
    ? `请基于已绑定的教材《${document.display_name}》总结知识点。请包含核心概念、公式及适用条件、知识依赖、常见题型、易错点，并引用实际检索到的[资料N]。`
    : `请基于已绑定的教材《${document.display_name}》生成一道有代表性的数学例题，并按已知条件与目标、所用知识点、分步推导、最终答案、结果检查完整讲解；引用实际检索到的[资料N]。`
  void router.push({
    name: 'SmartTutor',
    query: { knowledge_collection: String(activeCollectionId.value), prompt },
  })
}

function summarizeDocument(id: number) { launchDocumentLearning(id, 'summary') }
function workedExampleDocument(id: number) { launchDocumentLearning(id, 'worked-example') }

async function rebuildDocument(id: number) {
  try {
    await ElMessageBox.confirm('重新解析会更新这份资料的检索片段。', '重新解析')
    await backend.rebuildKnowledgeDocument(id)
  } catch (error) {
    reportMutationError(error)
  }
}

async function deleteDocument(id: number) {
  try {
    await ElMessageBox.confirm('这份资料会移入回收站，可在 30 天内恢复。', '移入回收站', { type: 'warning' })
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
    textbookItems.value = (await backendApi.textbookCatalog({ subject: '数学', publisher: '人民教育出版社' })).items
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
  collectionRequestVersion += 1
  disposeImportProgress?.()
})
</script>
<style scoped lang="scss">
.knowledge-page{max-width:1500px;margin:0 auto}.knowledge-header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:18px}.knowledge-kicker{color:#789b98;font-size:9px;letter-spacing:.18em}.knowledge-header h1{margin:5px 0 0;font-family:Georgia,"Songti SC",serif;font-size:24px;font-weight:500}.knowledge-header p{margin:7px 0 0;color:var(--muted);font-size:11px}.knowledge-toolbar{display:flex;align-items:center;gap:8px}.knowledge-toolbar button,.knowledge-mobile-tools button{min-height:34px;padding:0 13px;color:#fff;background:#678f92;border:0;border-radius:9px;cursor:pointer}.knowledge-toolbar button:disabled{color:#a39789;background:#e8dfd4}.mode-badge{padding:5px 9px;color:#6f918d;background:#e8f2ee;border-radius:99px;font-size:9px}.knowledge-workspace{min-height:560px;display:grid;grid-template-columns:240px minmax(340px,1fr) 320px;overflow:hidden;background:rgba(255,253,249,.8);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow-soft)}.knowledge-workspace.is-drop-active{box-shadow:inset 0 0 0 3px rgba(107,151,155,.35)}.knowledge-center{min-width:0}.center-heading{display:flex;align-items:center;justify-content:space-between;padding:15px 18px;border-bottom:1px solid var(--line)}.center-heading strong,.center-heading span{display:block}.center-heading strong{font-size:13px}.center-heading span{margin-top:3px;color:var(--muted);font-size:9px}.center-heading input{width:min(230px,45%);height:32px;padding:0 10px;color:#70655a;background:#fffaf4;border:1px solid #e4d9cc;border-radius:9px;outline:0}.center-heading input:focus{border-color:#8faeac;box-shadow:0 0 0 3px rgba(107,151,155,.1)}.knowledge-error{margin-bottom:10px;padding:10px;color:#a05561;background:#fff1f2;border-radius:9px}.knowledge-mobile-tools{display:none;gap:7px;margin-bottom:8px}@media(max-width:1060px){.knowledge-workspace{grid-template-columns:240px minmax(0,1fr)}.knowledge-workspace>.document-inspector{display:none}.knowledge-mobile-tools{display:flex}}@media(max-width:760px){.knowledge-header{align-items:stretch;flex-direction:column}.knowledge-workspace{display:block;min-height:480px}.knowledge-workspace>.knowledge-collection-rail{display:none}.knowledge-header h1{font-size:20px}.knowledge-toolbar{justify-content:space-between}.center-heading{align-items:stretch;flex-direction:column;gap:8px}.center-heading input{width:100%}}
.advanced-filters,.bulk-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:7px;padding:9px 18px;border-bottom:1px solid var(--line);font-size:9px}.advanced-filters{background:#faf7f1}.advanced-filters input:not([type=checkbox]),.advanced-filters select,.bulk-toolbar input,.bulk-toolbar select{height:30px;max-width:150px;padding:0 8px;color:#70655a;background:#fff;border:1px solid #e4d9cc;border-radius:8px}.bulk-toolbar{background:#f4f8f5}.bulk-toolbar button{min-height:29px;padding:0 9px;color:#5f8588;background:#fff;border:1px solid #d4e3dd;border-radius:8px;cursor:pointer}.bulk-toolbar button:disabled{opacity:.45;cursor:not-allowed}.bulk-toolbar .danger{color:#a05d65;border-color:#edd9d8}.bulk-toolbar span{margin-right:auto;color:#7b8d88}@media(max-width:760px){.advanced-filters,.bulk-toolbar{align-items:stretch;flex-direction:column}.advanced-filters input:not([type=checkbox]),.advanced-filters select,.bulk-toolbar input,.bulk-toolbar select,.bulk-toolbar button{width:100%;max-width:none}}
</style>
