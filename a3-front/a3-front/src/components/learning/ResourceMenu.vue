<template>
  <div class="resource-menu">
    <label class="menu-label">资源类型</label>
    <select :value="modelKey" @change="onChange" class="menu-select">
      <option value="bundle">📦 完整资源包</option>
      <option disabled>──────────</option>
      <option value="single:course_explanation">📖 课程讲解</option>
      <option value="single:mind_map">🧠 思维导图</option>
      <option value="single:question_bank">📝 题库</option>
      <option value="single:extended_reading">📚 延伸阅读</option>
      <option value="single:adaptive_practice">🔬 自适应练习</option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  modelValue?: { mode: string; resourceType?: string };
}>();

const emit = defineEmits<{
  "update:modelValue": [value: { mode: string; resourceType?: string }];
}>();

const modelKey = computed(() => {
  if (!props.modelValue || props.modelValue.mode === "bundle") return "bundle";
  return `single:${props.modelValue.resourceType}`;
});

function onChange(e: Event) {
  const target = e.target as HTMLSelectElement;
  const val = target.value;
  if (val === "bundle") {
    emit("update:modelValue", { mode: "bundle" });
  } else if (val.startsWith("single:")) {
    emit("update:modelValue", { mode: "single", resourceType: val.slice(7) });
  }
}
</script>

<style scoped>
.resource-menu {
  display: flex;
  align-items: center;
  gap: 8px;
}
.menu-label {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}
.menu-select {
  padding: 4px 8px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  background: #fff;
}
</style>
