<template>
  <div class="model-selection">
    <button
      type="button"
      class="selection-trigger"
      data-testid="model-selection-trigger"
      :disabled="busy || profiles.length === 0"
      @click="open = !open"
    >
      <span class="selection-dot" />
      {{ triggerLabel }}
      <span class="chevron">⌄</span>
    </button>

    <div v-if="open" class="selection-popover" role="dialog" aria-label="选择本空间模型与思考强度">
      <header>
        <div><span>LEARNING SPACE</span><strong>本空间的思考方式</strong></div>
        <button type="button" aria-label="关闭模型选择" @click="open = false">×</button>
      </header>

      <label>
        <span>模型配置</span>
        <select data-testid="profile-selection" :value="draftProfileValue" @change="changeProfile(($event.target as HTMLSelectElement).value)">
          <option value="__auto__">跟随全局默认</option>
          <option v-for="profile in enabledProfiles" :key="profile.id" :value="profile.id">{{ profile.label }}</option>
        </select>
      </label>

      <label>
        <span>模型</span>
        <select v-model="draft.model_id" data-testid="model-selection" :disabled="draft.profile_mode === 'auto'">
          <option v-for="model in selectedProfile?.models || []" :key="model.id" :value="model.id">{{ model.label }}</option>
        </select>
      </label>

      <fieldset>
        <legend>思考强度</legend>
        <label v-for="effort in efforts" :key="effort.value" :class="{ disabled: !supportsEffort(effort.value) }">
          <input
            v-model="draft.reasoning_effort"
            type="radio"
            :value="effort.value"
            :disabled="!supportsEffort(effort.value)"
            :data-testid="`reasoning-${effort.value}`"
          >
          <span><strong>{{ effort.label }}</strong><small>{{ effort.note }}</small></span>
        </label>
      </fieldset>

      <fieldset class="failover-choice">
        <legend>本空间自动备用</legend>
        <label><input v-model="draft.failover_override" type="radio" value="inherit"> 跟随全局</label>
        <label><input v-model="draft.failover_override" type="radio" value="on"> 开启</label>
        <label><input v-model="draft.failover_override" type="radio" value="off"> 关闭</label>
      </fieldset>

      <footer>
        <span>这里只保存脱敏 ID 与档位，不保存密钥。</span>
        <button type="button" data-testid="model-selection-save" :disabled="busy" @click="save">应用到本空间</button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ModelProfilePolicy, ModelProfileSummary, ReasoningEffort, SessionModelPreference, SessionModelPreferenceInput } from '@/api'

const props = defineProps<{
  profiles: ModelProfileSummary[]
  policy: ModelProfilePolicy | null
  preference: SessionModelPreference | null
  busy: boolean
  effectiveProfileId?: string
  effectiveModelId?: string
  effectiveReasoningEffort?: ReasoningEffort
}>()
const emit = defineEmits<{ save: [input: SessionModelPreferenceInput] }>()
const open = ref(false)
const draft = reactive<SessionModelPreferenceInput>(defaultPreference())

const efforts: Array<{ value: ReasoningEffort; label: string; note: string }> = [
  { value: 'auto', label: '自动', note: '交给模型决定' },
  { value: 'off', label: '关闭', note: '不发送显式推理参数' },
  { value: 'low', label: '轻量', note: '更快回应' },
  { value: 'medium', label: '标准', note: '速度与深度平衡' },
  { value: 'high', label: '深入', note: '适合复杂问题' },
  { value: 'xhigh', label: '极高', note: '只在模型明确支持时使用' },
]
const effortOrder: ReasoningEffort[] = ['off', 'low', 'medium', 'high', 'xhigh']
const enabledProfiles = computed(() => props.profiles.filter(profile => profile.enabled))
const selectedProfile = computed(() => {
  const id = draft.profile_mode === 'manual' ? draft.preferred_profile_id : (props.effectiveProfileId || props.policy?.default_profile_id)
  return props.profiles.find(profile => profile.id === id) || enabledProfiles.value[0]
})
const selectedModel = computed(() => {
  const id = props.effectiveModelId || draft.model_id || selectedProfile.value?.default_model_id
  return selectedProfile.value?.models.find(model => model.id === id)
    || selectedProfile.value?.models.find(model => model.id === selectedProfile.value?.default_model_id)
})
const effectiveEffort = computed(() => props.effectiveReasoningEffort || clampEffort(draft.reasoning_effort, selectedModel.value?.supported_reasoning_efforts || ['auto']))
const triggerLabel = computed(() => `${selectedModel.value?.label || '选择模型'} · ${effortLabel(effectiveEffort.value)}`)
const draftProfileValue = computed(() => draft.profile_mode === 'auto' ? '__auto__' : (draft.preferred_profile_id || '__auto__'))

