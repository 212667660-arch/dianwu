<template>
  <section class="page model-settings-page">
    <div class="page-heading">
      <div>
        <h1>模型设置</h1>
        <p>配置用于学习诊断、画像分析和资源生成的模型服务</p>
      </div>
      <span class="status-pill" :class="backend.modelConfigured ? 'good' : 'warn'">
        {{ backend.modelConfigured ? '模型已配置' : '等待配置' }}
      </span>
    </div>

    <div class="settings-grid">
      <article class="panel settings-panel">
        <div class="panel-header">
          <h2>连接模型服务</h2>
          <span class="muted">保存前会再次验证连接</span>
        </div>
        <div class="panel-body">
          <el-form label-position="top" @submit.prevent>
            <div class="form-grid">
              <el-form-item label="服务类型">
                <el-select v-model="form.provider" data-testid="model-provider">
                  <el-option label="OpenAI 兼容" value="openai" />
                  <el-option label="Anthropic Messages" value="anthropic" />
                </el-select>
              </el-form-item>
              <el-form-item label="模型名称">
                <el-input v-model="form.model_name" maxlength="128" data-testid="model-name" placeholder="例如 deepseek-chat" />
              </el-form-item>
            </div>

            <el-form-item label="API 地址">
              <el-input v-model="form.base_url" maxlength="512" data-testid="model-base-url" placeholder="https://api.example.com" />
            </el-form-item>

            <el-form-item label="API Key">
              <el-input
                v-model="form.api_key"
                type="password"
                maxlength="512"
                autocomplete="off"
                data-testid="model-api-key"
                :placeholder="keyPlaceholder"
              />
              <p class="field-note">
                {{ backend.model?.api_key_configured ? '留空将继续使用当前密钥。' : '首次配置必须输入 API Key。' }}
              </p>
            </el-form-item>

            <div class="form-grid">
              <el-form-item label="Anthropic 版本">
                <el-input v-model="form.anthropic_version" maxlength="32" data-testid="anthropic-version" />
              </el-form-item>
              <el-form-item label="请求超时（秒）">
                <el-input-number v-model="form.request_timeout_seconds" :min="5" :max="300" data-testid="request-timeout" />
              </el-form-item>
            </div>
          </el-form>

          <el-alert
            v-if="feedback.error"
            type="error"
            :closable="false"
            :title="feedback.error"
            show-icon
          />
          <el-alert
            v-else-if="feedback.success"
            type="success"
            :closable="false"
            :title="feedback.success"
            show-icon
          />

          <div class="form-actions">
            <el-button
              data-testid="model-test"
              :loading="backend.modelConfigBusy && activeAction === 'test'"
              :disabled="backend.modelConfigBusy || !backend.modelLoaded"
              @click="runTest"
            >测试连接</el-button>
            <el-button
              type="primary"
              data-testid="model-save"
              :loading="backend.modelConfigBusy && activeAction === 'save'"
              :disabled="!canSave"
              @click="runSave"
            >保存并启用</el-button>
          </div>
        </div>
      </article>

      <aside class="settings-aside">
        <article class="panel security-card">
          <div class="panel-header"><h2>安全存储</h2></div>
          <div class="panel-body">
            <div class="security-mark">安全</div>
            <h3>密钥由系统安全存储加密</h3>
            <p>桌面版使用 Electron safeStorage 保存密文。API Key 不会写入页面缓存、localStorage、学习记录或普通日志。</p>
          </div>
        </article>

        <article class="panel current-card">
          <div class="panel-header"><h2>当前配置</h2></div>
          <div class="panel-body current-list">
            <div><span>服务类型</span><strong>{{ providerLabel }}</strong></div>
            <div><span>模型</span><strong>{{ backend.model?.model_name || '未设置' }}</strong></div>
            <div><span>密钥</span><strong>{{ backend.model?.api_key_hint || '未配置' }}</strong></div>
            <div><span>状态</span><strong>{{ backend.modelConfigured ? '可用' : '待配置' }}</strong></div>
          </div>
        </article>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage, type ModelConfigInput } from '@/api'
import { useBackendStore } from '@/stores/backend'

