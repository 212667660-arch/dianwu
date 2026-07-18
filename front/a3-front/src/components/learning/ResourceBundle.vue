<template>
  <div class="resource-bundle">
    <div class="bundle-header">
      <h3 class="bundle-topic">{{ bundle.topic }}</h3>
      <span class="bundle-status" :class="bundle.status">{{ bundle.status }}</span>
      <span class="bundle-quality">综合质量: {{ bundle.aggregate_quality }}</span>
    </div>
    <div class="bundle-artifacts">
      <ResourceCard
        v-for="artifact in bundle.artifacts"
        :key="artifact.artifact_id"
        :artifact="artifact"
        :retrying="retryingTypes.includes(artifact.type)"
        @retry="() => $emit('retry-artifact', artifact.type)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import ResourceCard from "./ResourceCard.vue";
import type { ArtifactType, ResourceBundle } from "@/api/types";

withDefaults(defineProps<{
  bundle: ResourceBundle;
  retryingTypes?: ArtifactType[];
}>(), { retryingTypes: () => [] });

defineEmits<{ "retry-artifact": [artifactType: ArtifactType] }>();
</script>

<style scoped>
.resource-bundle { padding: 12px 0; }
.bundle-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.bundle-topic { font-size: 18px; margin: 0; }
.bundle-status { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.bundle-status.COMPLETED { background: #d1fae5; color: #065f46; }
.bundle-status.PARTIAL { background: #fef3c7; color: #92400e; }
.bundle-status.FAILED { background: #fee2e2; color: #991b1b; }
.bundle-status.CANCELLED { background: #e5e7eb; color: #374151; }
.bundle-quality { font-size: 13px; color: #6b7280; }
</style>
