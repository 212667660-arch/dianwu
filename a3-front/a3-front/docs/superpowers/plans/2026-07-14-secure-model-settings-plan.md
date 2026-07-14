# S-014 安装版安全模型配置闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Windows Electron 安装版可以在应用内安全测试、保存和启用模型配置，并在配置失败时自动回滚，同时保持 openhanako 参考的暖色桌面工作台与未来桌宠、账号体系扩展边界。

**Architecture:** Electron main process 通过 `safeStorage` 加密保存模型配置，并在启动 FastAPI 子进程时以环境变量注入；renderer 只通过固定 IPC 提交一次性表单，不接触令牌、文件路径或持久化密钥。模型测试和保存由 main process 的固定控制器执行，保存事务包含后端重启、ready 检查和旧配置回滚。全局 404/422 错误契约属于独立的 T-029，不在本计划中实现。

**Tech Stack:** Electron 32、Vue 3、TypeScript、Pinia、FastAPI、Node `node:test`、Vitest、Pytest、PyInstaller onedir。

---

## 文件地图

- Create: `electron/model-config.mjs` — safeStorage 配置格式、校验、原子写入和恢复。
- Create: `electron/model-config-controller.mjs` — trusted sender 校验、模型测试和保存/重启/回滚事务。
- Create: `electron/model-config.test.mjs` — 加密存储和回滚单元测试。
- Create: `electron/model-config-controller.test.mjs` — 测试、保存、失败回滚和密钥泄露回归。
- Create: `src/views/ModelSettings.vue` — 独立模型设置页。
- Create: `src/views/ModelSettings.test.ts` — 模型设置页交互、密钥清理和保存状态测试。
- Modify: `electron/main.mjs` — 启动注入、ready 检查、模型配置 IPC 和后端重启。
- Modify: `electron/preload.mjs` — 固定 `modelConfigTest`、`modelConfigSave` bridge。
- Modify: `electron/ipc-contract.mjs` — 模型配置候选输入校验与安全字段拒绝。
- Modify: `electron/runtime.test.mjs`、`electron/ipc-contract.test.mjs`、`electron/backend-proxy.test.mjs` — Electron 生命周期、请求边界和无密钥泄露回归。
- Modify: `src/api/types.ts`、`src/api/transport.ts`、`src/api/backend.ts`、`src/api/index.ts` — 配置表单、测试结果和双传输业务 API。
- Modify: `src/api/desktop-transport.test.ts`、`src/api/backend.test.ts` — bridge 调用和配置 API 测试。
- Modify: `src/stores/backend.ts`、`src/stores/backend.test.ts` — 配置状态、首次引导和保存后刷新。
- Modify: `src/router/index.ts`、`src/layouts/AppLayout.vue`、`src/layouts/AppLayout.test.ts` — `/model-settings` 入口和未配置自动导航。
- Modify: `src/views/SmartTutor.vue`、`src/views/SmartTutor.test.ts` — 未就绪时禁止模型发送。
- Modify: `README.md`、`src/api/README.md` — 安装版配置说明、safeStorage 边界和开发模式回退。
- Modify: `codex/AI模型任务队列.md` — S-014 文件、命令和验收结果。

---

### Task 1: 建立 safeStorage 配置存储的失败测试

**Files:**
- Create: `electron/model-config.test.mjs`
- Create: `electron/model-config.mjs`

- [ ] **Step 1: 写最小失败测试**

在 `electron/model-config.test.mjs` 中先写可注入 fake safeStorage 和临时文件系统的测试，测试公开行为而不是内部实现：

