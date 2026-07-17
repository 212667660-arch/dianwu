<template>
  <section class="knowledge-page">
    <header class="knowledge-header"><div><span class="knowledge-kicker">LOCAL LIBRARY</span><h1>把学过的风，收进一座小书房</h1><p>资料只留在这台设备。需要模型协助时，也只取与你问题相关的少量片段。</p></div><div class="knowledge-toolbar"><span class="mode-badge">{{ backend.knowledgeStatus?.semantic_pack.available?'混合检索':'关键词检索' }}</span><button type="button" :disabled="!desktopAvailable||!activeCollectionId" @click="importFiles">{{ desktopAvailable?'导入资料':'导入仅桌面版可用' }}</button></div></header>
    <TextbookCatalog :items="textbookItems" :desktop-available="desktopAvailable" @open="openOfficialTextbook" />
    <div v-if="backend.knowledgeError" class="knowledge-error" role="alert">{{ backend.knowledgeError }}</div>
    <div class="knowledge-mobile-tools"><button type="button" @click="collectionDrawer=true">集合</button><button type="button" :disabled="!selectedDocument" @click="inspectorDrawer=true">资料详情</button></div>
    <div class="knowledge-workspace" :class="{ 'is-drop-active': dropActive }">
      <CollectionRail :collections="backend.knowledgeCollections" :selected-id="activeCollectionId" @select="selectCollection" @create="createCollection" @rename="renameCollection" @delete="deleteCollection" />
      <div class="knowledge-center"><div class="center-heading"><div><strong>{{ activeCollection?.name||'全部资料' }}</strong><span>{{ filteredDocuments.length }} 份资料</span></div><input v-model="filter" aria-label="筛选知识库资料" placeholder="寻找一份记得的资料…"></div><DocumentGrid :documents="filteredDocuments" :jobs="backend.knowledgeJobs" :selected-id="selectedDocumentId" :cancel-job="backend.cancelKnowledgeJob" @select="selectDocument" @drag-active="dropActive=$event" @drop="handleDrop" /></div>
      <DocumentInspector :document="selectedDocument" :desktop-available="desktopAvailable" @open="openDocument" @rebuild="rebuildDocument" @delete="deleteDocument" />
    </div>
    <el-drawer v-model="collectionDrawer" direction="ltr" size="280px" title="资料集合"><CollectionRail :collections="backend.knowledgeCollections" :selected-id="activeCollectionId" @select="selectCollection" @create="createCollection" @rename="renameCollection" @delete="deleteCollection" /></el-drawer>
    <el-drawer v-model="inspectorDrawer" direction="rtl" size="330px" title="资料详情"><DocumentInspector :document="selectedDocument" :desktop-available="desktopAvailable" @open="openDocument" @rebuild="rebuildDocument" @delete="deleteDocument" /></el-drawer>
  </section>
</template>
<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { routeLocationKey } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  backendApi,
  errorMessage,
  type KnowledgeCollection,
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
const activeCollectionId = ref<number | null>(null)
const selectedDocumentId = ref<number | null>(null)
const filter = ref('')
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
const filteredDocuments = computed(() => {
  const query = filter.value.trim().toLowerCase()
  return backend.knowledgeDocuments.filter(item => !query || item.display_name.toLowerCase().includes(query))
})
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
    selectedDocumentId.value = backend.knowledgeDocuments[0]?.id || null
  } catch (error) {
    if (requestVersion === collectionRequestVersion) ElMessage.error(errorMessage(error))
  }
}

function selectDocument(id: number) {
  selectedDocumentId.value = id
  if (window.innerWidth < 1060) inspectorDrawer.value = true
}

async function importFiles() {
  if (!activeCollectionId.value) return
  try {
    await backend.chooseKnowledgeFiles(activeCollectionId.value)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function handleDrop(event: DragEvent) {
  dropActive.value = false
  if (!activeCollectionId.value || !event.dataTransfer?.files.length) return
  try {
    await backend.importDroppedKnowledgeFiles(event.dataTransfer.files, activeCollectionId.value)
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
    await backendApi.openOfficialTextbook(item.source_id, item.official_url)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

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
    await ElMessageBox.confirm('删除后，这份资料会从本机知识库移除。', '删除资料', { type: 'warning' })
    await backend.deleteKnowledgeDocument(id)
    selectedDocumentId.value = null
  } catch (error) {
    reportMutationError(error)
  }
}

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
</style>
