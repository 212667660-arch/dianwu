<template>
  <div class="safe-mermaid">
    <div v-if="safeToRender" class="mermaid-container">
      <div ref="mermaidEl" class="mermaid-render"></div>
    </div>
    <div v-else class="outline-fallback">
      <div class="fallback-notice">⚠ Mermaid 渲染不可用，显示文本大纲</div>
      <pre class="outline-text">{{ outlineText }}</pre>
    </div>
    <div class="outline-section">
      <details>
        <summary>📋 文本大纲</summary>
        <pre class="outline-text">{{ outlineText }}</pre>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

const props = defineProps<{
  content: string;
  outline?: string;
}>();

const mermaidEl = ref<HTMLElement | null>(null);

const SAFE_PREFIX = /^(flowchart|graph)\s/;
const UNSAFE_PATTERNS = [
  /<script/i,
  /javascript:/i,
  /onerror\s*=/i,
  /onclick\s*=/i,
  /<iframe/i,
  /<object/i,
  /<embed/i,
  /click\s+.*href/i,
];

const mermaidCode = computed(() => {
  const lines = props.content.split("\n");
  const startIdx = lines.findIndex(
    (l) => l.trim().startsWith("flowchart") || l.trim().startsWith("graph")
  );
  if (startIdx < 0) return "";
  const endIdx = lines.findIndex((l, i) => i > startIdx && /^##\s/.test(l));
  return lines.slice(startIdx, endIdx > 0 ? endIdx : undefined).join("\n").trim();
});

const safeToRender = computed(() => {
  if (!mermaidCode.value) return false;
  if (!SAFE_PREFIX.test(mermaidCode.value.trim())) return false;
  return !UNSAFE_PATTERNS.some((p) => p.test(mermaidCode.value));
});

const outlineText = computed(() => {
  if (props.outline) return props.outline;
  const match = props.content.match(/##\s*大纲\n([\s\S]*?)(?=\n##|$)/);
  return match ? match[1].trim() : "大纲不可用";
});

onMounted(async () => {
  if (safeToRender.value && mermaidEl.value) {
    try {
      const mermaid = await import("mermaid");
      mermaid.default.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "default",
      });
      const { svg } = await mermaid.default.render(
        `mermaid-${Date.now()}`,
        mermaidCode.value
      );
      mermaidEl.value.innerHTML = svg;
    } catch {
      // render failure -> fallback handled by safeToRender
    }
  }
});
</script>

<style scoped>
.safe-mermaid { margin: 8px 0; }
.mermaid-container {
  overflow-x: auto; padding: 8px;
  background: #f9fafb; border-radius: 6px;
  border: 1px solid #e5e7eb;
}
.outline-fallback {
  padding: 8px; background: #fef3c7;
  border-radius: 6px; border: 1px solid #fbbf24;
}
.fallback-notice { font-size: 13px; color: #92400e; margin-bottom: 4px; }
.outline-text {
  font-size: 13px; font-family: monospace;
  white-space: pre-wrap; margin: 4px 0;
}
.outline-section { margin-top: 8px; }
.outline-section summary { cursor: pointer; font-size: 13px; color: #6b7280; }
</style>