```js
test('保存配置只写入密文并可读取同一配置', async () => {
  const safeStorage = {
    isEncryptionAvailable: () => true,
    encryptString: value => Buffer.from(`cipher:${value}`, 'utf8'),
    decryptString: value => Buffer.from(value).toString('utf8').slice('cipher:'.length),
  }
  const store = createModelConfigStore({ safeStorage, filePath: tempPath })
  const input = validModelConfig()

  await store.save(input)

  const bytes = await fs.readFile(tempPath)
  assert.doesNotMatch(bytes.toString('utf8'), /test-secret-key/)
  assert.deepEqual(await store.load(), input)
})

test('safeStorage 不可用时拒绝保存且不创建明文文件', async () => {
  const store = createModelConfigStore({
    safeStorage: { isEncryptionAvailable: () => false },
    filePath: tempPath,
  })

  await assert.rejects(() => store.save(validModelConfig()), error => error.code === 'MODEL_CREDENTIAL_STORE_UNAVAILABLE')
  await assert.rejects(fs.access(tempPath))
})

test('原子替换前的旧密文可以恢复', async () => {
  const store = createModelConfigStore({ safeStorage, filePath: tempPath })
  const oldConfig = validModelConfig({ model_name: 'old-model' })
  const newConfig = validModelConfig({ model_name: 'new-model' })
  await store.save(oldConfig)
  const snapshot = await store.snapshot()
  await store.save(newConfig)
  await store.restore(snapshot)

  assert.deepEqual(await store.load(), oldConfig)
})
```

`validModelConfig` 必须包含 `provider`、`api_key`、`base_url`、`model_name`、`anthropic_version` 和 `request_timeout_seconds`；测试文件使用 `mkdtemp`，每个测试结束清理自己的目录。

- [ ] **Step 2: 运行测试确认红灯**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
node --test electron/model-config.test.mjs
```

Expected: FAIL，因为 `electron/model-config.mjs` 尚未导出 `createModelConfigStore`。

- [ ] **Step 3: 实现最小存储模块**

实现以下稳定接口：

```js
export const MODEL_CONFIG_VERSION = 1

export function createModelConfigStore({ safeStorage, filePath, fsImpl = fs }) {
  return { load, snapshot, save, restore }
}
```

实现规则：

1. `save(config)` 先检查 `safeStorage.isEncryptionAvailable()`，再校验字段长度和 provider。
2. 文件内容为 `{ version: 1, payload: base64(safeStorage.encryptString(JSON.stringify(config))) }`，不写入原文。
3. 使用同目录随机临时文件 `writeFile` 后 `rename`/`replace`，避免半写入。
4. `snapshot()` 返回旧文件字节或 `null`；`restore(null)` 删除当前文件，`restore(bytes)` 原子写回旧字节。
5. `load()` 对不存在文件返回 `null`，对版本、Base64 或解密失败返回结构化 `MODEL_CREDENTIAL_STORE_INVALID`，不回退明文。
6. 同一模块导出纯函数 `modelEnvironment(config)`，只返回 `MODEL_PROVIDER`、`MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME`、`ANTHROPIC_VERSION` 和 `REQUEST_TIMEOUT_SECONDS`，便于 Electron 启动注入和单元测试。

- [ ] **Step 4: 运行测试确认绿灯**

Run the same command. Expected: all storage tests pass and the test output contains no secret value.

---

### Task 2: 为配置输入和主进程控制器建立失败测试

**Files:**
- Modify: `electron/ipc-contract.mjs`
- Create: `electron/model-config-controller.mjs`
- Create: `electron/model-config-controller.test.mjs`
- Modify: `electron/ipc-contract.test.mjs`

- [ ] **Step 1: 写输入校验和控制器失败测试**

增加以下行为测试：

```js
test('模型配置候选只接受固定字段并拒绝 headers、token 和文件路径', () => {
  assert.equal(validateModelConfigInput(validModelConfig()).ok, true)
  for (const field of ['headers', 'token', 'filePath', 'baseUrl']) {
    const input = { ...validModelConfig(), [field]: 'secret' }
    assert.equal(validateModelConfigInput(input).error.code, 'DESKTOP_REQUEST_DENIED')
  }
})

test('测试失败时保存控制器不写入配置且不重启后端', async () => {
  const restart = mock.fn()
  const controller = createModelConfigController({
    validateSender: () => true,
    testCandidate: async () => ({ ok: false, status: 401, error: authError() }),
    configStore: fakeStoreWithOldConfig(),
    restart,
  })

  const result = await controller.save(fakeEvent(), validModelConfig())

  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'MODEL_AUTHENTICATION_ERROR')
  assert.equal(restart.mock.calls.length, 0)
})

