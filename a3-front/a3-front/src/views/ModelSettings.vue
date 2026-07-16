<template>
  <section class="page model-settings-page">
    <header class="settings-hero">
      <div>
        <span class="hero-kicker">让可靠的连接，安静地守在学习背后</span>
        <h1>模型与连接</h1>
        <p>保存多套模型服务，选择默认连接，并为偶发的网络波动排好温柔而克制的备用顺序。</p>
      </div>
      <div class="hero-status" :class="{ ready: backend.modelRuntimeStatus?.ready }">
        <i />
        {{ backend.modelRuntimeStatus?.ready ? '学习引擎已就绪' : '等待第一套可用配置' }}
      </div>
    </header>

    <article class="failover-banner">
      <div class="banner-copy">
        <span class="banner-icon">↝</span>
        <div>
          <strong>自动使用备用配置</strong>
          <p>仅在连接中断、超时或服务临时不可用时切换；认证和输入错误不会被备用配置掩盖。</p>
        </div>
      </div>
      <el-switch
        :model-value="backend.modelPolicy?.auto_failover ?? false"
        data-testid="auto-failover"
        :disabled="backend.modelProfileBusy || !backend.modelPolicy"
        @change="changeAutoFailover"
      />
    </article>

    <div v-if="feedback.error || backend.lastError" class="page-feedback error" role="alert">
      {{ feedback.error || backend.lastError }}
    </div>
    <div v-if="feedback.success" class="page-feedback success" role="status">{{ feedback.success }}</div>

    <div v-if="backend.modelProfiles.length === 0" class="first-light">
      <span>☼</span>
      <div>
        <strong>点亮第一盏模型灯</strong>
        <p>先在右侧填写并测试一套连接。密钥会由系统加密保存，页面不会再次读取它。</p>
      </div>
    </div>

    <div class="settings-workbench">
      <ModelProfileList
        :profiles="backend.modelProfiles"
        :policy="backend.modelPolicy"
        :runtime-status="backend.modelRuntimeStatus"
        :selected-id="selectedId"
        :busy="backend.modelProfileBusy"
        @select="selectProfile"
        @create="startNewProfile"
        @set-default="setDefaultProfile"
        @toggle-enabled="toggleProfile"
        @test="testExistingProfile"
        @duplicate="duplicateProfile"
        @delete="deleteProfile"
        @move-fallback="moveFallback"
      />

      <ModelProfileEditor :profile="selectedProfile" :seed-profile="draftSeed" @saved="handleSaved" />

      <aside class="status-desk">
        <article class="desk-card runtime-card">
          <span class="desk-eyebrow">此刻的连接</span>
          <h2>{{ runtimeTitle }}</h2>
          <div class="runtime-orbit" :class="{ ready: backend.modelRuntimeStatus?.ready }">
            <span /><span /><span />
          </div>
          <dl>
            <div><dt>默认配置</dt><dd>{{ defaultProfile?.label || '尚未设置' }}</dd></div>
            <div><dt>备用数量</dt><dd>{{ backend.modelPolicy?.fallback_profile_ids.length || 0 }}</dd></div>
            <div><dt>自动切换</dt><dd>{{ backend.modelPolicy?.auto_failover ? '已开启' : '已关闭' }}</dd></div>
          </dl>
        </article>

        <article class="desk-card safety-card">
          <span class="desk-eyebrow">安全边界</span>
          <h3>密钥只在受信主进程短暂停留</h3>
          <p>列表、运行状态、学习记录和日志只接触脱敏信息。编辑旧配置时，Key 留空即沿用原密钥。</p>
        </article>

        <article class="desk-card order-card">
          <span class="desk-eyebrow">连接顺序</span>
          <ol>
            <li><b>1</b><span>学习空间手动选择</span></li>
            <li><b>2</b><span>全局默认配置</span></li>
            <li><b>3</b><span>你排列的备用配置</span></li>
          </ol>
          <p>流式回答一旦已经出现文字，就不会静默拼接另一个模型。</p>
        </article>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { errorMessage, type ModelProfileInput, type ModelProfileSummary } from '@/api'
import ModelProfileEditor from '@/components/model/ModelProfileEditor.vue'
import ModelProfileList from '@/components/model/ModelProfileList.vue'
import { useBackendStore } from '@/stores/backend'

const backend = useBackendStore()
const selectedId = ref('')
const draftSeed = ref<ModelProfileSummary | null>(null)
const feedback = reactive({ success: '', error: '' })

const selectedProfile = computed(() => backend.modelProfiles.find(profile => profile.id === selectedId.value) || null)
const defaultProfile = computed(() => backend.modelProfiles.find(profile => profile.id === backend.modelPolicy?.default_profile_id))
const runtimeTitle = computed(() => {
  if (!backend.modelProfiles.length) return '书桌还在等第一位伙伴'
  if (backend.modelRuntimeStatus?.ready) return '连接正在安静工作'
  return '有配置需要你的照看'
})

watch(() => [backend.modelProfiles, backend.modelPolicy?.default_profile_id] as const, ensureSelection, { deep: true })

