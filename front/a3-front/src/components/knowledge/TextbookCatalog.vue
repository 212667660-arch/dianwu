<template>
  <section class="textbook-catalog" aria-label="官方数学教材目录">
    <div class="catalog-heading">
      <div><span>OFFICIAL TEXTBOOKS</span><strong>初高中数学教材</strong></div>
      <div class="stage-tabs">
        <button type="button" aria-label="选择初中教材" :class="{ active: stage === '初中' }" @click="stage = '初中'">初中</button>
        <button type="button" aria-label="选择高中教材" :class="{ active: stage === '高中' }" @click="stage = '高中'">高中</button>
      </div>
    </div>
    <div class="catalog-list">
      <article v-for="item in visibleItems" :key="item.source_id">
        <div><small>{{ item.publisher }} · {{ item.edition }}</small><h2>{{ item.title }}</h2><p>{{ item.grade }} · {{ item.semester }}</p></div>
        <div class="catalog-action"><button type="button" :disabled="!desktopAvailable" :aria-label="`在线阅读 ${item.title}`" @click="$emit('open', item)">人教社官方在线阅读</button><span>{{ item.license_note }}</span></div>
      </article>
      <p v-if="!visibleItems.length" class="catalog-empty">当前筛选下暂无已核验教材来源。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TextbookCatalogItem } from '@/api'

const props = withDefaults(defineProps<{ items: TextbookCatalogItem[]; desktopAvailable?: boolean }>(), {
  desktopAvailable: true,
})
defineEmits<{ (event: 'open', item: TextbookCatalogItem): void }>()

const stage = ref<'初中' | '高中'>('初中')
const visibleItems = computed(() => props.items.filter(item => item.stage === stage.value && item.subject === '数学'))
</script>

<style scoped lang="scss">
.textbook-catalog{margin-bottom:14px;padding:14px 16px;background:rgba(248,244,236,.82);border:1px solid var(--line);border-radius:14px}.catalog-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.catalog-heading span,.catalog-heading strong{display:block}.catalog-heading span{color:#799995;font-size:8px;letter-spacing:.15em}.catalog-heading strong{margin-top:3px;font-family:Georgia,"Songti SC",serif;font-size:15px}.stage-tabs{display:flex;gap:5px}.stage-tabs button{min-width:48px;height:28px;color:#7d7166;background:#fffaf4;border:1px solid #e3d8cb;border-radius:8px;cursor:pointer}.stage-tabs button.active{color:#fff;background:#668f93;border-color:#668f93}.catalog-list{margin-top:10px}.catalog-list article{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:11px 0;border-top:1px solid #eadfd3}.catalog-list small,.catalog-list p,.catalog-action span{color:#998b7e;font-size:9px}.catalog-list h2{margin:3px 0;font-size:12px}.catalog-list p{margin:0}.catalog-action{max-width:360px;display:grid;justify-items:end;gap:4px;text-align:right}.catalog-action button{min-height:31px;padding:0 11px;color:#fff;background:#6e9291;border:0;border-radius:8px;cursor:pointer}.catalog-action button:disabled{color:#a79a8d;background:#e6ddd3;cursor:not-allowed}.catalog-empty{margin:12px 0 0}@media(max-width:760px){.catalog-list article{align-items:stretch;flex-direction:column}.catalog-action{justify-items:start;text-align:left}}
</style>
