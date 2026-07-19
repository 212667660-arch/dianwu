<template>
  <div class="resource-menu">
    <label class="menu-label">{{ t('components.resourceMenu.resourceType') }}</label>
    <select data-testid="resource-mode" :value="modelKey" @change="onChange" class="menu-select">
      <option value="bundle">{{ t('components.resourceMenu.resource') }}</option>
      <option disabled>──────────</option>
      <option v-for="type in resourceTypes" :key="type" :value="`single:${type}`">{{ t(resourceTypeKey(type)) }}</option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { ArtifactType, ResourceSelection } from "@/api/types";
import { resourceTypeKey } from "@/i18n/display-maps";

const { t } = useI18n();
const resourceTypes: ArtifactType[] = ["course_explanation", "mind_map", "question_bank", "extended_reading", "adaptive_practice"];

const props = defineProps<{
  modelValue?: ResourceSelection;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: ResourceSelection];
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
    emit("update:modelValue", {
      mode: "single",
      resourceType: val.slice(7) as ArtifactType,
    });
  }
}
</script>

<style scoped>
.resource-menu {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.menu-label {
  font-size: 14px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.menu-select {
  min-width: 0;
  padding: 4px 8px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  background: #fff;
}
</style>