onMounted(async () => {
  feedback.error = ''
  try {
    await backend.refreshModelProfiles()
    ensureSelection()
  } catch (error) {
    feedback.error = errorMessage(error)
  }
})

function ensureSelection() {
  if (selectedId.value && backend.modelProfiles.some(profile => profile.id === selectedId.value)) return
  selectedId.value = backend.modelPolicy?.default_profile_id || backend.modelProfiles[0]?.id || ''
}

function selectProfile(profile: ModelProfileSummary) {
  selectedId.value = profile.id
  draftSeed.value = null
  clearFeedback()
}

function startNewProfile() {
  selectedId.value = ''
  draftSeed.value = null
  clearFeedback()
}

function duplicateProfile(profile: ModelProfileSummary) {
  selectedId.value = ''
  draftSeed.value = {
    ...profile,
    id: nextCopyId(profile.id),
    label: `${profile.label} 副本`,
    enabled: true,
    api_key_configured: false,
    models: profile.models.map(model => ({ ...model, supported_reasoning_efforts: [...model.supported_reasoning_efforts] })),
  }
  clearFeedback()
}

async function changeAutoFailover(value: string | number | boolean) {
  if (!backend.modelPolicy) return
  await savePolicy({ ...backend.modelPolicy, auto_failover: Boolean(value) }, value ? '自动备用已开启。' : '自动备用已关闭。')
}

async function setDefaultProfile(profileId: string) {
  if (!backend.modelPolicy || backend.modelPolicy.default_profile_id === profileId) return
  const oldDefault = backend.modelPolicy.default_profile_id
  const fallback = backend.modelPolicy.fallback_profile_ids.filter(id => id !== profileId)
  if (oldDefault && oldDefault !== profileId && !fallback.includes(oldDefault)) fallback.unshift(oldDefault)
  await savePolicy({ ...backend.modelPolicy, default_profile_id: profileId, fallback_profile_ids: fallback }, '默认模型配置已更新。')
  selectedId.value = profileId
}

async function moveFallback(payload: { profileId: string; direction: -1 | 1 }) {
  if (!backend.modelPolicy) return
  const fallback = [...backend.modelPolicy.fallback_profile_ids]
  const index = fallback.indexOf(payload.profileId)
  const next = index + payload.direction
  if (index < 0 || next < 0 || next >= fallback.length) return
  ;[fallback[index], fallback[next]] = [fallback[next], fallback[index]]
  await savePolicy({ ...backend.modelPolicy, fallback_profile_ids: fallback }, '备用顺序已更新。')
}

async function toggleProfile(payload: { profileId: string; enabled: boolean }) {
  const profile = backend.modelProfiles.find(item => item.id === payload.profileId)
  if (!profile) return
  clearFeedback()
  try {
    await backend.upsertModelProfile(toInput(profile, payload.enabled))
    feedback.success = payload.enabled ? '配置已启用并通过连接测试。' : '配置已停用。'
  } catch (error) {
    feedback.error = errorMessage(error)
  }
}

async function testExistingProfile(profile: ModelProfileSummary) {
  clearFeedback()
  try {
    const result = await backend.testModelProfile(toInput(profile, profile.enabled))
    feedback.success = `${profile.label} 连接稳定 · ${result.latency_ms} ms`
  } catch (error) {
    feedback.error = errorMessage(error)
  }
}

async function deleteProfile(profileId: string) {
  clearFeedback()
  try {
    await backend.deleteModelProfile(profileId)
    if (selectedId.value === profileId) selectedId.value = ''
    ensureSelection()
    feedback.success = '模型配置已删除。'
  } catch (error) {
    feedback.error = errorMessage(error)
  }
}

async function handleSaved(profileId: string) {
  selectedId.value = profileId
  draftSeed.value = null
  if (backend.modelPolicy && backend.modelPolicy.default_profile_id !== profileId && !backend.modelPolicy.fallback_profile_ids.includes(profileId)) {
    await savePolicy({ ...backend.modelPolicy, fallback_profile_ids: [...backend.modelPolicy.fallback_profile_ids, profileId] }, '配置已保存，并加入备用顺序。')
  }
}

async function savePolicy(policy: NonNullable<typeof backend.modelPolicy>, success: string) {
  clearFeedback()
  try {
    await backend.saveModelPolicy(policy)
    feedback.success = success
  } catch (error) {
    feedback.error = errorMessage(error)
  }
}

function toInput(profile: ModelProfileSummary, enabled: boolean): ModelProfileInput {
  return {
    id: profile.id,
    label: profile.label,
    enabled,
    provider: profile.provider,
    base_url: profile.base_url,
    api_key: '',
    anthropic_version: profile.anthropic_version,
    request_timeout_seconds: profile.request_timeout_seconds,
    default_model_id: profile.default_model_id,
    models: profile.models.map(model => ({ ...model, supported_reasoning_efforts: [...model.supported_reasoning_efforts] })),
  }
}

function clearFeedback() {
  feedback.error = ''
  feedback.success = ''
}

