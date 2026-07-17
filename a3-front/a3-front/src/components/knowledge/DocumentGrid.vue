<template>
  <section class="knowledge-document-pane" data-testid="document-grid" @dragenter.prevent="$emit('drag-active', true)" @dragover.prevent @dragleave.prevent="$emit('drag-active', false)" @drop.prevent="$emit('drop', $event)">
    <div v-if="!documents.length" class="document-empty"><span>一页空白，也是一种邀请</span><strong>把讲义、笔记或表格放进来吧</strong></div>
    <div v-else class="document-grid">
      <article v-for="item in documents" :key="item.id" class="document-card" :class="{ selected: selectedId === item.id }">
        <button type="button" class="document-select" :aria-label="`查看文档 ${item.display_name}`" @click="$emit('select', item.id)" @keydown.enter.prevent="$emit('select', item.id)" @keydown.space.prevent="$emit('select', item.id)">
          <span class="file-mark">{{ item.extension.replace('.', '').toUpperCase() }}</span><span class="file-copy"><strong>{{ item.display_name }}</strong><small>{{ statusLabel(item.status) }} · {{ sizeLabel(item.byte_size) }}</small></span>
        </button>
        <div v-if="activeJobFor(item.id)" class="import-progress"><div role="progressbar" :aria-label="`${item.display_name} 导入进度`" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="activeJobFor(item.id)!.progress"><i :style="{ width: `${activeJobFor(item.id)!.progress}%` }" /></div><span>{{ progressLabel(activeJobFor(item.id)!) }}</span><button type="button" :aria-label="`取消 ${item.display_name} 的导入`" @click="cancelJob(activeJobFor(item.id)!.id)">取消</button></div>
        <div v-else-if="failedOcrJobFor(item.id)" class="ocr-failure" role="status"><span>{{ failedOcrLabel(failedOcrJobFor(item.id)!) }}</span><small>{{ etaLabel(failedOcrJobFor(item.id)!) }} · 失败页：{{ failedOcrJobFor(item.id)!.failed_pages.join('、') }}</small><button type="button" :aria-label="`重试 ${item.display_name} 的失败 OCR 页面`" @click="retryJob?.(failedOcrJobFor(item.id)!.id)">只重试失败页</button></div>
      </article>
    </div>
  </section>
</template>
<script setup lang="ts">
import type { KnowledgeDocument, KnowledgeImportJob } from '@/api'
const props=defineProps<{documents:KnowledgeDocument[];jobs:KnowledgeImportJob[];selectedId:number|null;cancelJob:(id:number)=>unknown;retryJob?:(id:number)=>unknown}>()
defineEmits<{(event:'select',id:number):void;(event:'drop',value:DragEvent):void;(event:'drag-active',value:boolean):void}>()
function activeJobFor(documentId:number){return props.jobs.find(job=>job.document_id===documentId&&['QUEUED','VALIDATING','PARSING','OCR_RUNNING','INDEXING'].includes(job.status))}
function failedOcrJobFor(documentId:number){return props.jobs.find(job=>job.document_id===documentId&&job.status==='FAILED'&&job.retryable&&job.failed_pages.length>0)}
function progressLabel(job:KnowledgeImportJob){return job.current_page&&job.page_count?`第 ${job.current_page}/${job.page_count} 页 · ${job.progress}%`:`${job.progress}%`}
function etaLabel(job:KnowledgeImportJob){return job.eta_seconds===null?'剩余时间计算中':`约 ${job.eta_seconds} 秒`}
function failedOcrLabel(job:KnowledgeImportJob){return job.current_page&&job.page_count?`第 ${job.current_page}/${job.page_count} 页识别后需要处理`:'部分页面识别失败'}
function sizeLabel(bytes:number){if(bytes<1024*1024)return `${Math.max(1,Math.round(bytes/1024))} KB`;return `${(bytes/1024/1024).toFixed(1)} MB`}
function statusLabel(status:string){return ({COMPLETED:'已整理',PARSING:'正在阅读',INDEXING:'正在编目',OCR_REQUIRED:'等待 OCR',FAILED:'需要处理',QUEUED:'等待导入'} as Record<string,string>)[status]||status}
</script>
<style scoped lang="scss">
.knowledge-document-pane{min-width:0;padding:18px}.document-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:11px}.document-card{padding:10px;background:rgba(255,253,249,.88);border:1px solid #e7ddd1;border-radius:13px;transition:.18s}.document-card:hover,.document-card.selected{border-color:#9db7b5;box-shadow:0 10px 22px rgba(88,72,53,.06);transform:translateY(-1px)}.document-select{display:flex;align-items:center;gap:11px;width:100%;padding:2px;color:inherit;text-align:left;background:transparent;border:0;cursor:pointer}.document-select:focus-visible{outline:3px solid rgba(107,151,155,.3);outline-offset:4px}.file-mark{width:42px;height:52px;display:grid;place-items:center;flex:none;color:#fff;background:linear-gradient(145deg,#7fa3a1,#587f84);border-radius:8px 8px 8px 3px;font-size:8px;letter-spacing:.08em}.file-copy{min-width:0}.file-copy strong,.file-copy small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file-copy strong{font-size:12px}.file-copy small{margin-top:6px;color:var(--muted);font-size:9px}.import-progress{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:7px;margin-top:10px;color:#9b8d80;font-size:9px}.import-progress [role=progressbar]{height:5px;overflow:hidden;background:#eee5da;border-radius:9px}.import-progress i{display:block;height:100%;background:#7ca49c;transition:width .2s}.import-progress button{padding:0;color:#ad6670;background:transparent;border:0;cursor:pointer}.document-empty{min-height:330px;display:grid;place-content:center;text-align:center;color:#aa9d90}.document-empty span,.document-empty strong{display:block}.document-empty strong{margin-top:8px;color:#7e7266;font-family:Georgia,"Songti SC",serif;font-size:17px;font-weight:500}@media(max-width:760px){.document-grid{grid-template-columns:1fr}.knowledge-document-pane{padding:12px}}@media(prefers-reduced-motion:reduce){.document-card,.import-progress i{transition:none}.document-card:hover{transform:none}}
.ocr-failure{display:grid;gap:4px;margin-top:10px;padding:8px;color:#8a6536;background:#fff4df;border-radius:8px;font-size:9px}.ocr-failure small{color:#9b7d57}.ocr-failure button{justify-self:start;padding:0;color:#8b5b45;background:transparent;border:0;text-decoration:underline;cursor:pointer}
</style>
