<template>
  <section class="pet-card" data-test="pet-settings-card">
    <header>
      <div class="pet-orb" aria-hidden="true">墨</div>
      <div><small>桌面学习伙伴</small><strong>{{ snapshot.pet?.displayName || '墨团' }}</strong></div>
      <span class="pet-state" :class="{ offline: !snapshot.available }">{{ snapshot.available ? stateLabel : '仅桌面端' }}</span>
    </header>
    <p>{{ snapshot.available ? (snapshot.pet?.description || '在桌边陪你学习。') : '请在 Electron 桌面应用中使用显示、拖动与动画控制。' }}</p>
    <div class="pet-control visible-control">
      <label for="pet-visible">显示伙伴</label>
      <input id="pet-visible" data-test="pet-visible" type="checkbox" :checked="snapshot.settings.visible" :disabled="busy || !snapshot.available" @change="changeVisible">
    </div>
    <div class="pet-control-grid">
      <label>大小
        <select data-test="pet-scale" :value="snapshot.settings.scale" :disabled="busy || !snapshot.available" @change="changeScale">
          <option v-for="value in scales" :key="value" :value="value">{{ Math.round(value * 100) }}%</option>
        </select>
      </label>
      <label>动画
        <select data-test="pet-speed" :value="snapshot.settings.speed" :disabled="busy || !snapshot.available" @change="changeSpeed">
          <option v-for="value in speeds" :key="value" :value="value">{{ speedLabel(value) }}</option>
        </select>
      </label>
    </div>
    <small v-if="message" class="pet-message">{{ message }}</small>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { backendApi, type PetSettings, type PetSnapshot } from '@/api'

const scales: PetSettings['scale'][] = [0.5, 0.75, 1, 1.25, 1.5]
const speeds: PetSettings['speed'][] = [0.5, 0.75, 1, 1.25, 1.5, 2]
const snapshot = reactive<PetSnapshot>({ available: false, pet: null, settings: { visible: false, scale: 1, speed: 1 }, state: 'idle' })
const busy = ref(false)
const message = ref('')
const stateLabel = computed(() => ({ idle: '安静陪伴', running: '正在努力', waiting: '等你回来', review: '认真检查', failed: '需要安慰' }[snapshot.state]))

onMounted(async () => {
  try { applySnapshot(await backendApi.pet()) }
  catch { message.value = '桌宠设置暂时无法读取。' }
})
function changeVisible(event: Event) { void update({ visible: (event.target as HTMLInputElement).checked }) }
function changeScale(event: Event) { void update({ scale: Number((event.target as HTMLSelectElement).value) as PetSettings['scale'] }) }
function changeSpeed(event: Event) { void update({ speed: Number((event.target as HTMLSelectElement).value) as PetSettings['speed'] }) }
async function update(patch: Partial<PetSettings>) {
  busy.value = true
  message.value = ''
  try { applySnapshot(await backendApi.updatePetSettings(patch)) }
  catch { message.value = '设置没有保存成功，请稍后再试。' }
  finally { busy.value = false }
}
function applySnapshot(value: PetSnapshot) {
  snapshot.available = value.available
  snapshot.pet = value.pet
  snapshot.settings = { ...value.settings }
  snapshot.state = value.state
}
function speedLabel(value: number) {
  if (value < 1) return `${value}× 舒缓`
  if (value === 1) return '1× 自然'
  return `${value}× 轻快`
}
</script>

<style scoped lang="scss">
.pet-card { margin-top: 18px; padding: 14px; color: #665c52; background: linear-gradient(145deg, #f1f7f3, #fffaf0); border: 1px solid #dfe9e2; border-radius: 16px; box-shadow: 0 10px 28px rgba(43, 82, 79, .06); }
.pet-card header { display: grid; grid-template-columns: 38px 1fr auto; align-items: center; gap: 9px; }
.pet-orb { display: grid; width: 38px; height: 38px; place-items: center; color: #fff3d2; font-family: Georgia, serif; font-size: 15px; background: #315f62; border: 3px solid #d9ebe2; border-radius: 50% 48% 46% 52%; }
.pet-card header small, .pet-card header strong { display: block; }
.pet-card header small { color: #96a49e; font-size: 9px; letter-spacing: .08em; }
.pet-card header strong { margin-top: 2px; color: #456e70; font-size: 14px; }
.pet-state { padding: 3px 7px; color: #668b82; font-size: 9px; background: #e2efe8; border-radius: 999px; }
.pet-state.offline { color: #9d8d7d; background: #eee7de; }
.pet-card > p { margin: 10px 0 12px; color: #8b8176; font-size: 10px; line-height: 1.55; }
.pet-control { display: flex; align-items: center; justify-content: space-between; }
.pet-control, .pet-control-grid label { color: #81766b; font-size: 10px; }
.visible-control { padding: 9px 0; border-top: 1px dashed #dce5df; border-bottom: 1px dashed #dce5df; }
.visible-control input { width: 28px; accent-color: #5d8985; }
.pet-control-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
.pet-control-grid label { display: grid; gap: 5px; }
.pet-control-grid select { min-width: 0; padding: 6px 7px; color: #526f6e; font-size: 10px; background: rgba(255,255,255,.72); border: 1px solid #d9e4dd; border-radius: 8px; outline: 0; }
.pet-message { display: block; margin-top: 8px; color: #aa6c5f; font-size: 9px; }
</style>