test('新后端 ready 失败时恢复旧配置并返回 MODEL_RESTART_FAILED', async () => {
  const store = fakeStoreWithOldConfig()
  const controller = createModelConfigController({
    validateSender: () => true,
    testCandidate: async () => ({ ok: true, status: 200, data: connectedResult() }),
    configStore: store,
    restart: async () => { throw Object.assign(new Error('ready timeout'), { code: 'MODEL_RESTART_FAILED' }) },
  })

  const result = await controller.save(fakeEvent(), validModelConfig())

  assert.equal(result.error.code, 'MODEL_RESTART_FAILED')
  assert.deepEqual(await store.load(), oldConfig)
})
```

- [ ] **Step 2: 运行控制器测试确认红灯**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
node --test electron/model-config-controller.test.mjs electron/ipc-contract.test.mjs
```

Expected: FAIL because the validator, controller and model-specific IPC behavior do not exist.

- [ ] **Step 3: 实现固定候选校验和控制器**

`validateModelConfigInput` 只接受：`provider`、`api_key`、`base_url`、`model_name`、`anthropic_version`、`request_timeout_seconds`；拒绝未知键、空白值、控制字符、超长值、非有限超时和不支持 provider。生产候选地址必须经过现有 `validate_model_base_url` 规则，开发地址只能在明确开发开关下允许。

`createModelConfigController` 接受依赖注入：

```js
createModelConfigController({
  validateSender,
  configStore,
  testCandidate,
  restart,
  getCurrentSettings,
})
```

公开方法：

```js
controller.test(event, input) // 固定调用后端 POST /api/settings/model/test
controller.save(event, input) // 再测一次，safeStorage 保存，restart，失败 restore
```

控制器必须在每次操作前校验 `event.sender`、`senderFrame.url` 和窗口未销毁；任何失败只返回 `{ ok, status, error }`，不得返回候选 API Key。

- [ ] **Step 4: 运行测试确认绿灯**

Run the same command. Expected: validator、测试失败不保存、新后端失败回滚和 sender 拒绝测试全部通过。

---

### Task 3: 接入 Electron 启动注入和配置 IPC

**Files:**
- Modify: `electron/main.mjs`
- Modify: `electron/preload.mjs`
- Modify: `electron/runtime.test.mjs`
- Modify: `electron/backend-proxy.test.mjs`

- [ ] **Step 1: 写启动注入与 ready 回滚失败测试**

在生命周期测试中增加可注入 `spawn`/`waitForBackendReady` 的测试，先规定：

```js
test('后端子进程环境包含解密配置但命令行和日志不包含 API Key', async () => {
  const env = modelEnvironment(validModelConfig({ api_key: 'secret-key' }))

  assert.equal(env.MODEL_API_KEY, 'secret-key')
  assert.doesNotMatch(JSON.stringify({ args: [], log: '' }), /secret-key/)
})

test('modelConfigSave 和 modelConfigTest 只由受信 renderer 调用', async () => {
  const foreignEvent = makeForeignEvent()
  const result = await invokeModelConfigSave(foreignEvent, validModelConfig())
  assert.equal(result.error.code, 'DESKTOP_REQUEST_DENIED')
})
```

