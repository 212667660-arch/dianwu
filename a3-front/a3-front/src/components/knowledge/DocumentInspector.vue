<template>
  <aside class="document-inspector" data-testid="document-inspector">
    <div v-if="!document" class="inspector-empty">选一份资料，看看它被整理成了什么模样。</div>
    <template v-else>
      <div class="inspector-mark">{{ document.extension.replace('.','').toUpperCase() }}</div><h2>{{ document.display_name }}</h2><p class="inspector-status">{{ statusText }}</p>
      <dl><div><dt>篇幅</dt><dd>{{ extent }}</dd></div><div><dt>可检索片段</dt><dd>{{ document.chunk_count }} 条</dd></div><div><dt>解析器</dt><dd>{{ document.parser_version || '等待解析' }}</dd></div></dl>
      <div v-if="document.status==='OCR_REQUIRED'" class="ocr-note"><strong>需要本地 OCR</strong><p>这是一份图片型 PDF。安装通过许可校验的本地 OCR 包后即可继续，原文件不会上传。</p></div>
      <div class="inspector-actions"><button v-if="document.status==='COMPLETED'" type="button" :aria-label="`总结知识点 ${document.display_name}`" @click="$emit('summarize',document.id)">总结知识点</button><button v-if="document.status==='COMPLETED'" type="button" :aria-label="`生成例题与步骤 ${document.display_name}`" @click="$emit('worked-example',document.id)">生成例题与步骤</button><button v-if="desktopAvailable&&document.status==='COMPLETED'" type="button" :aria-label="`预览（本地阅读器） ${document.display_name}`" @click="$emit('open',document.id)">预览（本地阅读器）</button><button type="button" :aria-label="`重新解析 ${document.display_name}`" @click="$emit('rebuild',document.id)">重新解析</button><button class="danger" type="button" :aria-label="`删除 ${document.display_name}`" @click="$emit('delete',document.id)">删除资料</button></div>
    </template>
  </aside>
</template>
<script setup lang="ts">
import { computed } from 'vue';import type{KnowledgeDocument}from '@/api'
const props=defineProps<{document:KnowledgeDocument|null;desktopAvailable:boolean}>();defineEmits<{(event:'open',id:number):void;(event:'summarize',id:number):void;(event:'worked-example',id:number):void;(event:'rebuild',id:number):void;(event:'delete',id:number):void}>()
const extent=computed(()=>props.document?.page_count?`${props.document.page_count} 页`:props.document?.slide_count?`${props.document.slide_count} 张幻灯片`:props.document?.sheet_count?`${props.document.sheet_count} 个工作表`:'—')
const statusText=computed(()=>props.document?.status==='COMPLETED'?'已经安静地整理好了':props.document?.status==='OCR_REQUIRED'?'等待你启用本地识别':'仍在整理中')
</script>
<style scoped lang="scss">
.document-inspector{height:100%;padding:24px 20px;background:rgba(250,246,239,.86);border-left:1px solid var(--line)}.inspector-empty{min-height:300px;display:grid;place-items:center;color:#a29486;text-align:center;line-height:1.8}.inspector-mark{width:52px;height:64px;display:grid;place-items:center;color:#fff;background:#668f93;border-radius:10px 10px 10px 4px;font-size:9px}.document-inspector h2{margin:16px 0 5px;font-family:Georgia,"Songti SC",serif;font-size:18px;overflow-wrap:anywhere}.inspector-status{margin:0;color:#899f9c;font-size:10px}.document-inspector dl{margin:22px 0}.document-inspector dl div{display:flex;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid #e8ddd1;font-size:10px}.document-inspector dt{color:#9d8f81}.document-inspector dd{margin:0;color:#665d55}.ocr-note{padding:12px;color:#8a6536;background:#fff4df;border:1px solid #ecd9b8;border-radius:10px}.ocr-note strong{font-size:11px}.ocr-note p{margin:5px 0 0;font-size:9px;line-height:1.7}.inspector-actions{display:grid;gap:7px;margin-top:20px}.inspector-actions button{min-height:34px;color:#5f8588;background:#f1f7f4;border:1px solid #d9e8e2;border-radius:9px;cursor:pointer}.inspector-actions .danger{color:#a05d65;background:#fff6f5;border-color:#edd9d8}
</style>
