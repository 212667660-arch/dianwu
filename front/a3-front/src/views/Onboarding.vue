<template>
  <main class="onboarding-page">
    <section class="onboarding-card">
      <span class="kicker">WELCOME TO A3</span>
      <h1>第一次见面，先把学习环境安顿好</h1>
      <p>所有资料默认保存在本机。你可以现在配置在线模型，也可以先进入内置离线演示。</p>
      <div v-if="loading" class="loading" role="status">正在检查桌面环境…</div>
      <div v-else class="checks">
        <article><i :class="{ ok: info?.backend_ready }" /><div><strong>本地后端</strong><span>{{ info?.backend_ready ? '已就绪' : '需要诊断' }}</span></div></article>
        <article><i :class="{ ok: info?.data_directory_ready }" /><div><strong>本地数据目录</strong><span>{{ info?.data_directory_ready ? '可安全写入' : '不可写' }}</span></div></article>
        <article><i :class="{ ok: info?.model_configured }" /><div><strong>在线模型</strong><span>{{ info?.model_configured ? '已配置' : '可稍后配置' }}</span></div></article>
        <article><i :class="{ ok: info?.ocr_available }" /><div><strong>离线 OCR</strong><span>{{ info?.ocr_available ? '中文扫描教材可识别' : '组件不可用' }}</span></div></article>
      </div>
      <div class="version">桌面版本 {{ info?.app_version || '—' }} · {{ updateLabel }}</div>
      <div v-if="error" class="error" role="alert">{{ error }}</div>
      <div class="actions">
        <button data-testid="offline-demo-onboarding" type="button" :disabled="busy" @click="finish(true)">先看离线演示</button>
        <button data-testid="complete-onboarding" class="primary" type="button" :disabled="busy" @click="finish(false)">进入应用</button>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { backendApi, type DesktopInfo } from '@/api'

const router = useRouter()
const info = ref<DesktopInfo | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const updateLabel = computed(() => info.value?.update_status === 'offline_build' ? '当前为离线构建' : '可检查更新')

async function finish(offlineDemo: boolean) {
  busy.value = true
  error.value = ''
  try {
    await backendApi.completeDesktopOnboarding({ offlineDemo })
    await router.replace({ path: '/dashboard', query: offlineDemo ? { demo: 'offline' } : {} })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法保存首次启动设置。'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    info.value = await backendApi.desktopInfo()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '桌面环境检查失败。'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped lang="scss">
.onboarding-page{min-height:100vh;display:grid;place-items:center;padding:30px;background:radial-gradient(circle at top,#fffaf0,#eee4d8)}.onboarding-card{width:min(760px,100%);padding:38px;background:rgba(255,253,249,.94);border:1px solid #e3d6c8;border-radius:24px;box-shadow:0 24px 80px rgba(72,55,40,.12)}.kicker{color:#6b9693;font-size:10px;letter-spacing:.2em}.onboarding-card h1{margin:9px 0;font-family:Georgia,"Microsoft YaHei",serif;font-size:30px;font-weight:500}.onboarding-card>p{color:#817468;line-height:1.8}.checks{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:24px 0}.checks article{display:flex;align-items:center;gap:11px;padding:14px;background:#faf6ef;border:1px solid #e8ddd2;border-radius:14px}.checks i{width:10px;height:10px;border-radius:50%;background:#c77c72;box-shadow:0 0 0 5px rgba(199,124,114,.12)}.checks i.ok{background:#6e9f91;box-shadow:0 0 0 5px rgba(110,159,145,.13)}.checks strong,.checks span{display:block}.checks strong{font-size:13px}.checks span{margin-top:4px;color:#918477;font-size:10px}.version,.loading{color:#8b8074;font-size:11px}.error{margin-top:12px;padding:10px;color:#9d4e48;background:#f8e4e0;border-radius:10px}.actions{display:flex;justify-content:flex-end;gap:10px;margin-top:24px}.actions button{min-height:40px;padding:0 18px;color:#5d817f;background:#edf5f1;border:1px solid #d0e0da;border-radius:10px;cursor:pointer}.actions .primary{color:#fff;background:#648e8f;border-color:#648e8f}.actions button:disabled{opacity:.5}@media(max-width:620px){.onboarding-card{padding:24px}.checks{grid-template-columns:1fr}.actions{align-items:stretch;flex-direction:column}.actions button{width:100%}}
</style>
