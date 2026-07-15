<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <h1>学习总览</h1>
        <p>基于当前会话的画像、掌握度与复习安排</p>
      </div>
      <div class="toolbar">
        <el-button :icon="Refresh" :loading="backend.loading" @click="backend.refreshAll()">同步</el-button>
        <el-button type="primary" :icon="ChatLineRound" @click="router.push('/tutor')">继续学习</el-button>
      </div>
    </div>

    <div class="metric-grid">
      <div class="metric"><span>会话阶段</span><strong>{{ stateLabel }}</strong></div>
      <div class="metric"><span>知识点</span><strong>{{ backend.progress?.knowledge_points.length || 0 }}</strong></div>
      <div class="metric"><span>答题正确率</span><strong>{{ accuracyLabel }}</strong></div>
      <div class="metric"><span>已生成资源</span><strong>{{ backend.resources.length }}</strong></div>
    </div>

    <div v-if="backend.nextAction" class="next-action">
      <div>
        <span class="eyebrow">推荐下一步</span>
        <h2>{{ actionLabel(backend.nextAction.action) }}</h2>
        <p>{{ backend.nextAction.reason }}</p>
      </div>
      <div class="action-meta">
        <span>{{ backend.nextAction.knowledge_point || '学习诊断' }}</span>
        <el-tag effect="plain">{{ backend.nextAction.recommended_difficulty }}</el-tag>
        <el-button type="primary" @click="startSuggested">开始</el-button>
      </div>
    </div>

    <div class="grid-2 content-grid">
      <article class="panel">
        <div class="panel-header"><h2>知识点掌握度</h2><span class="muted">按薄弱程度排序</span></div>
        <div class="panel-body">
          <template v-if="knowledgePoints.length">
            <div v-for="point in knowledgePoints" :key="point.id" class="knowledge-row">
              <div class="knowledge-title">
                <strong>{{ point.name }}</strong>
                <span>{{ masteryLabel(point.mastery_label) }} · {{ point.correct_attempts }}/{{ point.attempts }}</span>
              </div>
              <el-progress :percentage="Math.round(point.mastery_score * 100)" :stroke-width="8" :show-text="false" />
            </div>
          </template>
          <div v-else class="empty-block">
            <div><p>完成诊断后显示知识点掌握度</p><el-button text type="primary" @click="router.push('/tutor')">开始诊断</el-button></div>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header"><h2>最近资源</h2><span class="muted">质量校验结果</span></div>
        <div class="panel-body resource-list">
          <template v-if="recentResources.length">
            <div v-for="resource in recentResources" :key="resource.id" class="list-row resource-row">
              <div>
                <strong>{{ resource.topic }}</strong>
                <p>画像 v{{ resource.profile_version }} · {{ resource.questions.length }} 道练习</p>
              </div>
              <span class="quality" :class="resource.quality_score >= 80 ? 'good' : 'warn'">{{ resource.quality_score }} 分</span>
            </div>
          </template>
          <div v-else class="empty-block"><p>暂无已生成资源</p></div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ChatLineRound, Refresh } from '@element-plus/icons-vue'
import { useBackendStore } from '@/stores/backend'
import { actionLabel, masteryLabel } from '@/utils/protocol'

const backend = useBackendStore()
const router = useRouter()
const stateLabel = computed(() => backend.session?.state || (backend.live ? '等待开始' : '服务离线'))
const accuracyLabel = computed(() => backend.progress?.total_attempts ? `${Math.round(backend.progress.accuracy * 100)}%` : '--')
const knowledgePoints = computed(() => backend.progress?.knowledge_points || [])
const recentResources = computed(() => [...backend.resources].slice(-4).reverse())

function startSuggested() {
  router.push({ path: '/tutor', query: { prompt: backend.nextAction?.suggested_request || '', at: Date.now().toString(36) } })
}
</script>

<style scoped lang="scss">
.next-action {
  display: flex; align-items: center; justify-content: space-between; gap: 20px;
  margin-bottom: 16px; padding: 18px; color: #fff; background: #2e4a4b; border-left: 5px solid #51b7a9;
  h2 { margin: 3px 0 5px; font-size: 20px; letter-spacing: 0; }
  p { margin: 0; color: #d4e0df; font-size: 13px; }
}
.eyebrow { color: #9ed7cf; font-size: 11px; }
.action-meta { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 9px; }
.content-grid { align-items: start; }
.knowledge-row { padding: 11px 0; border-bottom: 1px solid var(--line); }
.knowledge-row:last-child { border-bottom: 0; }
.knowledge-title { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 7px; }
.knowledge-title span, .resource-row p { color: var(--muted); font-size: 12px; }
.resource-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.resource-row p { margin: 3px 0 0; }
.quality { flex: 0 0 auto; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
.quality.good { color: var(--accent); background: var(--accent-soft); }
.quality.warn { color: var(--warning); background: #fff3df; }
@media (max-width: 760px) { .next-action { align-items: flex-start; flex-direction: column; } .action-meta { justify-content: flex-start; } }
</style>
