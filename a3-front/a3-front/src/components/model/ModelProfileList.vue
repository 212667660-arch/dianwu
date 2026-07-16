<template>
  <section class="profile-rail" aria-label="模型配置列表">
    <div class="rail-heading">
      <div>
        <span class="eyebrow">连接书架</span>
        <h2>模型配置</h2>
      </div>
      <button class="new-button" type="button" data-testid="profile-create" :disabled="busy" @click="emit('create')">
        ＋ 新建
      </button>
    </div>

    <div v-if="profiles.length === 0" class="empty-rail">
      <span>空</span>
      <p>还没有可用的模型配置。</p>
    </div>

    <article
      v-for="profile in profiles"
      :key="profile.id"
      class="profile-card"
      :class="{ 'is-selected': profile.id === selectedId, 'is-disabled': !profile.enabled }"
      :data-testid="`profile-card-${profile.id}`"
      tabindex="0"
      role="button"
      @click="emit('select', profile)"
      @keydown.enter="emit('select', profile)"
    >
      <div class="card-topline">
        <div class="profile-name">
          <strong>{{ profile.label }}</strong>
          <span>{{ providerLabel(profile.provider) }}</span>
        </div>
        <button
          class="star-button"
          :class="{ active: policy?.default_profile_id === profile.id }"
          type="button"
          :title="policy?.default_profile_id === profile.id ? '当前默认配置' : '设为默认配置'"
          :aria-label="policy?.default_profile_id === profile.id ? '当前默认配置' : `将${profile.label}设为默认配置`"
          :data-testid="`profile-default-${profile.id}`"
          :disabled="busy || !profile.enabled || policy?.default_profile_id === profile.id"
          @click.stop="emit('set-default', profile.id)"
        >
          {{ policy?.default_profile_id === profile.id ? '★ 默认' : '☆' }}
        </button>
      </div>

      <p class="model-name">{{ defaultModel(profile) }}</p>

      <div class="status-row">
        <span v-if="!profile.enabled" class="state-tag muted">已停用</span>
        <span v-else-if="runtime(profile.id)?.needs_attention" class="state-tag danger">需要处理</span>
        <span v-else-if="runtime(profile.id)?.circuit_state === 'open'" class="state-tag warn">冷却中</span>
        <span v-else class="state-tag healthy">可用</span>
        <span v-if="runtime(profile.id)?.circuit_state === 'open'" class="state-tag warn">冷却中</span>
        <span v-if="fallbackNumber(profile.id)" class="fallback-order">备用 {{ fallbackNumber(profile.id) }}</span>
      </div>

      <div class="card-actions">
        <button type="button" :data-testid="`profile-test-${profile.id}`" :disabled="busy" @click.stop="emit('test', profile)">测试</button>
        <button type="button" :data-testid="`profile-toggle-${profile.id}`" :disabled="busy || (profile.enabled && policy?.default_profile_id === profile.id)" @click.stop="emit('toggle-enabled', { profileId: profile.id, enabled: !profile.enabled })">
          {{ profile.enabled ? '停用' : '启用' }}
        </button>
        <button type="button" :data-testid="`profile-duplicate-${profile.id}`" :disabled="busy" @click.stop="emit('duplicate', profile)">复制</button>
        <button type="button" :data-testid="`profile-move-up-${profile.id}`" :disabled="busy || !canMove(profile.id, -1)" @click.stop="emit('move-fallback', { profileId: profile.id, direction: -1 })">↑</button>
        <button type="button" :data-testid="`profile-move-down-${profile.id}`" :disabled="busy || !canMove(profile.id, 1)" @click.stop="emit('move-fallback', { profileId: profile.id, direction: 1 })">↓</button>
        <button class="danger-action" type="button" :data-testid="`profile-delete-${profile.id}`" :disabled="busy || policy?.default_profile_id === profile.id" @click.stop="requestDelete(profile)">删除</button>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import type { ModelProfilePolicy, ModelProfileSummary, ModelRuntimeProfileStatus, ModelRuntimeStatus } from '@/api'

const props = defineProps<{
  profiles: ModelProfileSummary[]
  policy: ModelProfilePolicy | null
  runtimeStatus: ModelRuntimeStatus | null
  selectedId: string
  busy: boolean
}>()

const emit = defineEmits<{
  select: [profile: ModelProfileSummary]
  create: []
  'set-default': [profileId: string]
  'toggle-enabled': [payload: { profileId: string; enabled: boolean }]
  test: [profile: ModelProfileSummary]
  duplicate: [profile: ModelProfileSummary]
  delete: [profileId: string]
  'move-fallback': [payload: { profileId: string; direction: -1 | 1 }]
}>()

