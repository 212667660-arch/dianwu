<template>
  <main class="onboarding-page">
    <section class="onboarding-card">
      <span class="kicker">WELCOME TO A3</span>
      <h1>{{ t('views.onboarding.environmentFirstTime') }}</h1>
      <p>{{ t('views.onboarding.localFirstModelChoice') }}</p>
      <div v-if="loading" class="loading" role="status">{{ t('views.onboarding.checkingDesktopEnvironment') }}</div>
      <div v-else class="checks">
        <article><i :class="{ ok: info?.backend_ready }" /><div><strong>{{ t('views.onboarding.backendLocal') }}</strong><span>{{ info?.backend_ready ? t('views.onboarding.ready') : t('views.onboarding.diagnosis') }}</span></div></article>
        <article><i :class="{ ok: info?.data_directory_ready }" /><div><strong>{{ t('views.onboarding.directoryLocal') }}</strong><span>{{ info?.data_directory_ready ? t('views.onboarding.security') : t('views.onboarding.notWritable') }}</span></div></article>
        <article><i :class="{ ok: info?.model_configured }" /><div><strong>{{ t('views.onboarding.modelOnline') }}</strong><span>{{ info?.model_configured ? t('views.onboarding.profile') : t('views.onboarding.profileTitle') }}</span></div></article>
        <article><i :class="{ ok: info?.ocr_available }" /><div><strong>{{ t('views.onboarding.offlineOcr') }}</strong><span>{{ info?.ocr_available ? t('views.onboarding.chineseTextbookRecognition') : t('views.onboarding.ocrUnavailable') }}</span></div></article>
      </div>
      <div class="version">{{ t('views.onboarding.desktopVersion') }} {{ info?.app_version || '—' }} · {{ updateLabel }}</div>
      <div v-if="error" class="error" role="alert">{{ error }}</div>
      <div class="actions">
        <button data-testid="offline-demo-onboarding" type="button" :disabled="busy" @click="finish(true)">{{ t('views.onboarding.offline') }}</button>
        <button data-testid="complete-onboarding" class="primary" type="button" :disabled="busy" @click="finish(false)">{{ t('views.onboarding.application') }}</button>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { backendApi, type DesktopInfo } from '@/api'

const { t } = useI18n()

const router = useRouter()
const info = ref<DesktopInfo | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const updateLabel = computed(() => info.value?.update_status === 'offline_build' ? t('views.onboarding.offlineCurrent') : t('views.onboarding.updateCheck'))

async function finish(offlineDemo: boolean) {
  busy.value = true
  error.value = ''
  try {
    await backendApi.completeDesktopOnboarding({ offlineDemo })
    await router.replace({ path: '/dashboard', query: offlineDemo ? { demo: 'offline' } : {} })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('views.onboarding.settingsSaveFailure')
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    info.value = await backendApi.desktopInfo()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('views.onboarding.environmentCheckFailure')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped lang="scss">
.onboarding-page{min-height:100vh;display:grid;place-items:center;padding:30px;background:radial-gradient(circle at top,#fffaf0,#eee4d8)}.onboarding-card{width:min(760px,100%);padding:38px;background:rgba(255,253,249,.94);border:1px solid #e3d6c8;border-radius:24px;box-shadow:0 24px 80px rgba(72,55,40,.12)}.kicker{color:#6b9693;font-size:10px;letter-spacing:.2em}.onboarding-card h1{margin:9px 0;font-family:Georgia,"Microsoft YaHei",serif;font-size:30px;font-weight:500}.onboarding-card>p{color:#817468;line-height:1.8}.checks{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:24px 0}.checks article{display:flex;align-items:center;gap:11px;padding:14px;background:#faf6ef;border:1px solid #e8ddd2;border-radius:14px}.checks i{width:10px;height:10px;border-radius:50%;background:#c77c72;box-shadow:0 0 0 5px rgba(199,124,114,.12)}.checks i.ok{background:#6e9f91;box-shadow:0 0 0 5px rgba(110,159,145,.13)}.checks strong,.checks span{display:block}.checks strong{font-size:13px}.checks span{margin-top:4px;color:#918477;font-size:10px}.version,.loading{color:#8b8074;font-size:11px}.error{margin-top:12px;padding:10px;color:#9d4e48;background:#f8e4e0;border-radius:10px}.actions{display:flex;justify-content:flex-end;gap:10px;margin-top:24px}.actions button{min-height:40px;padding:0 18px;color:#5d817f;background:#edf5f1;border:1px solid #d0e0da;border-radius:10px;cursor:pointer}.actions .primary{color:#fff;background:#648e8f;border-color:#648e8f}.actions button:disabled{opacity:.5}@media(max-width:620px){.onboarding-card{padding:24px}.checks{grid-template-columns:1fr}.actions{align-items:stretch;flex-direction:column}.actions button{width:100%}}
</style>
