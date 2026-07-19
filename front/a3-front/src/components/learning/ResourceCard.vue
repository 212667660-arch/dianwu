<template>
  <div class="resource-card" :class="{ collapsed: !expanded, failed: artifact.status === 'FAILED' }">
    <div class="card-header" @click="toggle">
      <span class="card-type">{{ typeLabel }}</span>
      <span class="card-title">{{ artifact.title }}</span>
      <span class="card-status">
        {{ artifact.status === 'SUCCEEDED' ? '✅' : artifact.status === 'FAILED' ? '❌' : '⏹' }}
      </span>
      <span class="card-score">{{ t('components.resourceCard.quality') }} {{ formatPercent(artifact.quality_score / 100) }}</span>
      <span v-if="answerReview" class="review-badge" :class="answerReview.status.toLowerCase()">{{ t('components.resourceCard.answer') }}{{ reviewLabel }}</span>
      <span v-if="answerReview?.formula_checked && answerReview?.substitution_checked" class="review-detail">{{ t('components.resourceCard.formulaCheck') }}</span>
      <button class="card-toggle">{{ t(expanded ? 'components.resourceCard.collapse' : 'components.resourceCard.expand') }}</button>
    </div>
    <div v-if="expanded" class="card-body">
      <div v-if="artifact.status !== 'SUCCEEDED'" class="card-error">
        <p v-if="publicSafetyMessage" class="safety-message">{{ publicSafetyMessage }}</p>
        <template v-else>
          <p>{{ failureMessage }}</p>
          <p>{{ t('components.resourceCard.errorCodeLabel') }} {{ artifact.error_code }}</p>
          <p v-if="artifact.quality_issues.length">{{ t('components.resourceCard.questionLabel') }} {{ artifact.quality_issues.join(', ') }}</p>
        </template>
        <button v-if="artifact.retryable" class="retry-btn" :disabled="retrying" @click.stop="$emit('retry', artifact.artifact_id)">
          {{ t(retrying ? 'components.resourceCard.retrying' : 'components.resourceBundle.retry') }}
        </button>
      </div>
      <div v-else class="card-content">
        <SafeMermaid
          v-if="artifact.type === 'mind_map'"
          :content="artifact.body"
          :outline="mindMapOutline"
        />
        <SafeMarkdown v-else :content="artifact.body" />
      </div>
      <div v-if="artifact.status === 'SUCCEEDED' && artifact.body" class="card-actions">
        <button @click.stop="copyContent" class="copy-btn">{{ t('components.resourceCard.copyMarkdown') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { ResourceArtifact } from "@/api/types";
import { BackendApiError } from "@/api/transport";
import { resourceTypeKey } from "@/i18n/display-maps";
import { errorMessage } from "@/i18n/errors";
import { formatPercent } from "@/i18n/formatters";
import SafeMarkdown from "./SafeMarkdown.vue";
import SafeMermaid from "./SafeMermaid.vue";

const props = defineProps<{
  artifact: ResourceArtifact;
  retrying?: boolean;
}>();
const { t } = useI18n();

defineEmits<{ retry: [artifactId: string] }>();

const expanded = ref(false);

const typeLabel = computed(() => t(resourceTypeKey(props.artifact.type)));

const publicSafetyMessage = computed(() => {
  switch (props.artifact.error_code) {
    case "CONTENT_ARTIFACT_BLOCKED":
    case "CONTENT_CITATION_NOT_ALLOWED":
      return t('components.resourceCard.securityContentCheck');
    case "SAFETY_REVIEW_UNAVAILABLE":
      return t('components.resourceCard.securityReviewUnavailable');
    case "UNSAFE_RENDER_PAYLOAD":
      return t('components.resourceCard.securityContentStructure');
    default:
      return "";
  }
});

const mindMapOutline = computed(() => {
  const outline = props.artifact.type_specific_data?.outline;
  return typeof outline === "string" ? outline : undefined;
});
const failureMessage = computed(() => props.artifact.error_code
  ? errorMessage(new BackendApiError(0, props.artifact.error_code, '', props.artifact.retryable))
  : t('errors.unknown'));

const answerReview = computed(() => {
  const value = props.artifact.type_specific_data?.answer_review
  if (!value || typeof value !== 'object') return null
  const item = value as Record<string, unknown>
  if (!['PASSED', 'REPAIRED', 'WARNING'].includes(String(item.status))) return null
  return {
    status: String(item.status) as 'PASSED' | 'REPAIRED' | 'WARNING',
    formula_checked: item.formula_checked === true,
    substitution_checked: item.substitution_checked === true,
  }
})
const reviewLabel = computed(() => t({ PASSED: 'components.resourceCard.reviewPassed', REPAIRED: 'components.resourceCard.reviewCorrected', WARNING: 'components.resourceCard.manualReviewRequired' }[answerReview.value?.status || 'PASSED']))

function toggle() {
  expanded.value = !expanded.value;
}

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.artifact.body);
  } catch {
    // fallback silently
  }
}
</script>

<style scoped>
.resource-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;
}
.resource-card.failed {
  border-color: #fca5a5;
  background: #fef2f2;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  flex-wrap: wrap;
}
.card-type { font-size: 13px; color: #6b7280; }
.card-title { font-weight: 600; flex: 1; }
.card-status { font-size: 16px; }
.card-score { font-size: 12px; color: #9ca3af; }
.review-badge,.review-detail{padding:2px 6px;border-radius:999px;font-size:10px}.review-badge{color:#446f67;background:#e5f4ed}.review-badge.repaired{color:#725d35;background:#fff0cf}.review-badge.warning{color:#8c4d49;background:#fde7e4}.review-detail{color:#617b79;background:#edf4f2}
.card-toggle {
  font-size: 12px; padding: 2px 8px;
  border: 1px solid #d1d5db; border-radius: 4px;
  background: #fff; cursor: pointer;
}
.card-body { padding: 0 12px 12px; }
.card-error { color: #dc2626; font-size: 13px; }
.card-actions { display: flex; gap: 8px; margin-top: 8px; }
.copy-btn, .retry-btn {
  font-size: 12px; padding: 4px 10px;
  border: 1px solid #d1d5db; border-radius: 4px;
  background: #f9fafb; cursor: pointer;
}
.retry-btn { background: #fef3c7; border-color: #fbbf24; }
.collapsed .card-body { display: none; }
@media (max-width: 640px) {
  .card-header { flex-direction: column; align-items: flex-start; }
  .card-actions { flex-direction: column; }
}
</style>