function nextCopyId(profileId: string) {
  const stem = `${profileId}-copy`.slice(0, 60)
  let candidate = stem
  let suffix = 2
  while (backend.modelProfiles.some(profile => profile.id === candidate)) {
    const ending = `-${suffix}`
    candidate = `${stem.slice(0, 64 - ending.length)}${ending}`
    suffix += 1
  }
  return candidate
}
</script>

<style scoped lang="scss">
.model-settings-page { max-width: 1580px; margin: 0 auto; }
.settings-hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 18px; padding: 8px 4px; }
.hero-kicker, .desk-eyebrow { color: var(--accent); font-size: 10px; letter-spacing: .18em; }
.settings-hero h1 { margin: 6px 0 8px; font-family: Georgia, "Microsoft YaHei", serif; font-size: clamp(28px, 3vw, 42px); font-weight: 500; }
.settings-hero p { max-width: 720px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; }
.hero-status { display: flex; align-items: center; gap: 7px; padding: 8px 11px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); background: rgba(255, 253, 250, .74); font-size: 11px; white-space: nowrap; }
.hero-status i { width: 7px; height: 7px; border-radius: 50%; background: #d3a16e; box-shadow: 0 0 0 4px rgba(211, 161, 110, .13); }
.hero-status.ready i { background: #72a394; box-shadow: 0 0 0 4px rgba(114, 163, 148, .14); }
.failover-banner { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 16px; padding: 14px 17px; border: 1px solid rgba(107, 151, 155, .25); border-radius: 16px; background: linear-gradient(110deg, rgba(228, 240, 237, .72), rgba(255, 250, 242, .88)); }
.banner-copy { display: flex; align-items: center; gap: 12px; }
.banner-icon { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; color: #4f8082; background: rgba(255, 255, 255, .7); font-size: 22px; }
.banner-copy strong { font-size: 13px; }
.banner-copy p { margin: 3px 0 0; color: var(--muted); font-size: 11px; line-height: 1.55; }
.page-feedback, .first-light { margin-bottom: 14px; padding: 11px 14px; border-radius: 12px; font-size: 12px; }
.page-feedback.error { color: #9d4e48; background: #f8e4e0; }
.page-feedback.success { color: #467a6d; background: #e7f2eb; }
.first-light { display: flex; align-items: center; gap: 12px; border: 1px dashed #d7b98e; color: #7b5b35; background: #fff6e8; }
.first-light > span { font-size: 26px; }
.first-light p { margin: 3px 0 0; color: #8b7252; font-size: 11px; }
.settings-workbench { display: grid; grid-template-columns: minmax(230px, 270px) minmax(500px, 1fr) minmax(220px, 260px); gap: 16px; align-items: start; }
.status-desk { display: grid; gap: 13px; }
.desk-card { padding: 17px; border: 1px solid var(--line); border-radius: 17px; background: rgba(255, 253, 250, .88); box-shadow: 0 12px 34px rgba(91, 72, 55, .05); }
.desk-card h2, .desk-card h3 { margin: 7px 0 10px; font-family: Georgia, "Microsoft YaHei", serif; font-weight: 500; }
.desk-card h2 { font-size: 17px; } .desk-card h3 { font-size: 15px; }
.desk-card p { margin: 0; color: var(--muted); font-size: 11px; line-height: 1.75; }
.runtime-orbit { position: relative; height: 62px; margin: 12px 0 6px; }
.runtime-orbit::before, .runtime-orbit::after { content: ''; position: absolute; inset: 8px 28px; border: 1px dashed #d9cfc0; border-radius: 50%; }
.runtime-orbit::after { inset: 17px 46px; }
.runtime-orbit span { position: absolute; z-index: 1; width: 10px; height: 10px; border: 2px solid #fffdfa; border-radius: 50%; background: #d3a16e; box-shadow: 0 0 0 4px rgba(211, 161, 110, .12); }
.runtime-orbit.ready span { background: #72a394; }
.runtime-orbit span:nth-child(1) { top: 8px; left: 50%; }
.runtime-orbit span:nth-child(2) { bottom: 8px; left: 29%; }
.runtime-orbit span:nth-child(3) { right: 26%; bottom: 13px; }
dl { display: grid; gap: 9px; margin: 0; }
dl div { display: flex; justify-content: space-between; gap: 10px; padding-top: 8px; border-top: 1px dashed var(--line); font-size: 11px; }
dt { color: var(--muted); } dd { margin: 0; text-align: right; }
.order-card ol { display: grid; gap: 9px; margin: 11px 0; padding: 0; list-style: none; }
.order-card li { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 11px; }
.order-card b { display: grid; place-items: center; width: 21px; height: 21px; border-radius: 50%; color: #507d7d; background: var(--accent-soft); font-size: 10px; }
@media (max-width: 1580px) { .settings-workbench { grid-template-columns: 250px minmax(0, 1fr); } .status-desk { grid-column: 1 / -1; grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 920px) { .settings-workbench { grid-template-columns: 1fr; } .status-desk { grid-column: auto; grid-template-columns: 1fr; } }
@media (max-width: 680px) { .settings-hero, .failover-banner { align-items: flex-start; flex-direction: column; } .hero-status { white-space: normal; } }
</style>
