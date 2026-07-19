<template>
  <section class="profile-editor" :aria-label="t('components.modelProfileEditor.modelProfileEdit')">
    <div class="editor-heading">
      <div>
        <span class="eyebrow">{{ t(profile ? 'components.modelProfileEditor.inProgress' : 'components.modelProfileEditor.connection') }}</span>
        <h2>{{ profile ? t('components.modelProfileEditor.edit', { name: profile.label }) : t('components.modelProfileEditor.modelProfileCreate') }}</h2>
      </div>
      <span class="key-state">{{ t(profile?.api_key_configured ? 'components.modelProfileEditor.apiKeySave' : 'components.modelProfileEditor.apiKeyRequired') }}</span>
    </div>

    <div class="form-section two-columns">
      <label>
        <span>{{ t('components.modelProfileEditor.profile') }}</span>
        <input v-model="draft.id" data-testid="profile-id" maxlength="64" :disabled="Boolean(profile)" autocomplete="off" :placeholder="t('components.modelProfileEditor.profileIdExample')">
        <small>{{ t('components.modelProfileEditor.workspacePreferenceHint') }}</small>
      </label>
      <label>
        <span>{{ t('components.modelProfileEditor.nameTitle') }}</span>
        <input v-model="draft.label" data-testid="profile-label" maxlength="64" autocomplete="off" :placeholder="t('components.modelProfileEditor.model')">
      </label>
      <label>
        <span>{{ t('components.modelProfileEditor.serviceType') }}</span>
        <select v-model="draft.provider" data-testid="profile-provider">
          <option value="openai">{{ t('components.modelProfileEditor.openAiCompatible') }}</option>
          <option value="anthropic">Anthropic Messages</option>
        </select>
      </label>
      <label>
        <span>{{ t('components.modelProfileEditor.timeoutSeconds') }}</span>
        <input v-model.number="draft.request_timeout_seconds" data-testid="profile-timeout" type="number" min="5" max="300">
      </label>
    </div>

    <div class="form-section">
      <label>
        <span>{{ t('components.modelProfileEditor.apiUrl') }}</span>
        <input v-model="draft.base_url" data-testid="profile-base-url" maxlength="512" autocomplete="off" placeholder="https://api.example.com/v1">
      </label>
      <label>
        <span>{{ t('components.modelProfileEditor.apiKey') }}</span>
        <input v-model="draft.api_key" data-testid="profile-api-key" type="password" maxlength="512" autocomplete="new-password" :placeholder="keyPlaceholder">
        <small>{{ t(profile?.api_key_configured ? 'components.modelProfileEditor.apiKeyRetentionHint' : 'components.modelProfileEditor.newProfileApiKeyHint') }}</small>
      </label>
      <label v-if="draft.provider === 'anthropic'">
        <span>{{ t('components.modelProfileEditor.version') }}</span>
        <input v-model="draft.anthropic_version" data-testid="profile-anthropic-version" maxlength="32">
      </label>
    </div>

    <div class="model-section">
      <div class="section-heading">
        <div>
          <span class="eyebrow">{{ t('components.modelProfileEditor.capabilities') }}</span>
          <h3>{{ t('components.modelProfileEditor.modelReasoning') }}</h3>
        </div>
        <button type="button" :disabled="busy || draft.models.length >= 64" @click="addModel">{{ t('components.modelProfileEditor.modelTitle') }}</button>
      </div>

      <article v-for="(model, index) in draft.models" :key="`${model.id}-${index}`" class="model-card">
        <div class="model-card-heading">
          <strong>{{ t('components.modelProfileEditor.modelAction', { index: formatNumber(index + 1) }) }}</strong>
          <label class="default-choice">
            <input v-model="draft.default_model_id" type="radio" :value="model.id">
            {{ t('components.modelProfileEditor.defaultModel') }}
          </label>
          <button v-if="draft.models.length > 1" type="button" @click="removeModel(index)">{{ t('common.actions.remove') }}</button>
        </div>
        <div class="model-grid">
          <label>
            <span>{{ t('components.modelProfileEditor.modelDescription') }}</span>
            <input v-model="model.id" :data-testid="`model-${index}-id`" maxlength="128" autocomplete="off">
          </label>
          <label>
            <span>{{ t('components.modelProfileEditor.modelLabel') }}</span>
            <input v-model="model.provider_model_name" :data-testid="`model-${index}-provider-name`" maxlength="128" autocomplete="off">
          </label>
          <label>
            <span>{{ t('components.modelProfileEditor.displayName') }}</span>
            <input v-model="model.label" :data-testid="`model-${index}-label`" maxlength="128" autocomplete="off">
          </label>
          <label>
            <span>{{ t('components.modelProfileEditor.maxOutputTokens') }}</span>
            <input v-model.number="model.max_output_tokens" :data-testid="`model-${index}-tokens`" type="number" min="512" max="32768">
          </label>
          <label class="adapter-field">
            <span>{{ t('components.modelProfileEditor.reasoning') }}</span>
            <select v-model="model.reasoning_adapter" :data-testid="`model-${index}-adapter`">
              <option v-for="adapter in reasoningAdapters" :key="adapter.value" :value="adapter.value">{{ adapter.label }}</option>
            </select>
          </label>
        </div>
        <fieldset class="effort-fieldset">
          <legend>{{ t('components.modelProfileEditor.reasoningTitle') }}</legend>
          <label v-for="effort in reasoningEfforts" :key="effort.value">
            <input
              v-model="model.supported_reasoning_efforts"
              type="checkbox"
              :value="effort.value"
              :data-testid="`model-${index}-effort-${effort.value}`"
            >
            {{ effort.label }}
          </label>
        </fieldset>
      </article>
    </div>

    <div v-if="feedback.error" class="feedback error" role="alert">{{ feedback.error }}</div>
    <div v-if="feedback.success" class="feedback success" role="status">{{ feedback.success }}</div>

    <div class="editor-actions">
      <span>{{ t('components.modelProfileEditor.connectionRetryTest') }}</span>
      <button type="button" data-testid="profile-test" :disabled="busy" @click="runTest">
        {{ t(activeAction === 'test' ? 'components.modelProfileEditor.inProgressTitle' : 'components.modelProfileEditor.testConnection') }}
      </button>
      <button class="primary-action" type="button" data-testid="profile-save" :disabled="!canSave" @click="runSave">
        {{ t(activeAction === 'save' ? 'common.state.saving' : 'components.modelProfileEditor.securitySave') }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { errorMessage, type ModelDefinition, type ModelProfileInput, type ModelProfileSummary, type ReasoningAdapter, type ReasoningEffort } from '@/api'
import { useBackendStore } from '@/stores/backend'
import { reasoningEffortKey } from '@/i18n/display-maps'
import { formatNumber } from '@/i18n/formatters'

const { t } = useI18n()

const props = defineProps<{ profile: ModelProfileSummary | null; seedProfile?: ModelProfileSummary | null }>()
const emit = defineEmits<{ saved: [profileId: string] }>()
const backend = useBackendStore()
const activeAction = ref<'test' | 'save' | ''>('')
const testedSignature = ref('')
const feedback = reactive({ success: '', error: '' })

const reasoningAdapters = computed<Array<{ value: ReasoningAdapter; label: string }>>(() => [
  { value: 'none', label: t('components.modelProfileEditor.reasoningDescription') },
  { value: 'openai_reasoning_effort', label: 'OpenAI reasoning_effort' },
  { value: 'anthropic_thinking', label: 'Anthropic thinking' },
])
const reasoningEfforts = computed<Array<{ value: ReasoningEffort; label: string }>>(() =>
  (['auto', 'off', 'low', 'medium', 'high', 'xhigh'] as ReasoningEffort[]).map(value => ({ value, label: t(reasoningEffortKey(value)) })),
)

const draft = reactive<ModelProfileInput>(emptyDraft())
const busy = computed(() => backend.modelProfileBusy || Boolean(activeAction.value))
const keyPlaceholder = computed(() => t(props.profile?.api_key_configured ? 'components.modelProfileEditor.apiKeyRetainPlaceholder' : 'components.modelProfileEditor.apiKeyPlaceholder'))
const currentSignature = computed(() => JSON.stringify(candidate()))
const canSave = computed(() => Boolean(testedSignature.value && testedSignature.value === currentSignature.value && !busy.value))

watch(
  () => [props.profile, props.seedProfile] as const,
  ([profile, seedProfile]) => resetDraft(profile, seedProfile || null),
  { immediate: true },
)
watch(draft, () => {
  if (testedSignature.value && testedSignature.value !== currentSignature.value) {
    testedSignature.value = ''
    feedback.success = ''
  }
}, { deep: true, flush: 'sync' })

function emptyModel(index = 1): ModelDefinition {
  return {
    id: `model-${index}`,
    provider_model_name: '',
    label: `${String.fromCodePoint(0x6a21, 0x578b)} ${index}`,
    max_output_tokens: 4096,
    supported_reasoning_efforts: ['auto'],
    reasoning_adapter: 'none',
  }
}

function emptyDraft(): ModelProfileInput {
  return {
    id: '', label: '', enabled: true, provider: 'openai', base_url: 'https://api.deepseek.com', api_key: '',
    anthropic_version: '2023-06-01', request_timeout_seconds: 60, default_model_id: 'model-1', models: [emptyModel()],
  }
}

function resetDraft(profile: ModelProfileSummary | null, seedProfile: ModelProfileSummary | null) {
  const source = profile || seedProfile
  const value = source
    ? { ...source, api_key: '', models: source.models.map(model => ({ ...model, supported_reasoning_efforts: [...model.supported_reasoning_efforts] })) }
    : emptyDraft()
  Object.assign(draft, value)
  draft.models = value.models
  testedSignature.value = ''
  activeAction.value = ''
  feedback.error = ''
  feedback.success = ''
}

function candidate(): ModelProfileInput {
  return {
    id: draft.id.trim(),
    label: draft.label.trim(),
    enabled: draft.enabled,
    provider: draft.provider,
    base_url: draft.base_url.trim(),
    api_key: draft.api_key.trim(),
    anthropic_version: draft.anthropic_version.trim(),
    request_timeout_seconds: Number(draft.request_timeout_seconds),
    default_model_id: draft.default_model_id,
    models: draft.models.map(model => ({
      id: model.id.trim(),
      provider_model_name: model.provider_model_name.trim(),
      label: model.label.trim(),
      max_output_tokens: Number(model.max_output_tokens),
      supported_reasoning_efforts: [...model.supported_reasoning_efforts],
      reasoning_adapter: model.reasoning_adapter,
    })),
  }
}

function validate(value: ModelProfileInput) {
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(value.id)) return t('components.modelProfileEditor.profileTitle')
  if (!value.label) return t('components.modelProfileEditor.profileName')
  if (!/^https?:\/\//i.test(value.base_url)) return t('components.modelProfileEditor.apiUrlValidation')
  if (!props.profile?.api_key_configured && !value.api_key) return t('components.modelProfileEditor.profileDescription')
  if (!value.anthropic_version) return t('components.modelProfileEditor.versionTitle')
  if (!Number.isFinite(value.request_timeout_seconds) || value.request_timeout_seconds < 5 || value.request_timeout_seconds > 300) return t('components.modelProfileEditor.timeoutValidation')
  if (!value.models.length) return t('components.modelProfileEditor.modelStatus')
  const ids = new Set<string>()
  for (const model of value.models) {
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(model.id)) return t('components.modelProfileEditor.modelNotice')
    if (ids.has(model.id)) return t('components.modelProfileEditor.modelPrompt')
    ids.add(model.id)
    if (!model.provider_model_name || !model.label) return t('components.modelProfileEditor.modelName')
    if (!Number.isInteger(model.max_output_tokens) || model.max_output_tokens < 512 || model.max_output_tokens > 32768) return t('components.modelProfileEditor.maxOutputTokensValidation')
    if (!model.supported_reasoning_efforts.includes('auto')) return t('components.modelProfileEditor.modelReasoningAutomatic')
    if (!reasoningAdapters.value.some(adapter => adapter.value === model.reasoning_adapter)) return t('components.modelProfileEditor.securityReasoning')
    if (model.supported_reasoning_efforts.some(effort => !reasoningEfforts.value.some(item => item.value === effort))) return t('components.modelProfileEditor.securityReasoningTitle')
  }
  if (!ids.has(value.default_model_id)) return t('components.modelProfileEditor.modelDefaultSelect')
  return ''
}