watch(() => props.preference, value => {
  Object.assign(draft, value ? {
    profile_mode: value.profile_mode,
    preferred_profile_id: value.preferred_profile_id,
    model_id: value.model_id,
    reasoning_effort: value.reasoning_effort,
    failover_override: value.failover_override,
  } : defaultPreference())
}, { immediate: true, deep: true })

function defaultPreference(): SessionModelPreferenceInput {
  return { profile_mode: 'auto', preferred_profile_id: null, model_id: null, reasoning_effort: 'auto', failover_override: 'inherit' }
}

function changeProfile(profileId: string) {
  if (profileId === '__auto__') {
    draft.profile_mode = 'auto'
    draft.preferred_profile_id = null
    draft.model_id = null
    return
  }
  const profile = props.profiles.find(item => item.id === profileId)
  draft.profile_mode = 'manual'
  draft.preferred_profile_id = profileId
  draft.model_id = profile?.default_model_id || null
}

function supportsEffort(effort: ReasoningEffort) {
  return selectedModel.value?.supported_reasoning_efforts.includes(effort) ?? effort === 'auto'
}

function clampEffort(requested: ReasoningEffort, supported: ReasoningEffort[]): ReasoningEffort {
  if (requested === 'auto' || supported.includes(requested)) return requested
  const requestedIndex = effortOrder.indexOf(requested)
  const candidates = supported
    .filter(value => effortOrder.includes(value) && effortOrder.indexOf(value) < requestedIndex)
    .sort((left, right) => effortOrder.indexOf(left) - effortOrder.indexOf(right))
  return candidates[candidates.length - 1] || 'off'
}

function effortLabel(effort: ReasoningEffort) {
  return efforts.find(item => item.value === effort)?.label || effort
}

function save() {
  emit('save', {
    profile_mode: draft.profile_mode,
    preferred_profile_id: draft.profile_mode === 'auto' ? null : draft.preferred_profile_id,
    model_id: draft.profile_mode === 'auto' ? null : draft.model_id,
    reasoning_effort: draft.reasoning_effort,
    failover_override: draft.failover_override,
  })
  open.value = false
}
</script>

<style scoped lang="scss">
.model-selection { position: relative; }
.selection-trigger { display: inline-flex; align-items: center; gap: 6px; min-height: 28px; padding: 4px 9px; border: 1px solid #ddd4c9; border-radius: 999px; color: #6f807c; background: rgba(250, 248, 244, .92); cursor: pointer; font-size: 10px; }
.selection-dot { width: 6px; height: 6px; border-radius: 50%; background: #72a394; box-shadow: 0 0 0 3px rgba(114, 163, 148, .12); }
.chevron { color: #a39588; }
.selection-popover { position: absolute; z-index: 20; left: 0; bottom: calc(100% + 9px); width: min(380px, calc(100vw - 38px)); padding: 17px; border: 1px solid #ded2c5; border-radius: 16px; background: #fffaf4; box-shadow: 0 20px 55px rgba(66, 51, 36, .18); }
header, footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
header div { display: grid; gap: 3px; } header span { color: #719592; font-size: 9px; letter-spacing: .15em; } header strong { font-family: Georgia, "Microsoft YaHei", serif; font-size: 16px; }
header button { border: 0; color: #9b8c7e; background: transparent; cursor: pointer; font-size: 19px; }
.selection-popover > label { display: grid; gap: 5px; margin-top: 12px; color: var(--muted); font-size: 10px; }
select { min-height: 36px; padding: 7px 9px; border: 1px solid var(--line); border-radius: 9px; color: var(--ink); background: #fffdfa; }
fieldset { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; margin: 13px 0 0; padding: 11px; border: 1px dashed var(--line); border-radius: 11px; }
legend { padding: 0 5px; color: var(--muted); font-size: 10px; }
fieldset label { display: flex; align-items: flex-start; gap: 6px; font-size: 10px; }
fieldset label span { display: grid; gap: 2px; } fieldset small { color: var(--muted); font-size: 8px; line-height: 1.4; }
fieldset label.disabled { opacity: .42; }
.failover-choice { grid-template-columns: repeat(3, auto); }
footer { margin-top: 13px; padding-top: 12px; border-top: 1px solid var(--line); }
footer span { max-width: 190px; color: var(--muted); font-size: 8px; line-height: 1.5; }
footer button { min-height: 32px; padding: 0 12px; border: 0; border-radius: 9px; color: #fff; background: #668f93; cursor: pointer; font-size: 10px; }
button:disabled, select:disabled { cursor: not-allowed; opacity: .48; }
@media (max-width: 560px) { .selection-popover { position: fixed; left: 12px; right: 12px; bottom: 88px; width: auto; } }
</style>
