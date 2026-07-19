<template>
  <div class="safe-mermaid">
    <div v-if="canRender" class="mermaid-container">
      <div ref="mermaidEl" class="mermaid-render"></div>
    </div>
    <div v-else class="outline-fallback">
      <div class="fallback-notice">{{ t('components.safeMermaid.unavailableNotice') }}</div>
      <pre class="outline-text">{{ outlineText }}</pre>
    </div>
    <div class="outline-section">
      <details>
        <summary>{{ t('components.safeMermaid.textOutline') }}</summary>
        <pre class="outline-text">{{ outlineText }}</pre>
      </details>
    </div>
  </div>
</template>

<script lang="ts">
let safeMermaidSequence = 0;
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = defineProps<{
  content: string;
  outline?: string;
}>();

const componentId = `safe-mermaid-${++safeMermaidSequence}`;
const mermaidEl = ref<HTMLElement | null>(null);
const renderFailed = ref(false);
let renderVersion = 0;

const MAX_SOURCE_CHARACTERS = 20_000;
const MAX_SOURCE_LINES = 250;
const MAX_NODES = 200;
const MAX_EDGES = 300;
const SAFE_PREFIX = /^(flowchart|graph)(?:\s|$)/;
const UNSAFE_PATTERNS = [
  /%%\s*\{/i,
  /\bclick\b/i,
  /\bhref\b/i,
  /javascript:/i,
  /htmlLabels/i,
  /securityLevel/i,
  /<\/?(?:script|iframe|object|embed|foreignObject)/i,
  /on(?:error|load|click)\s*=/i,
];

const mermaidCode = computed(() => {
  const lines = props.content.replace(/\r\n?/g, "\n").split("\n");
  const startIndex = lines.findIndex(
    line => line.trim().startsWith("flowchart") || line.trim().startsWith("graph"),
  );
  if (startIndex < 0) return "";
  const endIndex = lines.findIndex((line, index) => index > startIndex && /^##\s/.test(line));
  return lines.slice(startIndex, endIndex > startIndex ? endIndex : undefined).join("\n").trim();
});

const safeToRender = computed(() => {
  const normalized = props.content.replace(/\r\n?/g, "\n");
  if (!mermaidCode.value || normalized.length > MAX_SOURCE_CHARACTERS) return false;
  if (normalized.split("\n").length > MAX_SOURCE_LINES) return false;
  if (!SAFE_PREFIX.test(mermaidCode.value)) return false;
  if (UNSAFE_PATTERNS.some(pattern => pattern.test(normalized))) return false;
  const edgeCount = (mermaidCode.value.match(/-->|---|-.->|==>/g) || []).length;
  if (edgeCount > MAX_EDGES) return false;
  const nodeIds = new Set<string>();
  const edgePattern = /([A-Za-z_][A-Za-z0-9_-]*)\s*(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})?\s*(?:-->|---|-.->|==>)\s*([A-Za-z_][A-Za-z0-9_-]*)/g;
  for (const match of mermaidCode.value.matchAll(edgePattern)) {
    nodeIds.add(match[1]);
    nodeIds.add(match[2]);
  }
  const definitionPattern = /(?:^|[;\n])\s*([A-Za-z_][A-Za-z0-9_-]*)\s*[\[({]/g;
  for (const match of mermaidCode.value.matchAll(definitionPattern)) nodeIds.add(match[1]);
  return nodeIds.size <= MAX_NODES;
});

const canRender = computed(() => safeToRender.value && !renderFailed.value);

const outlineText = computed(() => {
  if (props.outline) return props.outline;
  const match = props.content.match(/##\s*\u5927\u7eb2\n([\s\S]*?)(?=\n##|$)/);
  return match ? match[1].trim() : t('components.safeMermaid.outlineUnavailableTitle');
});

const ALLOWED_SVG_TAGS = new Set([
  "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline",
  "polygon", "text", "tspan", "defs", "marker", "style",
]);
const ALLOWED_SVG_ATTRIBUTES = new Set([
  "xmlns", "viewbox", "preserveaspectratio", "id", "class", "d", "fill",
  "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "opacity",
  "fill-opacity", "stroke-opacity", "transform", "x", "y", "x1", "y1",
  "x2", "y2", "cx", "cy", "r", "rx", "ry", "width", "height", "points",
  "marker-start", "marker-end", "marker-mid", "refx", "refy", "markerwidth",
  "markerheight", "orient", "text-anchor", "dominant-baseline", "font-family",
  "font-size", "font-weight", "style",
]);

function safeSvgAttribute(name: string, value: string): boolean {
  const lowerName = name.toLowerCase();
  const lowerValue = value.toLowerCase().replace(/\s+/g, "");
  if (!ALLOWED_SVG_ATTRIBUTES.has(lowerName) || lowerName.startsWith("on")) return false;
  if (/javascript:|data:|file:|https?:|vbscript:|@import/.test(lowerValue)) return false;
  if (lowerValue.includes("url(") && !/^url\(#[A-Za-z_][A-Za-z0-9_.:-]*\)$/.test(value.trim())) return false;
  return true;
}

function sanitizeSvg(svg: string): string | null {
  const parser = new DOMParser();
  const document = parser.parseFromString(svg, "image/svg+xml");
  if (document.querySelector("parsererror")) return null;
  const root = document.documentElement;
  if (root.localName.toLowerCase() !== "svg") return null;
  for (const element of Array.from(root.querySelectorAll("*"))) {
    const tag = element.localName.toLowerCase();
    if (!ALLOWED_SVG_TAGS.has(tag)) {
      element.remove();
      continue;
    }
    if (tag === "style" && /url\s*\(|@import|javascript:|https?:/i.test(element.textContent || "")) {
      element.remove();
      continue;
    }
    for (const attribute of Array.from(element.attributes)) {
      if (!safeSvgAttribute(attribute.name, attribute.value)) {
        element.removeAttribute(attribute.name);
      }
    }
  }
  for (const attribute of Array.from(root.attributes)) {
    if (!safeSvgAttribute(attribute.name, attribute.value)) root.removeAttribute(attribute.name);
  }
  return new XMLSerializer().serializeToString(root);
}

async function renderDiagram() {
  const version = ++renderVersion;
  renderFailed.value = false;
  if (!safeToRender.value) return;
  await nextTick();
  if (!mermaidEl.value || version !== renderVersion) return;
  mermaidEl.value.textContent = "";
  try {
    const mermaid = await import("mermaid");
    mermaid.default.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "default",
    });
    const { svg } = await mermaid.default.render(
      `${componentId}-${version}`,
      mermaidCode.value,
    );
    if (version !== renderVersion || !mermaidEl.value) return;
    const safeSvg = sanitizeSvg(svg);
    if (!safeSvg) throw new Error("unsafe svg");
    mermaidEl.value.innerHTML = safeSvg;
  } catch {
    if (version === renderVersion) {
      if (mermaidEl.value) mermaidEl.value.textContent = "";
      renderFailed.value = true;
    }
  }
}

watch([mermaidCode, safeToRender], renderDiagram, { immediate: true, flush: "post" });
onBeforeUnmount(() => { renderVersion += 1; });
</script>

<style scoped>
.safe-mermaid { min-width: 0; margin: 8px 0; }
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
.fallback-notice, .outline-section summary { overflow-wrap: anywhere; }
.outline-text {
  font-size: 13px; font-family: monospace;
  white-space: pre-wrap; margin: 4px 0;
}
.outline-section { margin-top: 8px; }
.outline-section summary { cursor: pointer; font-size: 13px; color: #6b7280; }
</style>