async function runTest() {
  const value = candidate()
  const signature = JSON.stringify(value)
  const validationError = validate(value)
  testedSignature.value = ''
  feedback.success = ''
  feedback.error = validationError
  if (validationError) return
  activeAction.value = 'test'
  try {
    const result = await backend.testModelProfile(value)
    if (signature === currentSignature.value) {
      testedSignature.value = signature
      feedback.success = t('components.modelProfileEditor.connectionTitle', { latencyMs: formatNumber(result.latency_ms) })
    } else {
      feedback.error = t('components.modelProfileEditor.connectionProfileRetryTest')
    }
  } catch (error) {
    draft.api_key = ''
    feedback.error = errorMessage(error)
  } finally {
    activeAction.value = ''
  }
}

async function runSave() {
  if (!canSave.value) return
  const value = candidate()
  activeAction.value = 'save'
  feedback.error = ''
  try {
    await backend.upsertModelProfile(value)
    draft.api_key = ''
    testedSignature.value = ''
    feedback.success = t('components.modelProfileEditor.profileEnvironmentSaveCurrentApplication')
    emit('saved', value.id)
  } catch (error) {
    draft.api_key = ''
    testedSignature.value = ''
    feedback.success = ''
    feedback.error = errorMessage(error)
  } finally {
    activeAction.value = ''
  }
}