function providerLabel(provider: ModelProfileSummary['provider']) {
  return provider === 'anthropic' ? 'Anthropic' : 'OpenAI 兼容'
}

function defaultModel(profile: ModelProfileSummary) {
  return profile.models.find(model => model.id === profile.default_model_id)?.label || profile.default_model_id
}

function runtime(profileId: string): ModelRuntimeProfileStatus | undefined {
  return props.runtimeStatus?.profiles.find(item => item.profile_id === profileId)
}

function fallbackNumber(profileId: string) {
  const index = props.policy?.fallback_profile_ids.indexOf(profileId) ?? -1
  return index >= 0 ? index + 1 : 0
}

function canMove(profileId: string, direction: -1 | 1) {
  const index = props.policy?.fallback_profile_ids.indexOf(profileId) ?? -1
  if (index < 0) return false
  const next = index + direction
  return next >= 0 && next < (props.policy?.fallback_profile_ids.length ?? 0)
}

async function requestDelete(profile: ModelProfileSummary) {
  try {
    await ElMessageBox.confirm(`删除“${profile.label}”？加密凭据和本地配置会一并移除。`, '删除模型配置', { type: 'warning' })
    emit('delete', profile.id)
  } catch {
    // User cancelled the destructive action.
  }
}
</script>

<style scoped lang="scss">
.profile-rail { min-width: 0; padding: 18px; border: 1px solid var(--line); border-radius: 18px; background: rgba(248, 242, 233, .78); }
.rail-heading, .card-topline, .status-row, .card-actions { display: flex; align-items: center; }
.rail-heading { justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.eyebrow { color: var(--accent); font-size: 10px; letter-spacing: .18em; }
h2 { margin: 3px 0 0; font-family: Georgia, "Microsoft YaHei", serif; font-size: 18px; }
.new-button { padding: 8px 12px; border: 1px solid rgba(107, 151, 155, .38); border-radius: 999px; color: #47777a; background: var(--accent-soft); cursor: pointer; }
.empty-rail { display: grid; place-items: center; min-height: 150px; color: var(--muted); text-align: center; }
.empty-rail span { display: grid; place-items: center; width: 46px; height: 46px; border: 1px dashed var(--line); border-radius: 50%; }
.profile-card { margin-top: 10px; padding: 14px; border: 1px solid transparent; border-radius: 15px; background: rgba(255, 253, 250, .88); box-shadow: 0 8px 24px rgba(92, 74, 57, .05); cursor: pointer; transition: .18s ease; }
.profile-card:hover, .profile-card:focus-visible { border-color: rgba(107, 151, 155, .35); outline: none; transform: translateY(-1px); }
.profile-card.is-selected { border-color: rgba(107, 151, 155, .62); box-shadow: 0 12px 28px rgba(83, 130, 132, .12); }
.profile-card.is-disabled { opacity: .72; }
.card-topline { justify-content: space-between; gap: 8px; }
.profile-name { display: grid; min-width: 0; gap: 2px; }
.profile-name strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.profile-name span, .model-name { color: var(--muted); font-size: 11px; }
.star-button { border: 0; color: #a77c3d; background: transparent; cursor: pointer; }
.star-button.active { padding: 4px 7px; border-radius: 999px; background: #fbf0d9; }
.model-name { margin: 9px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-row { min-height: 22px; gap: 6px; flex-wrap: wrap; }
.state-tag, .fallback-order { padding: 3px 7px; border-radius: 999px; font-size: 10px; }
.state-tag.healthy { color: #4c7e70; background: #e7f2eb; }
.state-tag.warn { color: #9a6d2f; background: #fbefd9; }
.state-tag.danger { color: #a4534d; background: #f7e3df; }
.state-tag.muted, .fallback-order { color: var(--muted); background: #efebe5; }
.card-actions { gap: 4px; margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--line); }
.card-actions button { min-width: 30px; padding: 5px 7px; border: 0; border-radius: 7px; color: var(--muted); background: transparent; cursor: pointer; font-size: 11px; }
.card-actions button:hover:not(:disabled) { color: var(--ink); background: var(--surface-soft); }
.card-actions .danger-action { margin-left: auto; color: #a45a52; }
button:disabled { cursor: not-allowed; opacity: .45; }
</style>
