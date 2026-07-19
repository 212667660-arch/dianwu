<template>
  <section class="page">
    <div class="page-heading">
      <div><h1>{{ t('views.learningPath.title') }}</h1><p>{{ t('views.learningPath.adaptiveOrderingDescription') }}</p></div>
      <el-button :icon="Refresh" @click="backend.refreshSession()">{{ t('views.learningPath.retry') }}</el-button>
    </div>

    <article v-if="backend.nextAction" class="decision-band">
      <div class="decision-icon"><el-icon><Guide /></el-icon></div>
      <div class="decision-copy">
        <span>{{ t('views.learningPath.recommendationCurrent') }}</span><h2>{{ actionLabel(backend.nextAction.action) }}</h2>
        <p>{{ backend.nextAction.reason }}</p>
      </div>
      <div class="decision-target"><span>{{ backend.nextAction.knowledge_point || t('views.learningPath.diagnosisLabel') }}</span><strong>{{ backend.nextAction.recommended_difficulty }}</strong></div>
      <el-button type="primary" @click="startAction">{{ t('views.learningPath.start') }}</el-button>
    </article>

    <div class="grid-2 path-grid">
      <article class="panel">
        <div class="panel-header"><h2>{{ t('views.learningPath.knowledgePointPath') }}</h2><span class="muted">{{ t('views.learningPath.knowledgePointCount', { count: points.length }) }}</span></div>
        <div class="panel-body">
          <div v-for="(point, index) in points" :key="point.id" class="path-row">
            <div class="path-index">{{ index + 1 }}</div>
            <div class="path-copy">
              <div><strong>{{ point.name }}</strong><span>{{ masteryLabel(point.mastery_label) }}</span></div>
              <el-progress :percentage="Math.round(point.mastery_score * 100)" :stroke-width="7" />
              <p>{{ point.attempts ? t('views.learningPath.attemptSummary', { attempts: point.attempts, correctStreak: point.correct_streak }) : t('views.learningPath.firstPracticePending') }}</p>
            </div>
          </div>
          <div v-if="!points.length" class="empty-block"><p>{{ t('views.learningPath.pathGeneratedAfterProfile') }}</p></div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header"><h2>{{ t('views.learningPath.reviewSchedule') }}</h2><span class="muted">{{ t('views.learningPath.reviewCount', { count: backend.reviews.length }) }}</span></div>
        <div class="panel-body">
          <div v-for="review in backend.reviews" :key="review.id" class="review-row list-row">
            <div class="review-date"><strong>{{ day(review.due_at) }}</strong><span>{{ month(review.due_at) }}</span></div>
            <div><strong>{{ review.knowledge_point }}</strong><p>{{ review.reason === 'ANSWER_INCORRECT' ? t('views.learningPath.immediateRemediation') : t('views.learningPath.reviewTitle', { intervalDays: review.interval_days }) }}</p></div>
            <span class="status-pill" :class="isDue(review.due_at) ? 'bad' : 'good'">{{ isDue(review.due_at) ? t('views.learningPath.due') : t('views.learningPath.scheduled') }}</span>
          </div>
          <div v-if="!backend.reviews.length" class="empty-block"><p>{{ t('views.learningPath.noReviewTasks') }}</p></div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Guide, Refresh } from '@element-plus/icons-vue'
import { useBackendStore } from '@/stores/backend'
import { actionLabel, masteryLabel } from '@/utils/protocol'

const { t, locale } = useI18n()

const backend = useBackendStore()
const router = useRouter()
const points = computed(() => backend.progress?.knowledge_points || [])
const date = (value: string) => new Date(value)
const day = (value: string) => String(date(value).getDate()).padStart(2, '0')
const month = (value: string) => new Intl.DateTimeFormat(locale.value, { month: 'short' }).format(date(value))
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
