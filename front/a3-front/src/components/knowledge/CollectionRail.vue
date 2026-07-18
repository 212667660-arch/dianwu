<template>
  <aside class="knowledge-collection-rail" data-testid="collection-rail">
    <div class="knowledge-pane-heading"><div><span>资料花园</span><strong>我的集合</strong></div><button type="button" aria-label="新建知识集合" @click="$emit('create')">＋</button></div>
    <div class="collection-list">
      <article v-for="item in collections" :key="item.id" class="collection-wrap" :class="{ active: selectedId === item.id }"><button type="button" class="collection-card" :aria-label="`打开集合 ${item.name}`" @click="$emit('select', item.id)"><i :style="{ background: item.color }" /><span><strong>{{ item.name }}</strong><small>{{ item.document_count }} 份资料 · {{ item.description || '安静地收好学习材料' }}</small></span></button><div class="collection-actions"><button type="button" :aria-label="`重命名集合 ${item.name}`" @click="$emit('rename',item)">✎</button><button type="button" :aria-label="`删除集合 ${item.name}`" @click="$emit('delete',item)">×</button></div></article>
      <p v-if="!collections.length" class="knowledge-empty">还没有集合。<br>从一门正在学习的课开始吧。</p>
    </div>
    <p class="local-note">⌂ 文件只保存在这台设备</p>
  </aside>
</template>
<script setup lang="ts">
import type { KnowledgeCollection } from '@/api'
defineProps<{ collections: KnowledgeCollection[]; selectedId: number | null }>()
defineEmits<{ (event: 'select', id: number): void; (event: 'create'): void; (event:'rename',item:KnowledgeCollection):void; (event:'delete',item:KnowledgeCollection):void }>()
</script>
<style scoped lang="scss">
.knowledge-collection-rail{height:100%;padding:18px 14px;background:rgba(248,242,233,.86);border-right:1px solid var(--line)}
.knowledge-pane-heading{display:flex;align-items:center;justify-content:space-between;padding:2px 5px 16px}.knowledge-pane-heading span,.knowledge-pane-heading strong{display:block}.knowledge-pane-heading span{color:var(--muted);font-size:10px;letter-spacing:.14em}.knowledge-pane-heading strong{margin-top:3px;font-family:Georgia,"Songti SC",serif;font-size:18px}.knowledge-pane-heading button{width:30px;height:30px;color:#6e9292;background:#eef5f1;border:1px solid #dce9e4;border-radius:50%;cursor:pointer}.collection-list{display:grid;gap:7px}.collection-wrap{position:relative;border:1px solid transparent;border-radius:11px}.collection-wrap:hover,.collection-wrap.active{background:#fffaf4;border-color:#e5d8ca}.collection-wrap.active{box-shadow:0 8px 18px rgba(91,71,48,.05)}.collection-card{display:flex;align-items:center;gap:9px;width:100%;padding:11px 42px 11px 9px;color:#75695e;text-align:left;background:transparent;border:0;border-radius:11px;cursor:pointer}.collection-card i{width:8px;height:32px;border-radius:9px}.collection-card span{min-width:0}.collection-card strong,.collection-card small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.collection-card strong{font-size:12px}.collection-card small{max-width:140px;margin-top:4px;color:#a09284;font-size:9px}.collection-actions{position:absolute;top:8px;right:5px;display:grid;grid-template-columns:1fr 1fr}.collection-actions button{width:20px;height:22px;padding:0;color:#a09284;background:transparent;border:0;cursor:pointer}.collection-actions button:hover{color:#5f8588}.knowledge-empty,.local-note{color:#a09284;font-size:10px;line-height:1.7}.knowledge-empty{padding:24px 8px;text-align:center}.local-note{margin:24px 5px 0;padding-top:13px;border-top:1px solid #e8ddd0}
</style>
