<template>
  <section class="page">
    <div class="page-heading">
      <div><h1>学习路径</h1><p>根据真实答题记录动态调整顺序与难度</p></div>
      <el-button :icon="Refresh" @click="backend.refreshSession()">重新计算</el-button>
    </div>

    <article v-if="backend.nextAction" class="decision-band">
      <div class="decision-icon"><el-icon><Guide /></el-icon></div>
      <div class="decision-copy">
        <span>当前建议</span><h2>{{ actionLabel(backend.nextAction.action) }}</h2>
        <p>{{ backend.nextAction.reason }}</p>
      </div>
      <div class="decision-target"><span>{{ backend.nextAction.knowledge_point || '学习诊断' }}</span><strong>{{ backend.nextAction.recommended_difficulty }}</strong></div>
      <el-button type="primary" @click="startAction">开始任务</el-button>
    </article>

    <div class="grid-2 path-grid">
      <article class="panel">
        <div class="panel-header"><h2>知识点路径</h2><span class="muted">{{ points.length }} 个知识点</span></div>
        <div class="panel-body">
          <div v-for="(point, index) in points" :key="point.id" class="path-row">
            <div class="path-index">{{ index + 1 }}</div>
            <div class="path-copy">
              <div><strong>{{ point.name }}</strong><span>{{ masteryLabel(point.mastery_label) }}</span></div>
              <el-progress :percentage="Math.round(point.mastery_score * 100)" :stroke-width="7" />
              <p>{{ point.attempts ? `已答 ${point.attempts} 次，连续答对 ${point.correct_streak} 次` : '等待首次练习' }}</p>
            </div>
          </div>
          <div v-if="!points.length" class="empty-block"><p>完成画像后自动生成知识点路径</p></div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header"><h2>复习日程</h2><span class="muted">{{ backend.reviews.length }} 项待复习</span></div>
        <div class="panel-body">
          <div v-for="review in backend.reviews" :key="review.id" class="review-row list-row">
            <div class="review-date"><strong>{{ day(review.due_at) }}</strong><span>{{ month(review.due_at) }}</span></div>
            <div><strong>{{ review.knowledge_point }}</strong><p>{{ review.reason === 'ANSWER_INCORRECT' ? '答错后立即巩固' : `间隔 ${review.interval_days} 天复习` }}</p></div>
            <span class="status-pill" :class="isDue(review.due_at) ? 'bad' : 'good'">{{ isDue(review.due_at) ? '已到期' : '已安排' }}</span>
          </div>
          <div v-if="!backend.reviews.length" class="empty-block"><p>暂无待复习任务</p></div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Guide, Refresh } from '@element-plus/icons-vue'
import { useBackendStore } from '@/stores/backend'
import { actionLabel, masteryLabel } from '@/utils/protocol'

const backend = useBackendStore()
const router = useRouter()
const points = computed(() => backend.progress?.knowledge_points || [])
const date = (value: string) => new Date(value)
const day = (value: string) => String(date(value).getDate()).padStart(2, '0')
const month = (value: string) => `${date(value).getMonth() + 1}月`
const isDue = (value: string) => date(value).getTime() <= Date.now()
function startAction() { router.push({ path: '/tutor', query: { prompt: backend.nextAction?.suggested_request || '' } }) }
</script>

<style scoped lang="scss">
.decision-band { display: grid; grid-template-columns: 48px minmax(0, 1fr) auto auto; align-items: center; gap: 16px; margin-bottom: 16px; padding: 18px; color: #fff; background: #2e4a4b; border-left: 5px solid #51b7a9; }
.decision-icon { width: 44px; height: 44px; display: grid; place-items: center; color: #18373a; background: #b9e5df; border-radius: 6px; font-size: 21px; }
.decision-copy span { color: #9ed7cf; font-size: 11px; }
.decision-copy h2 { margin: 2px 0 4px; font-size: 19px; }
.decision-copy p { margin: 0; color: #d4e0df; font-size: 12px; }
.decision-target { text-align: right; }
.decision-target span, .decision-target strong { display: block; }
.decision-target span { color: #d4e0df; font-size: 12px; }
.decision-target strong { margin-top: 3px; }
.path-grid { align-items: start; }
.path-row { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.path-row:last-child { border: 0; }
.path-index { width: 27px; height: 27px; display: grid; place-items: center; color: var(--accent); background: var(--accent-soft); border-radius: 50%; font-size: 11px; }
.path-copy > div { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 7px; }
.path-copy span, .path-copy p, .review-row p { color: var(--muted); font-size: 11px; }
.path-copy p, .review-row p { margin: 4px 0 0; }
.review-row { display: grid; grid-template-columns: 42px minmax(0, 1fr) auto; align-items: center; gap: 12px; }
.review-date { width: 40px; text-align: center; color: var(--accent); }
.review-date strong, .review-date span { display: block; }
.review-date strong { font-size: 17px; }
.review-date span { font-size: 10px; }
@media (max-width: 760px) { .decision-band { grid-template-columns: 44px minmax(0, 1fr); } .decision-target, .decision-band > .el-button { grid-column: 2; text-align: left; justify-self: start; } }
</style>
