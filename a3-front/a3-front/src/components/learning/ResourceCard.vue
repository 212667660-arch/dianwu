<template>
  <div class="resource-card" :class="{ collapsed: !expanded, failed: artifact.status === 'FAILED' }">
    <div class="card-header" @click="toggle">
      <span class="card-type">{{ typeLabel }}</span>
      <span class="card-title">{{ artifact.title }}</span>
      <span class="card-status">
        {{ artifact.status === 'SUCCEEDED' ? '✅' : artifact.status === 'FAILED' ? '❌' : '⏹' }}
      </span>
      <span class="card-score">质量: {{ artifact.quality_score }}</span>
      <button class="card-toggle">{{ expanded ? '收起' : '展开' }}</button>
    </div>
    <div v-if="expanded" class="card-body">
      <div v-if="artifact.status !== 'SUCCEEDED'" class="card-error">
        <p v-if="publicSafetyMessage" class="safety-message">{{ publicSafetyMessage }}</p>
        <template v-else>
          <p>错误码: {{ artifact.error_code }}</p>
          <p v-if="artifact.quality_issues.length">问题: {{ artifact.quality_issues.join(', ') }}</p>
        </template>
        <button v-if="artifact.retryable" class="retry-btn" :disabled="retrying" @click.stop="$emit('retry', artifact.artifact_id)">
          {{ retrying ? '重试中…' : '重试' }}
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
        <button @click.stop="copyContent" class="copy-btn">复制 Markdown</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { ResourceArtifact } from "@/api/types";
import SafeMarkdown from "./SafeMarkdown.vue";
import SafeMermaid from "./SafeMermaid.vue";

const props = defineProps<{
  artifact: ResourceArtifact;
  retrying?: boolean;
}>();

defineEmits<{ retry: [artifactId: string] }>();

const expanded = ref(false);

const typeLabels: Record<string, string> = {
  course_explanation: "📖 课程讲解",
  mind_map: "🧠 思维导图",
  question_bank: "📝 题库",
  extended_reading: "📚 延伸阅读",
  adaptive_practice: "🔬 自适应练习",
};

const typeLabel = computed(() => typeLabels[props.artifact.type] || props.artifact.type);

const publicSafetyMessage = computed(() => {
  switch (props.artifact.error_code) {
    case "CONTENT_ARTIFACT_BLOCKED":
    case "CONTENT_CITATION_NOT_ALLOWED":
      return "内容未通过安全检查，请修改请求后重试。";
    case "SAFETY_REVIEW_UNAVAILABLE":
      return "内容安全审核暂时不可用，请稍后重试。";
    case "UNSAFE_RENDER_PAYLOAD":
      return "内容包含不安全的展示结构，已停止渲染。";
    default:
      return "";
  }
});

const mindMapOutline = computed(() => {
  const outline = props.artifact.type_specific_data?.outline;
  return typeof outline === "string" ? outline : undefined;
});

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
