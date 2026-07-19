<template>
  <section class="language-card" aria-labelledby="language-settings-title">
    <header class="language-header">
      <div>
        <h2 id="language-settings-title">{{ t('views.desktopSettings.language.title') }}</h2>
        <p>{{ t('views.desktopSettings.language.contentFollowsUi') }}</p>
      </div>
      <button
        v-if="desktopAvailable"
        data-testid="language-refresh"
        type="button"
        @click="emit('refresh')"
      >
        {{ t('views.desktopSettings.language.refresh') }}
      </button>
    </header>

    <ul class="language-list">
      <li v-for="language in displayedLanguages" :key="language.locale" class="language-row">
        <div class="language-copy">
          <strong>{{ language.nativeName }}</strong>
          <span>{{ language.locale }}</span>
          <small v-if="language.version">{{ language.version }}</small>
        </div>
        <span class="language-status">{{ statusLabel(language) }}</span>
        <div class="language-actions">
          <button
            v-if="desktopAvailable && language.status === 'available'"
            :data-testid="`language-download-${language.locale}`"
            type="button"
            :disabled="busyLocale !== null"
            @click="emit('download', language.locale)"
          >
            {{ t('views.desktopSettings.language.download') }}
          </button>
          <button
            v-if="language.locale !== activeLocale && (language.status === 'installed' || language.status === 'built_in')"
            :data-testid="`language-activate-${language.locale}`"
            type="button"
            :disabled="busyLocale !== null"
            @click="emit('activate', language.locale)"
          >
            {{ t('views.desktopSettings.language.activate') }}
          </button>
          <button
            v-if="desktopAvailable && language.locale !== activeLocale && language.status === 'installed'"
            :data-testid="`language-remove-${language.locale}`"
            type="button"
            :disabled="busyLocale !== null"
            @click="emit('remove', language.locale)"
          >
            {{ t('views.desktopSettings.language.remove') }}
          </button>
        </div>
        <div
          v-if="progress && busyLocale === language.locale"
          class="language-progress"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="progressPercent"
        >
          <i :style="{ width: `${progressPercent}%` }" />
        </div>
      </li>
    </ul>

    <footer v-if="desktopAvailable" class="language-footer">
      <button data-testid="language-import" type="button" :disabled="busyLocale !== null" @click="emit('import')">
        {{ t('views.desktopSettings.language.import') }}
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

interface LanguagePackSummary {
  locale: string
  nativeName: string
  version?: string | null
  status: 'built_in' | 'installed' | 'available' | 'error'
}

interface LanguageProgress {
  percent?: number
  receivedBytes?: number
  totalBytes?: number
}

const props = defineProps<{
  activeLocale: string
  languages: LanguagePackSummary[]
  busyLocale: string | null
  progress: LanguageProgress | null
  desktopAvailable: boolean
}>()

const emit = defineEmits<{
  refresh: []
  download: [locale: string]
  activate: [locale: string]
  remove: [locale: string]
  import: []
}>()

const { t } = useI18n()
const displayedLanguages = computed<LanguagePackSummary[]>(() => [
  { locale: 'zh-CN', nativeName: t('views.desktopSettings.language.builtInName'), status: 'built_in' },
  ...props.languages.filter(language => language.locale !== 'zh-CN'),
])
const progressPercent = computed(() => {
  const explicit = props.progress?.percent
  if (typeof explicit === 'number') return Math.min(100, Math.max(0, Math.round(explicit)))
  const received = props.progress?.receivedBytes
  const total = props.progress?.totalBytes
  return received !== undefined && total ? Math.min(100, Math.max(0, Math.round(received / total * 100))) : 0
})

function statusLabel(language: LanguagePackSummary): string {
  if (language.locale === props.activeLocale) return t('views.desktopSettings.language.active')
  if (language.status === 'built_in') return t('views.desktopSettings.language.builtIn')
  if (language.status === 'installed') return t('views.desktopSettings.language.installed')
  return t('views.desktopSettings.language.available')
}
</script>

<style scoped>
.language-card { padding: 20px; border: 1px solid #ded6ca; border-radius: 16px; background: #fffdf9; }
.language-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.language-header h2 { margin: 0; font-size: 18px; }
.language-header p { max-width: 68ch; margin: 6px 0 0; color: var(--muted); line-height: 1.65; overflow-wrap: anywhere; }
.language-header button, .language-actions button, .language-footer button { min-height: 34px; padding: 6px 12px; border: 1px solid #d8cec1; border-radius: 9px; background: #fff; cursor: pointer; overflow-wrap: anywhere; }
.language-list { display: grid; gap: 10px; margin: 18px 0 0; padding: 0; list-style: none; }
.language-row { display: grid; grid-template-columns: minmax(150px, 1fr) auto minmax(190px, auto); align-items: center; gap: 14px; padding: 14px; border: 1px solid #e6ddd2; border-radius: 12px; }
.language-copy strong, .language-copy span, .language-copy small { display: block; overflow-wrap: anywhere; }
.language-copy span, .language-copy small, .language-status { color: var(--muted); font-size: 11px; }
.language-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 7px; }
.language-progress { grid-column: 1 / -1; height: 5px; overflow: hidden; border-radius: 999px; background: #eee8df; }
.language-progress i { display: block; height: 100%; background: var(--accent); }
.language-footer { display: flex; justify-content: flex-end; margin-top: 14px; }
button:focus-visible { outline: 3px solid rgba(68, 126, 128, .3); outline-offset: 2px; }
button:disabled { cursor: not-allowed; opacity: .55; }
@media (max-width: 720px) {
  .language-header { flex-direction: column; }
  .language-row { grid-template-columns: 1fr auto; }
  .language-actions { grid-column: 1 / -1; justify-content: flex-start; }
}
</style>