function addModel() {
  const model = emptyModel(draft.models.length + 1)
  draft.models.push(model)
}

function removeModel(index: number) {
  const removed = draft.models[index]
  draft.models.splice(index, 1)
  if (removed?.id === draft.default_model_id) draft.default_model_id = draft.models[0]?.id || ''
}

onBeforeUnmount(() => {
  draft.api_key = ''
  testedSignature.value = ''
})
</script>

<style scoped lang="scss">
.profile-editor { min-width: 0; padding: 22px; border: 1px solid var(--line); border-radius: 18px; background: rgba(255, 253, 250, .94); box-shadow: 0 18px 48px rgba(91, 72, 55, .07); }
.editor-heading, .section-heading, .model-card-heading, .editor-actions { display: flex; align-items: center; }
.editor-heading, .section-heading { justify-content: space-between; gap: 16px; }
.eyebrow { color: var(--accent); font-size: 10px; letter-spacing: .18em; }
h2, h3 { margin: 4px 0 0; font-family: Georgia, "Microsoft YaHei", serif; }
h2 { font-size: 21px; } h3 { font-size: 16px; }
.key-state { padding: 5px 9px; border-radius: 999px; color: #5e857d; background: var(--accent-soft); font-size: 10px; }
.form-section { display: grid; gap: 13px; margin-top: 18px; }
.two-columns, .model-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
label { display: grid; gap: 6px; color: var(--muted); font-size: 11px; }
label > span, legend { color: var(--ink); font-size: 11px; }
input, select { width: 100%; min-height: 38px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 9px; color: var(--ink); background: #fffdfa; outline: none; }
input:focus, select:focus { border-color: rgba(107, 151, 155, .72); box-shadow: 0 0 0 3px rgba(107, 151, 155, .1); }
small { line-height: 1.5; }
.model-section { margin-top: 22px; padding-top: 18px; border-top: 1px dashed var(--line); }
.section-heading button, .model-card-heading button { padding: 6px 9px; border: 1px solid var(--line); border-radius: 8px; color: var(--muted); background: var(--surface); cursor: pointer; }
.model-card { margin-top: 13px; padding: 15px; border: 1px solid var(--line); border-radius: 14px; background: rgba(248, 242, 233, .5); }
.model-card-heading { gap: 12px; margin-bottom: 12px; }
.model-card-heading button { margin-left: auto; color: #a45a52; }
.default-choice { display: flex; align-items: center; gap: 5px; }
.default-choice input { width: auto; min-height: auto; }
.model-grid { display: grid; gap: 12px; }
.adapter-field { grid-column: 1 / -1; }
.effort-fieldset { display: flex; gap: 8px 14px; flex-wrap: wrap; margin: 13px 0 0; padding: 11px; border: 1px dashed var(--line); border-radius: 10px; }
.effort-fieldset legend { padding: 0 5px; }
.effort-fieldset label { display: flex; align-items: center; gap: 5px; }
.effort-fieldset input { width: auto; min-height: auto; }
.feedback { margin-top: 14px; padding: 10px 12px; border-radius: 10px; font-size: 12px; }
.feedback.error { color: #9d4e48; background: #f8e4e0; }
.feedback.success { color: #467a6d; background: #e7f2eb; }
.editor-actions { justify-content: flex-end; gap: 8px; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--line); }
.editor-actions span { margin-right: auto; color: var(--muted); font-size: 10px; line-height: 1.5; }
.editor-actions button { min-width: 96px; padding: 9px 13px; border: 1px solid var(--line); border-radius: 9px; color: var(--ink); background: var(--surface); cursor: pointer; }
.editor-actions .primary-action { border-color: #6b979b; color: white; background: #6b979b; }
button:disabled, input:disabled { cursor: not-allowed; opacity: .5; }
@media (max-width: 760px) {
  .profile-editor { padding: 17px; }
  .editor-heading, .section-heading, .editor-actions { align-items: flex-start; flex-direction: column; }
  .two-columns, .model-grid { grid-template-columns: 1fr; }
  .adapter-field { grid-column: auto; }
  .editor-actions button { width: 100%; }
}
</style>