- [ ] **Step 2: 运行测试确认红灯**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
node --test electron/runtime.test.mjs electron/backend-proxy.test.mjs electron/model-config-controller.test.mjs
```

Expected: FAIL，因为 main 尚未加载密文配置、注入 `MODEL_*`，也没有固定模型 IPC。

- [ ] **Step 3: 实现启动和 IPC**

修改 `startBackend`：

```js
const modelConfig = await modelConfigStore.load()
const childEnv = {
  ...process.env,
  A3_HOST: '127.0.0.1',
  A3_PORT: String(port),
  A3_DATA_DIR: command.dataDir,
  DESKTOP_TOKEN: token,
  APP_ENV: app.isPackaged ? 'production' : 'development',
  ...(modelConfig ? modelEnvironment(modelConfig) : {}),
}
```

新增 `waitForBackendReady(baseUrl, token)`：请求 `/health/ready` 时只在 main 内添加 `X-A3-Desktop-Token`，ready 返回 200 才完成保存后的重启。

新增固定 IPC：

```js
ipcMain.handle('a3:model-config-test', (event, input) => modelConfigController.test(event, input))
ipcMain.handle('a3:model-config-save', (event, input) => modelConfigController.save(event, input))
```

`preload.mjs` 只暴露：

```js
modelConfigTest: input => ipcRenderer.invoke('a3:model-config-test', input)
modelConfigSave: input => ipcRenderer.invoke('a3:model-config-save', input)
```

不把模型测试路径加入通用 renderer 路由白名单；控制器内部使用固定路径和 main 持有的 token。保存流程保留旧配置快照，重启 ready 失败时恢复密文并重新启动旧后端。

- [ ] **Step 4: 运行 Electron 单元测试确认绿灯**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
node --test electron/runtime.test.mjs electron/backend-proxy.test.mjs electron/model-config.test.mjs electron/model-config-controller.test.mjs electron/ipc-contract.test.mjs
```

Expected: 所有现有生命周期、代理、窗口清理和新增配置测试通过。

---

### Task 4: 接入前端 API、类型和 transport

**Files:**
- Modify: `src/api/types.ts`
- Modify: `src/api/transport.ts`
- Modify: `src/api/backend.ts`
- Modify: `src/api/index.ts`
- Modify: `src/api/desktop-transport.test.ts`
- Modify: `src/api/backend.test.ts`

- [ ] **Step 1: 写失败测试**

增加类型和 bridge 行为测试：

```ts
it('桌面模型测试和保存使用固定 bridge 方法，不走任意 URL', async () => {
  const bridge = fakeBridge()
  vi.mocked(bridge.modelConfigTest).mockResolvedValue({
    ok: true, status: 200,
    data: { provider: 'openai', model_name: 'test', status: 'connected', latency_ms: 12 },
  })

  await expect(backendApi.testModelSettings(validInput())).resolves.toMatchObject({ status: 'connected' })
  expect(bridge.modelConfigTest).toHaveBeenCalledWith(validInput())
  expect(bridge.request).not.toHaveBeenCalledWith(expect.objectContaining({ path: expect.stringContaining('file:') }))
})
```

- [ ] **Step 2: 运行前端测试确认红灯**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
npx vitest run src/api/backend.test.ts src/api/desktop-transport.test.ts
```

Expected: FAIL because `ModelConfigInput`, `modelConfigTest`, `modelConfigSave` and the backend methods do not exist.

- [ ] **Step 3: 实现类型和双传输 API**

在 `src/api/types.ts` 增加：

```ts
export interface ModelConfigInput {
  provider: 'openai' | 'anthropic'
  api_key: string
  base_url: string
  model_name: string
  anthropic_version: string
  request_timeout_seconds: number
}

export interface ModelConnectionTest {
  provider: 'openai' | 'anthropic'
  model_name: string
  status: 'connected'
  latency_ms: number
}
```

在 `DesktopBridge` 增加 `modelConfigTest` 和 `modelConfigSave`，在 `backendApi` 增加：

```ts
testModelSettings(input: ModelConfigInput): Promise<ModelConnectionTest>
saveModelSettings(input: ModelConfigInput): Promise<ModelSettings>
```

Electron 使用固定 bridge；Web 开发模式使用现有 POST `/api/settings/model/test` 和 PUT `/api/settings/model`，方便本地开发与后端测试。两种路径都通过 `DesktopApiError`/`errorMessage` 返回统一可读错误。

- [ ] **Step 4: 运行测试确认绿灯**

Run:

```powershell
npx vitest run src/api/backend.test.ts src/api/desktop-transport.test.ts
```

Expected: 新增配置 API 测试与原 SSE 解析测试全部通过。

---

### Task 5: 接入 Pinia 状态和首次启动导航

**Files:**
- Modify: `src/stores/backend.ts`
- Modify: `src/stores/backend.test.ts`
- Modify: `src/router/index.ts`
- Modify: `src/layouts/AppLayout.vue`
- Modify: `src/layouts/AppLayout.test.ts`

- [ ] **Step 1: 写失败测试**

增加以下状态和导航测试：

```ts
it('模型未配置但后端在线时标记 modelConfigured=false', async () => {
  apiMock.modelSettings.mockResolvedValue({ ...settings, api_key_configured: false, api_key_hint: '' })
  await store.refreshHealth()
  expect(store.modelConfigured).toBe(false)
})