const backend = useBackendStore()
const router = useRouter()
const activeAction = ref<'test' | 'save' | ''>('')
const formRevision = ref(0)
const testedRevision = ref(-1)
const feedback = reactive({ success: '', error: '' })
const form = reactive<ModelConfigInput>({
  provider: backend.model?.provider || 'openai',
  api_key: '',
  base_url: backend.model?.base_url || 'https://api.deepseek.com',
  model_name: backend.model?.model_name || 'deepseek-chat',
  anthropic_version: backend.model?.anthropic_version || '2023-06-01',
  request_timeout_seconds: backend.model?.request_timeout_seconds || 60,
})

const providerLabel = computed(() => backend.model?.provider === 'anthropic' ? 'Anthropic' : 'OpenAI 兼容')
const keyPlaceholder = computed(() => backend.model?.api_key_configured
  ? `已配置 ${backend.model.api_key_hint || '密钥'}，留空可继续使用`
  : '输入模型服务 API Key')
const canSave = computed(() => Boolean(
  testedRevision.value >= 0
  && testedRevision.value === formRevision.value
  && !backend.modelConfigBusy,
))

watch(form, () => {
  formRevision.value += 1
  if (testedRevision.value >= 0) {
    testedRevision.value = -1
    feedback.success = ''
  }
}, { deep: true, flush: 'sync' })

function candidate(): ModelConfigInput {
  return {
    provider: form.provider,
    api_key: form.api_key.trim(),
    base_url: form.base_url.trim(),
    model_name: form.model_name.trim(),
    anthropic_version: form.anthropic_version.trim(),
    request_timeout_seconds: Number(form.request_timeout_seconds),
  }
}

function validateCandidate(value: ModelConfigInput) {
  if (!value.base_url || !value.model_name || !value.anthropic_version) return '请完整填写模型配置。'
  if (!/^https?:\/\//i.test(value.base_url)) return 'API 地址必须以 http:// 或 https:// 开头。'
  if (!Number.isFinite(value.request_timeout_seconds) || value.request_timeout_seconds < 5 || value.request_timeout_seconds > 300) {
    return '请求超时必须在 5 到 300 秒之间。'
  }
  return ''
}

async function runTest() {
  const value = candidate()
  const revision = formRevision.value
  const validationError = validateCandidate(value)
  feedback.error = validationError
  feedback.success = ''
  testedRevision.value = -1
  if (validationError) return

  activeAction.value = 'test'
  try {
    const result = await backend.testModelSettings(value)
    if (revision === formRevision.value) {
      testedRevision.value = revision
      feedback.success = `连接成功 · ${result.latency_ms} ms`
    } else {
      feedback.error = '配置已更改，请重新测试连接。'
    }
  } catch (error) {
    form.api_key = ''
    feedback.error = errorMessage(error)
  } finally {
    activeAction.value = ''
  }
}

async function runSave() {
  if (!canSave.value) return
  activeAction.value = 'save'
  feedback.error = ''
  try {
    await backend.saveModelSettings(candidate())
    form.api_key = ''
    testedRevision.value = -1
    feedback.success = '模型配置已安全保存并启用。'
    await router.push('/tutor')
  } catch (error) {
    form.api_key = ''
    testedRevision.value = -1
    feedback.success = ''
    feedback.error = errorMessage(error)
  } finally {
    activeAction.value = ''
  }
}

onBeforeUnmount(() => {
  form.api_key = ''
  testedRevision.value = -1
})
</script>

<style scoped lang="scss">
.settings-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 16px; align-items: start; }
.settings-panel { overflow: hidden; }
.panel-header .muted { font-size: 11px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.field-note { margin: 6px 0 0; color: var(--muted); font-size: 11px; }
.form-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--line); }
.settings-aside { display: grid; gap: 16px; }
.security-mark { display: inline-flex; padding: 4px 9px; color: var(--accent); background: var(--accent-soft); border-radius: 999px; font-size: 11px; }
.security-card h3 { margin: 12px 0 7px; font-size: 15px; }
.security-card p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.7; }
.current-list { display: grid; gap: 12px; }
.current-list div { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.current-list span { color: var(--muted); font-size: 12px; }
.current-list strong { max-width: 190px; text-align: right; overflow-wrap: anywhere; font-size: 12px; }
:deep(.el-form-item) { margin-bottom: 17px; }
:deep(.el-select), :deep(.el-input-number) { width: 100%; }
@media (max-width: 980px) { .settings-grid { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .form-grid { grid-template-columns: 1fr; gap: 0; } .form-actions { flex-direction: column; } .form-actions :deep(.el-button) { width: 100%; margin-left: 0; } }
</style>
