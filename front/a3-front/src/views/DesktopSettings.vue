<template>
  <section class="desktop-settings-page">
    <header><span>DESKTOP CONTROL</span><h1>桌面运行与墨团设置</h1><p>查看版本、检查运行状态、导出脱敏日志，并调整学习伙伴。</p></header>
    <div v-if="error" class="feedback error" role="alert">{{ error }}</div>
    <div v-if="messages.length" class="feedback success" role="status"><span v-for="item in messages" :key="item">{{ item }}</span></div>
    <div class="desktop-grid">
      <article class="desktop-card">
        <h2>版本与更新</h2>
        <dl><div><dt>应用版本</dt><dd>{{ info?.app_version || '—' }}</dd></div><div><dt>后端协议</dt><dd>{{ info?.backend_protocol || '—' }}</dd></div><div><dt>本地后端</dt><dd>{{ info?.backend_ready ? '已就绪' : '不可用' }}</dd></div><div><dt>离线 OCR</dt><dd>{{ info?.ocr_available ? `可用 ${info.ocr_version || ''}` : '不可用' }}</dd></div></dl>
        <button data-testid="check-desktop-updates" type="button" @click="checkUpdates">检查更新</button>
      </article>
      <article class="desktop-card">
        <h2>一键诊断</h2>
        <p>报告会自动移除密钥、令牌、学习正文和本地绝对路径。</p>
        <div class="actions"><button data-testid="run-desktop-diagnostics" type="button" @click="runDiagnostics">生成诊断</button><button data-testid="export-desktop-diagnostics" type="button" @click="exportDiagnostics">导出日志</button></div>
        <pre v-if="diagnostics">{{ diagnostics.logs.join('\n') || '暂无运行日志' }}</pre>
      </article>
      <PetSettingsCard />
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { backendApi, type DesktopDiagnosticReport, type DesktopInfo } from '@/api'
import PetSettingsCard from '@/components/pet/PetSettingsCard.vue'

const info = ref<DesktopInfo | null>(null)
const diagnostics = ref<DesktopDiagnosticReport | null>(null)
const messages = ref<string[]>([])
const error = ref('')

async function run(action: () => Promise<void>) {
  error.value = ''
  try { await action() } catch (reason) { error.value = reason instanceof Error ? reason.message : '桌面操作失败。' }
}
function addMessage(value: string) { messages.value = [...messages.value.filter(item => item !== value), value].slice(-4) }
function runDiagnostics() { return run(async () => { diagnostics.value = await backendApi.desktopDiagnostics(); addMessage('诊断报告已生成。') }) }
function exportDiagnostics() { return run(async () => { const result = await backendApi.exportDesktopDiagnostics(); addMessage(result.exported ? `已导出 ${result.file_name}` : '已取消导出。') }) }
function checkUpdates() { return run(async () => { const result = await backendApi.checkDesktopUpdates(); addMessage(result.status === 'offline_build' ? `离线构建：${result.message}` : result.message) }) }
onMounted(() => run(async () => { info.value = await backendApi.desktopInfo() }))
</script>

<style scoped lang="scss">
.desktop-settings-page{max-width:1280px;margin:0 auto}.desktop-settings-page header span{color:#6d9691;font-size:9px;letter-spacing:.18em}.desktop-settings-page h1{margin:6px 0;font-family:Georgia,"Microsoft YaHei",serif;font-size:28px;font-weight:500}.desktop-settings-page header p{color:var(--muted)}.desktop-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:20px}.desktop-card{padding:20px;background:rgba(255,253,249,.9);border:1px solid var(--line);border-radius:17px;box-shadow:var(--shadow-soft)}.desktop-card h2{margin-top:0;font-family:Georgia,"Microsoft YaHei",serif;font-weight:500}.desktop-card p{color:var(--muted);font-size:11px;line-height:1.7}.desktop-card dl div{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px dashed var(--line);font-size:11px}.desktop-card dd{margin:0}.desktop-card button{min-height:34px;margin-top:12px;padding:0 12px;color:#5c8381;background:#edf5f1;border:1px solid #d4e3dd;border-radius:9px;cursor:pointer}.actions{display:flex;gap:8px}.desktop-card pre{max-height:220px;overflow:auto;padding:10px;color:#645b52;background:#f7f2eb;border-radius:10px;font-size:9px;white-space:pre-wrap}.feedback{margin-top:12px;padding:10px;border-radius:10px}.feedback.error{color:#984f48;background:#f8e4e0}.feedback.success{color:#467a6d;background:#e7f2eb}@media(max-width:980px){.desktop-grid{grid-template-columns:1fr}}
.feedback span{display:block}.feedback span+span{margin-top:4px}
</style>