it('启动刷新后将未配置用户导航到模型设置页', async () => {
  backendMock.live = true
  backendMock.model = { api_key_configured: false }
  await mountLayoutAndFlush()
  expect(router.currentRoute.value.path).toBe('/model-settings')
})
```

- [ ] **Step 2: 运行测试确认红灯**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
npx vitest run src/stores/backend.test.ts src/layouts/AppLayout.test.ts
```

Expected: FAIL because `modelConfigured`、模型设置路由和自动导航尚未存在。

- [ ] **Step 3: 实现状态和导航**

在 store 中增加：

```ts
const modelConfigured = computed(() => model.value?.api_key_configured === true)
const modelConfigBusy = ref(false)
async function refreshModelSettings() { model.value = await backendApi.modelSettings() }
async function testModelSettings(input) { modelConfigBusy.value = true; try { return await backendApi.testModelSettings(input) } finally { modelConfigBusy.value = false } }
async function saveModelSettings(input) { modelConfigBusy.value = true; try { const value = await backendApi.saveModelSettings(input); model.value = value; await refreshHealth(); return value } finally { modelConfigBusy.value = false } }
```

`AppLayout` 在首次 `await backend.refreshAll()` 后执行：

```ts
if (backend.live && !backend.modelConfigured && route.path !== '/model-settings') {
  await router.replace('/model-settings')
}
```

只在后端在线且明确返回未配置时导航；后端离线不能覆盖用户当前页面。模型设置路由加入侧栏但不加入账号或桌宠入口。

- [ ] **Step 4: 运行测试确认绿灯**

Run:

```powershell
npx vitest run src/stores/backend.test.ts src/layouts/AppLayout.test.ts
```

Expected: store 状态、侧栏路由和首次导航测试通过，原后端退出处理不回归。

---

### Task 6: 实现 openhanako 风格模型设置页并锁定模型操作

**Files:**
- Create: `src/views/ModelSettings.vue`
- Modify: `src/views/SmartTutor.vue`
- Modify: `src/views/SmartTutor.test.ts`
- Modify: `src/styles/global.scss` only when existing variables cannot express the page without a new visual system

- [ ] **Step 1: 写页面失败测试**

测试页面行为而非 Element Plus 内部实现：

```ts
it('未配置时显示安全说明和测试按钮，发送保存期间禁用重复操作', async () => {
  apiMock.testModelSettings.mockImplementation(() => new Promise(resolve => { resolveTest = resolve }))
  const wrapper = mount(ModelSettings, { global: { plugins: [pinia], stubs } })
  await wrapper.get('[data-testid="model-test"]').trigger('click')
  expect(wrapper.get('[data-testid="model-test"]').attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('密钥由系统安全存储加密')
})

it('模型未就绪时学习助手发送按钮不可用', () => {
  storeMock.modelConfigured = false
  const wrapper = mount(SmartTutor, { global: { stubs } })
  expect(wrapper.get('[data-testid="send-message"]').attributes('disabled')).toBeDefined()
})
```

