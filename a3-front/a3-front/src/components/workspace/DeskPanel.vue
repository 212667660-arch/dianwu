<template>
  <aside class="desk-panel" data-test="desk-panel">
    <div class="desk-title"><span class="rule" /> <span>书桌</span> <span class="rule" /></div>

    <section class="desk-card desk-card-paper">
      <div class="desk-card-heading"><span>今天的学习</span><span class="desk-date">{{ todayLabel }}</span></div>
      <div class="desk-metrics">
        <div><strong>{{ Math.round((mastery || 0) * 100) }}%</strong><span>掌握度</span></div>
        <div><strong>{{ resourceCount }}</strong><span>份资源</span></div>
      </div>
      <el-progress :percentage="Math.round((mastery || 0) * 100)" :show-text="false" :stroke-width="6" />
    </section>

    <section class="desk-card desk-card-note">
      <div class="desk-card-heading"><span>便签</span><el-icon><EditPen /></el-icon></div>
      <textarea v-model="note" maxlength="120" aria-label="学习便签" placeholder="写下一句想提醒自己的话…" />
      <small>{{ note.length }}/120</small>
    </section>

    <section v-if="nextAction" class="desk-card desk-card-action">
      <div class="desk-card-heading"><span>下一步</span><el-icon><ArrowRight /></el-icon></div>
      <strong>{{ nextAction.knowledge_point || '学习诊断' }}</strong>
      <p>{{ nextAction.reason }}</p>
      <button data-test="suggested-action" type="button" @click="$emit('use-suggestion', nextAction.suggested_request)">开始这一小步 <span>↗</span></button>
    </section>
    <div v-else class="desk-empty">今天的书桌还很安静。<br />等你放下一点学习的痕迹。</div>

    <section v-if="sources?.length" class="desk-sources">
      <div class="desk-card-heading"><span>参考资料</span><span>{{ sources.length }}</span></div>
      <a v-for="source in sources.slice(0, 3)" :key="source.url" :href="source.url" target="_blank" rel="noreferrer">{{ source.title }}</a>
    </section>

    <div class="widget-slot" aria-label="桌宠功能预留">桌宠功能预留</div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowRight, EditPen } from '@element-plus/icons-vue'
import type { NextAction, SourceItem } from '@/api'

const props = defineProps<{
  nextAction?: NextAction | null
  mastery?: number
  resourceCount?: number
  sources?: SourceItem[]
}>()

defineEmits<{ (event: 'use-suggestion', prompt: string): void }>()

const note = ref('')
const todayLabel = computed(() => new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date()))

onMounted(() => { note.value = localStorage.getItem('a3-companion-note') || '' })
watch(note, value => localStorage.setItem('a3-companion-note', value.slice(0, 120)))
</script>

<style scoped lang="scss">
.desk-panel { min-width: 0; height: 100%; padding: 24px 18px 18px; overflow: auto; background: rgba(252, 249, 243, .9); border-left: 1px solid rgba(231, 220, 207, .74); }
.desk-title { display: flex; align-items: center; justify-content: center; gap: 9px; margin: 2px 0 17px; color: #6f8c8e; font-family: Georgia, "Times New Roman", serif; font-size: 17px; }
.rule { width: 28px; height: 1px; background: #d8cfc2; }
.desk-card { margin-bottom: 14px; padding: 14px; border: 1px solid #ebe1d4; border-radius: 14px; box-shadow: 0 8px 20px rgba(103, 81, 49, .035); }
.desk-card-paper { background: #fffdfa; }
.desk-card-note { background: #fff8de; border-color: #f1e5be; transform: rotate(.25deg); }
.desk-card-action { background: #edf4f0; border-color: #d8e8e1; }
.desk-card-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 13px; color: #837769; font-size: 11px; }
.desk-card-heading .el-icon { color: #9b8d7d; }
.desk-date { color: #b0a396; font-size: 10px; }
.desk-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 13px; }
.desk-metrics strong, .desk-metrics span { display: block; }
.desk-metrics strong { color: #4d777b; font-size: 22px; font-weight: 650; }
.desk-metrics span { margin-top: 2px; color: #9a8c7e; font-size: 10px; }
.desk-card-note textarea { width: 100%; min-height: 76px; resize: vertical; color: #6a5d4f; line-height: 1.6; background: transparent; border: 0; outline: 0; }
.desk-card-note textarea::placeholder { color: #c0aa7d; }
.desk-card-note small { display: block; color: #c0aa7d; font-size: 10px; text-align: right; }
.desk-card-action > strong { color: #4f7778; font-size: 14px; }
.desk-card-action p { margin: 6px 0 12px; color: #829391; font-size: 11px; line-height: 1.55; }
.desk-card-action button { padding: 0; color: #5e8986; font-size: 11px; background: transparent; border: 0; cursor: pointer; }
.desk-card-action button span { margin-left: 4px; }
.desk-empty { padding: 32px 12px; color: #b2a79a; font-family: Georgia, "Times New Roman", serif; font-size: 12px; line-height: 1.8; text-align: center; }
.desk-sources { padding-top: 4px; }
.desk-sources .desk-card-heading { margin-bottom: 8px; }
.desk-sources a { display: block; padding: 7px 0; overflow: hidden; color: #7f9795; font-size: 11px; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; border-bottom: 1px solid #eee6dc; }
.widget-slot { margin-top: 20px; color: #c2b6a8; font-size: 10px; text-align: center; }
</style>
