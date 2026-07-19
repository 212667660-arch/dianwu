<template>
  <section class="desktop-settings-page">
    <header><span>DESKTOP CONTROL</span><h1>{{ t('views.desktopSettings.desktopPetSettings') }}</h1><p>{{ t('views.desktopSettings.settingsOverview') }}</p></header>
    <div v-if="error" class="feedback error" role="alert">{{ error }}</div>
    <div v-if="messages.length" class="feedback success" role="status"><span v-for="item in messages" :key="item">{{ item }}</span></div>
    <div class="desktop-grid">
      <article class="desktop-card">
        <h2>{{ t('views.desktopSettings.versionUpdate') }}</h2>
        <dl><div><dt>{{ t('views.desktopSettings.application.version') }}</dt><dd>{{ info?.app_version || '—' }}</dd></div><div><dt>{{ t('views.desktopSettings.backendProtocol') }}</dt><dd>{{ info?.backend_protocol || '—' }}</dd></div><div><dt>{{ t('views.desktopSettings.backendLocal') }}</dt><dd>{{ info?.backend_ready ? t('views.desktopSettings.ready') : t('views.desktopSettings.backendUnavailable') }}</dd></div><div><dt>{{ t('views.desktopSettings.offline') }}</dt><dd>{{ info?.ocr_available ? t('views.desktopSettings.available', { version: info.ocr_version || '' }) : t('views.desktopSettings.backendUnavailable') }}</dd></div></dl>
        <button data-testid="check-desktop-updates" type="button" @click="checkUpdates">{{ t('views.desktopSettings.application.checkUpdates') }}</button>
      </article>
      <article class="desktop-card">
        <h2>{{ t('views.desktopSettings.diagnosis') }}</h2>
        <p>{{ t('views.desktopSettings.diagnosticPrivacyNotice') }}</p>
        <div class="actions"><button data-testid="run-desktop-diagnostics" type="button" @click="runDiagnostics">{{ t('views.desktopSettings.diagnosisGenerate') }}</button><button data-testid="export-desktop-diagnostics" type="button" @click="exportDiagnostics">{{ t('views.desktopSettings.exportLog') }}</button></div>
        <pre v-if="diagnostics">{{ diagnostics.logs.join('\n') || t('views.desktopSettings.noRuntimeLogs') }}</pre>
      </article>
      <LanguageSettingsCard
        :active-locale="locale"
        :languages="builtInLanguages"
        :busy-locale="null"
        :progress="null"
        :desktop-available="desktopLanguageAvailable"
        @activate="activateBundledLanguage"
      />
      <PetSettingsCard />
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, ref } from 'vue'
import { backendApi, type DesktopDiagnosticReport, type DesktopInfo } from '@/api'
import LanguageSettingsCard from '@/components/language/LanguageSettingsCard.vue'
import PetSettingsCard from '@/components/pet/PetSettingsCard.vue'
import { BUNDLED_LOCALE_SUMMARIES } from '@/i18n/bundled-locales'
import { activateLocale } from '@/i18n'

const { t, locale } = useI18n()

type DesktopLanguageCapability = {
  languageList?: () => unknown
  languageDownload?: (locale: string) => unknown
  languageImport?: () => unknown
}

const builtInLanguages = computed(() => BUNDLED_LOCALE_SUMMARIES)
const desktopLanguageAvailable = computed(() => {
  const bridge = window.a3Desktop as (typeof window.a3Desktop & DesktopLanguageCapability) | undefined
  return typeof bridge?.languageList === 'function'
    && typeof bridge.languageDownload === 'function'
    && typeof bridge.languageImport === 'function'
})

const info = ref<DesktopInfo | null>(null)
const diagnostics = ref<DesktopDiagnosticReport | null>(null)
const messages = ref<string[]>([])
const error = ref('')

async function run(action: () => Promise<void>) {
  error.value = ''
  try { await action() } catch (reason) { error.value = reason instanceof Error ? reason.message : t('views.desktopSettings.desktopFailure') }
}
function addMessage(value: string) { messages.value = [...messages.value.filter(item => item !== value), value].slice(-4) }
function activateBundledLanguage(value: string) { activateLocale(value, true) }
function runDiagnostics() { return run(async () => { diagnostics.value = await backendApi.desktopDiagnostics(); addMessage(t('views.desktopSettings.diagnosisGenerateTitle')) }) }
function exportDiagnostics() { return run(async () => { const result = await backendApi.exportDesktopDiagnostics(); addMessage(result.exported ? t('views.desktopSettings.export', { fileName: result.file_name }) : t('views.desktopSettings.exportCancel')) }) }
function checkUpdates() { return run(async () => { const result = await backendApi.checkDesktopUpdates(); addMessage(result.status === 'offline_build' ? t('views.desktopSettings.offlineTitle', { message: result.message }) : result.message) }) }
onMounted(() => run(async () => { info.value = await backendApi.desktopInfo() }))
</script>

<style scoped lang="scss">
.desktop-settings-page{max-width:1280px;margin:0 auto}.desktop-settings-page header span{color:#6d9691;font-size:9px;letter-spacing:.18em}.desktop-settings-page h1{margin:6px 0;font-family:Georgia,"Microsoft YaHei",serif;font-size:28px;font-weight:500;overflow-wrap:anywhere}.desktop-settings-page header p{color:var(--muted);overflow-wrap:anywhere}.desktop-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:20px}.desktop-card{padding:20px;background:rgba(255,253,249,.9);border:1px solid var(--line);border-radius:17px;box-shadow:var(--shadow-soft)}.desktop-card h2{margin-top:0;font-family:Georgia,"Microsoft YaHei",serif;font-weight:500;overflow-wrap:anywhere}.desktop-card p{color:var(--muted);font-size:11px;line-height:1.7;overflow-wrap:anywhere}.desktop-card dl div{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px dashed var(--line);font-size:11px}.desktop-card dd{margin:0;overflow-wrap:anywhere}.desktop-card button{min-height:34px;margin-top:12px;padding:0 12px;color:#5c8381;background:#edf5f1;border:1px solid #d4e3dd;border-radius:9px;cursor:pointer;overflow-wrap:anywhere}.actions{display:flex;flex-wrap:wrap;gap:8px}.desktop-card pre{max-height:220px;overflow:auto;padding:10px;color:#645b52;background:#f7f2eb;border-radius:10px;font-size:9px;white-space:pre-wrap}.feedback{margin-top:12px;padding:10px;border-radius:10px}.feedback.error{color:#984f48;background:#f8e4e0}.feedback.success{color:#467a6d;background:#e7f2eb}@media(max-width:980px){.desktop-grid{grid-template-columns:1fr}}
.feedback span{display:block}.feedback span+span{margin-top:4px}
</style>