- [ ] **Step 2: 运行测试确认红灯**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
npx vitest run src/views/SmartTutor.test.ts
```

Expected: FAIL because the settings page and model readiness guard do not exist.

- [ ] **Step 3: 实现页面**

页面结构固定为：

1. 页面标题“模型设置”和服务状态 pill。
2. provider、model name、base URL、API Key、超时字段。
3. “测试连接”按钮和 latency/错误反馈。
4. “保存并启用”按钮，仅在最近一次测试成功后可用。
5. 安全说明：密钥只进入 Electron 主进程加密存储，不写入明文文件。
6. 配置成功后显示“模型已就绪”和进入学习助手按钮。

视觉规则：复用 `--surface`、`--surface-soft`、`--line`、`--accent`、`panel`、`page-heading` 和 `status-pill`；使用现有圆角、浅米色背景、紧凑间距和窄屏媒体规则。不要加入桌宠按钮、账号头像或登录入口。

API Key 只绑定组件 ref；测试、保存、成功、失败和卸载时都清空；任何错误文本不得包含 input 对象。

在 `SmartTutor.vue` 中让发送按钮同时满足 `editor.trim()` 与 `backend.modelConfigured`，`send()` 内再次检查，避免只依赖 DOM disabled。

- [ ] **Step 4: 运行页面测试确认绿灯**

Run:

```powershell
npx vitest run src/views/SmartTutor.test.ts src/views/ModelSettings.test.ts
```

Expected: 设置页交互、密钥清理、错误反馈和未就绪发送保护全部通过。

---

### Task 7: 完成安装版、Web 开发和发布验证

**Files:**
- Modify: `README.md`
- Modify: `src/api/README.md`
- Modify: `codex/AI模型任务队列.md`
- Verify: `desktop-backend/` and `release/` generated outputs

- [ ] **Step 1: 写发布验收脚本/断言**

在现有 Node 测试中增加源码扫描：

```js
for (const file of rendererAndPreloadFiles) {
  assert.doesNotMatch(fs.readFileSync(file, 'utf8'), /MODEL_API_KEY|api_key.*secret|desktopToken|X-A3-Desktop-Token/)
}
```

增加隔离 userData 验收步骤：启动打包 Electron 测试模式，确认后端 live；使用 fake model gateway 或已有离线测试替身完成测试/保存；检查 ready；注入错误配置并确认旧配置恢复；结束后确认没有 `api.exe` 残留。

- [ ] **Step 2: 运行前端和后端完整测试**

Run:

```powershell
cd E:\软件杯\backend
powershell -NoProfile -ExecutionPolicy Bypass -File .\quick_test.ps1
cd E:\软件杯\a3-front\a3-front
npm run test
npm run build
npm run build:desktop
```

Expected: 后端全部测试、Electron Node 测试、Vitest 和 Web/desktop build 均退出码 0。

- [ ] **Step 3: 重建并验证桌面包**

Run:

```powershell
cd E:\软件杯\a3-front\a3-front
npm run desktop:pack
npm run desktop:dist
```

再运行隔离 userData 的安装版启动检查，验证模型未配置引导、配置状态显示、后端生命周期和密钥扫描。

- [ ] **Step 4: 更新文档和队列**

README 必须说明：

- 安装版首次启动进入模型设置，不需要手动编辑 `.env`。
- 生产版 API Key 使用 Windows safeStorage；safeStorage 不可用时禁止保存。
- Web 开发模式仍可用现有 PUT/POST 后端接口，但不代表生产桌面路径。
- 账号体系和桌宠只预留扩展边界，当前版本没有入口。

在 `codex/AI模型任务队列.md` 中记录实际修改文件、每条验证命令、测试数量、安装包路径和全新 userData 验收结果；只有所有验收通过后才把 S-014 改为“完成”。

---

## 计划自检

- 设计文档的安全存储、启动注入、测试、保存、回滚、首次引导、视觉约束、桌宠扩展和账号预留均有对应任务。
- T-029 的全局 404/422 统一已明确排除，避免 S-014 跨任务实现。
- 所有新增生产代码均先有失败测试步骤；每个测试步骤都有明确命令和预期结果。
- 计划不要求新增账号表、登录入口、桌宠 UI 或远程服务。
- 计划中没有未决定的占位项；safeStorage 不可用时的行为、旧配置回滚和密钥清理均已固定。
