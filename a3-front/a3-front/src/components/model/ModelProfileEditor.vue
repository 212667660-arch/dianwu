<template>
  <section class="profile-editor" aria-label="模型配置编辑器">
    <div class="editor-heading">
      <div>
        <span class="eyebrow">{{ profile ? '正在整理' : '点亮新连接' }}</span>
        <h2>{{ profile ? `编辑 · ${profile.label}` : '新建模型配置' }}</h2>
      </div>
      <span class="key-state">{{ profile?.api_key_configured ? '密钥已加密保存' : '需要 API Key' }}</span>
    </div>

    <div class="form-section two-columns">
      <label>
        <span>配置 ID</span>
        <input v-model="draft.id" data-testid="profile-id" maxlength="64" :disabled="Boolean(profile)" autocomplete="off" placeholder="例如 deepseek-main">
        <small>保存后保持稳定，用于学习空间偏好。</small>
      </label>
      <label>
        <span>显示名称</span>
        <input v-model="draft.label" data-testid="profile-label" maxlength="64" autocomplete="off" placeholder="例如 安静可靠的主模型">
      </label>
      <label>
        <span>服务类型</span>
        <select v-model="draft.provider" data-testid="profile-provider">
          <option value="openai">OpenAI 兼容</option>
          <option value="anthropic">Anthropic Messages</option>
        </select>
      </label>
      <label>
        <span>请求超时（秒）</span>
        <input v-model.number="draft.request_timeout_seconds" data-testid="profile-timeout" type="number" min="5" max="300">
      </label>
    </div>

    <div class="form-section">
      <label>
        <span>API 地址</span>
        <input v-model="draft.base_url" data-testid="profile-base-url" maxlength="512" autocomplete="off" placeholder="https://api.example.com/v1">
      </label>
      <label>
        <span>API Key</span>
        <input v-model="draft.api_key" data-testid="profile-api-key" type="password" maxlength="512" autocomplete="new-password" :placeholder="keyPlaceholder">
        <small>{{ profile?.api_key_configured ? '留空会沿用原密钥；输入内容只在测试和保存时短暂使用。' : '新配置必须输入密钥，保存完成后输入框会立即清空。' }}</small>
      </label>
      <label v-if="draft.provider === 'anthropic'">
        <span>Anthropic 版本</span>
        <input v-model="draft.anthropic_version" data-testid="profile-anthropic-version" maxlength="32">
      </label>
    </div>

    <div class="model-section">
      <div class="section-heading">
        <div>
          <span class="eyebrow">能力声明</span>
          <h3>模型与思考档位</h3>
        </div>
        <button type="button" :disabled="busy || draft.models.length >= 64" @click="addModel">＋ 添加模型</button>
      </div>

      <article v-for="(model, index) in draft.models" :key="`${model.id}-${index}`" class="model-card">
        <div class="model-card-heading">
          <strong>模型 {{ index + 1 }}</strong>
          <label class="default-choice">
            <input v-model="draft.default_model_id" type="radio" :value="model.id">
            默认模型
          </label>
          <button v-if="draft.models.length > 1" type="button" @click="removeModel(index)">移除</button>
        </div>
        <div class="model-grid">
          <label>
            <span>模型 ID</span>
            <input v-model="model.id" :data-testid="`model-${index}-id`" maxlength="128" autocomplete="off">
          </label>
          <label>
            <span>供应商模型名</span>
            <input v-model="model.provider_model_name" :data-testid="`model-${index}-provider-name`" maxlength="128" autocomplete="off">
          </label>
          <label>
            <span>显示名</span>
            <input v-model="model.label" :data-testid="`model-${index}-label`" maxlength="128" autocomplete="off">
          </label>
          <label>
            <span>最大输出 Token</span>
            <input v-model.number="model.max_output_tokens" :data-testid="`model-${index}-tokens`" type="number" min="512" max="32768">
          </label>
          <label class="adapter-field">
            <span>推理适配器</span>
            <select v-model="model.reasoning_adapter" :data-testid="`model-${index}-adapter`">
              <option v-for="adapter in reasoningAdapters" :key="adapter.value" :value="adapter.value">{{ adapter.label }}</option>
            </select>
          </label>
        </div>
        <fieldset class="effort-fieldset">
          <legend>允许的思考档位</legend>
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
      <span>每次修改后都需要重新测试，避免把不确定的连接带入学习过程。</span>
      <button type="button" data-testid="profile-test" :disabled="busy" @click="runTest">
        {{ activeAction === 'test' ? '正在试灯…' : '测试连接' }}
      </button>
      <button class="primary-action" type="button" data-testid="profile-save" :disabled="!canSave" @click="runSave">
        {{ activeAction === 'save' ? '正在保存…' : '安全保存' }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { errorMessage, type ModelDefinition, type ModelProfileInput, type ModelProfileSummary, type ReasoningAdapter, type ReasoningEffort } from '@/api'
import { useBackendStore } from '@/stores/backend'

const props = defineProps<{ profile: ModelProfileSummary | null; seedProfile?: ModelProfileSummary | null }>()
const emit = defineEmits<{ saved: [profileId: string] }>()
const backend = useBackendStore()
const activeAction = ref<'test' | 'save' | ''>('')
const testedSignature = ref('')
const feedback = reactive({ success: '', error: '' })

const reasoningAdapters: Array<{ value: ReasoningAdapter; label: string }> = [
  { value: 'none', label: '不发送显式推理参数' },
  { value: 'openai_reasoning_effort', label: 'OpenAI reasoning_effort' },
  { value: 'anthropic_thinking', label: 'Anthropic thinking' },
]
const reasoningEfforts: Array<{ value: ReasoningEffort; label: string }> = [
  { value: 'auto', label: '自动' },
  { value: 'off', label: '关闭' },
  { value: 'low', label: '轻量' },
  { value: 'medium', label: '标准' },
  { value: 'high', label: '深入' },
  { value: 'xhigh', label: '极高' },
]

const draft = reactive<ModelProfileInput>(emptyDraft())
const busy = computed(() => backend.modelProfileBusy || Boolean(activeAction.value))
const keyPlaceholder = computed(() => props.profile?.api_key_configured ? '留空沿用已保存密钥' : '输入 API Key')
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
    label: `模型 ${index}`,
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
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(value.id)) return '配置 ID 只能包含字母、数字、下划线和连字符。'
  if (!value.label) return '请填写配置显示名称。'
  if (!/^https?:\/\//i.test(value.base_url)) return 'API 地址必须以 http:// 或 https:// 开头。'
  if (!props.profile?.api_key_configured && !value.api_key) return '新配置必须输入 API Key。'
  if (!value.anthropic_version) return '请填写 Anthropic 版本。'
  if (!Number.isFinite(value.request_timeout_seconds) || value.request_timeout_seconds < 5 || value.request_timeout_seconds > 300) return '请求超时必须在 5 到 300 秒之间。'
  if (!value.models.length) return '至少需要一个模型。'
  const ids = new Set<string>()
  for (const model of value.models) {
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(model.id)) return '模型 ID 只能包含字母、数字、点、下划线、冒号和连字符。'
    if (ids.has(model.id)) return '模型 ID 不能重复。'
    ids.add(model.id)
    if (!model.provider_model_name || !model.label) return '请完整填写模型名称和显示名。'
    if (!Number.isInteger(model.max_output_tokens) || model.max_output_tokens < 512 || model.max_output_tokens > 32768) return '最大输出 Token 必须在 512 到 32768 之间。'
    if (!model.supported_reasoning_efforts.includes('auto')) return '每个模型都必须保留“自动”思考档位。'
    if (!reasoningAdapters.some(adapter => adapter.value === model.reasoning_adapter)) return '推理适配器不在安全白名单中。'
    if (model.supported_reasoning_efforts.some(effort => !reasoningEfforts.some(item => item.value === effort))) return '思考档位不在安全白名单中。'
  }
  if (!ids.has(value.default_model_id)) return '请选择有效的默认模型。'
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
      feedback.success = `连接稳定 · ${result.latency_ms} ms` 
    } else {
      feedback.error = '配置已改变，请重新测试连接。'
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
    feedback.success = '配置已加密保存，并热应用到当前学习环境。'
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
