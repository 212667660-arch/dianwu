# S-014 安装版安全模型配置闭环设计

> 日期：2026-07-14
> 状态：设计已由用户确认，等待文档审阅后进入实现计划
> 适用范围：`E:\软件杯\a3-front\a3-front` Electron 桌面端、Vue 前端与 `E:\软件杯\backend` FastAPI 后端

## 1. 目标

为智学协作台补齐安装版模型配置闭环，使用户在没有预置环境变量时，也能在桌面应用内安全配置 OpenAI 兼容或 Anthropic 模型服务，并在成功测试后立即使用学习诊断、资源生成和流式对话。

本设计同时保持当前暖色三栏工作台的视觉方向，延续用户指定的 openhanako 参考特征：浅米色背景、紧凑侧栏、顶部状态栏、白色卡片、低饱和强调色和清晰的状态反馈。GitHub 终端连接当前受限，精确源仓库复核留到网络恢复后的视觉回归；本设计以现有工作台和用户确认的参考方向为实现约束。

## 2. 已确认的产品行为

- 模型设置采用独立 `/model-settings` 页面，并加入侧栏固定入口。
- 首次启动没有有效模型配置时，自动进入模型设置页。
- 其他页面仍可查看；发送消息、生成资源等需要模型的操作保持禁用，已有题目的本地答题与历史查看继续可用。
- 连接测试成功并保存后，自动进入学习助手，随后恢复模型相关操作。
- 未来可能增加桌宠，但本任务只预留扩展边界，不实现桌宠 UI、角色动画或业务逻辑。
- 桌宠未来使用独立窗口、独立 IPC 通道和状态事件，不能读取模型 API Key、桌面令牌或加密配置明文。
- 账号体系只保留未来接入边界；当前不实现登录、注册、账号同步、云端数据或权限角色。

## 3. 范围与非目标

### 3.1 本任务范围

1. 新增模型设置页和路由入口。
2. 增加模型设置读取、连接测试和安全保存的前端 API。
3. Electron 主进程使用 `safeStorage` 加密保存配置。
4. Electron 启动后端时，将解密后的配置仅注入子进程环境变量。
5. 保存成功后重启后端并执行健康检查。
6. 后端启动失败时恢复旧配置和旧后端。
7. 统一模型配置相关错误的前端显示；全局 404/422 错误契约由独立任务 T-029 实施。
8. 增加前端、Electron、后端和打包启动回归测试。

### 3.2 非目标

- 不实现桌宠窗口、角色资源、动画、提醒调度或桌宠业务协议。
- 不实现账号体系、登录注册、账号同步、云端数据、权限角色、远程密钥托管或自动更新服务；只保留未来接入所需的边界。
- 不把 API Key 写入明文 `.env`、SQLite、localStorage、Pinia 持久化、命令行、URL 或日志。
- 不把任意 IPC、任意 URL、任意请求头或 Node 能力暴露给 renderer。
- 不重写现有学习状态机、SSE 事件协议和数据库结构。

## 4. 方案选择

### 4.1 采用方案：Electron 主进程安全配置

Electron 主进程是模型配置的安全边界：

```text
Vue 设置页
    | 一次性表单提交，不持久化 API Key
    v
preload 固定模型配置 IPC
    v
Electron main
    | safeStorage 加密配置
    | 通过环境变量注入后端子进程
    v
FastAPI 127.0.0.1
    | 读取 MODEL_* 环境变量
    | 只返回脱敏模型状态
    v
模型网关
```

连接测试仍通过受保护的后端 `/api/settings/model/test` 完成；测试候选配置只在本地回环请求中传递，不写入后端配置文件。保存操作由 Electron 主进程完成，生产后端不再使用 PUT 将密钥写入 `.env`。

### 4.2 未采用方案

- Python 后端 DPAPI/Credential Manager：安全性可行，但会增加 Windows 依赖、PyInstaller 复杂度和跨平台开发成本。
- 继续开放生产 PUT 并写入 `.env`：实现简单，但违反 API Key 不落明文文件的已确认安全边界。

## 5. 组件设计

### 5.1 Vue 前端

新增：

- `src/views/ModelSettings.vue`：模型配置表单、测试状态、保存状态、错误提示和安全说明。

修改：

- `src/router/index.ts`：新增 `/model-settings` 路由和侧栏图标。
- `src/layouts/AppLayout.vue`：启动后根据健康状态自动引导；统一展示“后端在线 / 模型未配置 / 模型就绪”。
- `src/stores/backend.ts`：暴露 `modelConfigured`、`modelConfiguring` 和配置后刷新方法。
- `src/api/backend.ts`：增加模型测试和安全保存业务方法。
- `src/api/types.ts`：增加配置表单、测试结果和统一错误类型。
- `src/api/transport.ts`、`src/api/desktop-transport.ts`、`src/api/web-transport.ts`：保持桌面/Web 双传输一致；桌面保存使用固定 IPC，Web 开发环境可使用受限后端测试接口。

交互约束：

- API Key 输入只保存在组件内存中的短生命周期 ref，提交成功或失败后立即清空。
- 不把 API Key 写入 `localStorage`、Pinia、路由 query、错误消息或日志。
- 保存和测试按钮在请求期间锁定，避免并发配置事务。
- 已有配置只显示 `api_key_hint`，不回填原密钥。
- 设置页继续使用现有米色背景、白色面板、窄间距表单和低饱和绿色状态标签，不引入独立视觉系统。

### 5.2 Electron 主进程

新增：

- `electron/model-config.mjs`：配置数据结构、safeStorage 加解密、原子文件写入、配置校验和回滚辅助函数。
- `electron/model-config.test.mjs`：加解密、不可用存储、配置脱敏、原子替换和回滚测试。

修改：

- `electron/main.mjs`：启动前加载配置；向后端子进程注入 `MODEL_PROVIDER`、`MODEL_BASE_URL`、`MODEL_NAME`、`MODEL_API_KEY`、`ANTHROPIC_VERSION` 和 `REQUEST_TIMEOUT_SECONDS`；注册模型保存 IPC；保存成功后重启后端并等待 ready。
- `electron/preload.mjs`：仅暴露固定的 `modelConfigTest`、`modelConfigSave` 或等价受限方法，不暴露 token、文件路径或 safeStorage 对象。
- `electron/ipc-contract.mjs`：增加模型配置 IPC 的输入字段、长度、来源和 sender 校验；禁止通过通用请求覆盖安全字段。
- `electron/backend-proxy.mjs`：允许受控的模型测试路由，并保留统一错误 envelope。
- `electron/runtime.test.mjs`、`electron/ipc-contract.test.mjs`：增加配置启动、来源校验和无密钥泄露断言。

安全存储文件：

- 位置：Electron `app.getPath('userData')` 下的专用文件，例如 `model-settings.enc`。
- 内容：`safeStorage.encryptString(JSON.stringify(config))` 的 Base64 密文和必要版本字段。
- 文件不包含可读 API Key；保存使用临时文件写入后 `replace`，避免半写入。
- `safeStorage.isEncryptionAvailable()` 为 false 时拒绝生产保存，不回退明文。

### 5.3 FastAPI 后端

修改范围保持最小：

- `backend/config.py`：继续从进程环境读取 `MODEL_*`；不增加生产明文持久化路径。
- `backend/services/model_settings.py`：保留开发模式 `.env` 兼容能力；生产模式拒绝明文 PUT，并将错误映射为结构化 envelope。
- `backend/routers/model_settings.py`：保留 GET 脱敏状态和 POST 测试；明确生产 PUT 不作为桌面保存通道。
- `backend/errors.py`、`backend/main.py`：S-014 只复用现有结构化模型错误；全局 FastAPI 验证错误和 HTTPException 统一留给 T-029。
- `backend/tests/test_model_settings.py`、`backend/tests/test_api.py`：复核生产拒绝明文保存、测试候选不落盘和 ready 状态；全局错误 envelope 回归由 T-029 补充。

## 6. 启动与保存数据流

### 6.1 启动

1. Electron 创建 userData 目录并检查 safeStorage 可用性。
2. 若存在密文配置，主进程解密并验证 provider、URL、模型名和超时范围。
3. 主进程启动后端时，把解密值仅放入子进程 `env`；不把 API Key 放入命令行或 URL。
4. 后端启动后，Electron 通过本地内部请求检查 `/health/live`。
5. renderer 调用健康状态和脱敏模型状态接口。
6. 后端在线但模型未配置时，AppLayout 自动导航 `/model-settings`。

### 6.2 测试连接

1. 用户填写 provider、base URL、model name、API Key 和超时。
2. 前端做长度、空值和格式校验。
3. Electron 校验 sender、窗口来源和候选字段，不接受 headers、URL、token 或文件路径。
4. 主进程将候选配置转发给后端测试路由。
5. 后端执行一次最小模型请求，不写 `.env`，不写数据库，不记录完整响应。
6. 返回成功延迟或结构化错误。

### 6.3 保存并启用

1. 仅当测试成功且用户确认保存时进入保存事务。
2. 主进程使用 safeStorage 加密新配置并原子替换密文文件。
3. 主进程保留旧配置内存副本，停止旧后端。
4. 使用新配置启动后端，检查 live 和 ready。
5. 新后端 ready：提交新配置状态，通知 renderer 刷新并导航学习助手。
6. 新后端失败：恢复旧密文和旧配置，重新启动旧后端；没有旧配置时保持未配置状态。
7. 事务完成后，renderer 清空 API Key 输入值，主进程不向 renderer 返回原密钥。

## 7. 错误与回滚契约

统一错误对象：

```json
{
  "code": "MODEL_AUTHENTICATION_ERROR",
  "message": "模型服务认证失败，请检查 API Key。",
  "retryable": false,
  "request_id": "..."
}
```

错误映射：

| 情况 | code | 是否可重试 | 行为 |
| --- | --- | --- | --- |
| safeStorage 不可用 | `MODEL_CREDENTIAL_STORE_UNAVAILABLE` | 否 | 禁止保存，保留当前配置 |
| base URL 非 HTTPS 或命中私网 | `MODEL_BASE_URL_INVALID` | 否 | 定位到地址字段 |
| API Key 无效 | `MODEL_AUTHENTICATION_ERROR` | 否 | 不保存候选配置 |
| 模型不存在 | `MODEL_NOT_FOUND` | 否 | 不保存候选配置 |
| 网关超时或暂时不可用 | `MODEL_TIMEOUT` / `MODEL_UNAVAILABLE` | 是 | 允许重新测试 |
| 新后端启动失败 | `MODEL_RESTART_FAILED` | 是 | 自动回滚旧配置 |
| 404/422 FastAPI 错误 | T-029 定义的稳定业务 code | 视错误而定 | 不阻塞 S-014；由独立任务统一 Web/Electron 提示 |

禁止在错误中返回：完整 API Key、Authorization、后端端口、配置文件路径、完整请求体或模型原始回答。

## 8. 桌宠扩展边界

本任务只建立扩展约束：

- 未来桌宠使用单独 `pet-window.mjs`，不复用设置页窗口。
- 主进程为桌宠定义独立 IPC namespace，例如 `a3:pet:*`，与 `a3:model:*` 分离。
- 桌宠只接收脱敏状态事件：模型就绪、当前学习阶段、生成进度和提醒状态。
- 桌宠不能调用模型配置保存、模型测试、后端启动或任意 URL 代理能力。
- 主题变量、状态事件和角色资源目录保持模块化，避免把桌宠逻辑写进 AppLayout。

## 9. 账号体系预留边界

本任务不新增账号数据表、登录路由或账号 UI。当前继续使用本地 `session_id` 作为学习会话标识，数据仍保存在本机 userData 目录。

为未来账号体系保留以下边界，但不实现：

- 将来可通过独立 `AccountProvider` 接入登录、登出、令牌刷新和账号状态，不复用模型 API Key 或 Electron 桌面令牌。
- 将来可通过数据库迁移增加 `account_id` 与会话归属，当前表结构不提前加入空字段或伪账号数据。
- 将来账号同步只能经过明确的远程 API 和隐私授权；本地模型配置、API Key 和桌面令牌永不进入账号同步 payload。
- 当前侧栏不显示登录入口、账号头像或同步状态，避免形成未实现承诺。

## 10. 测试与验收矩阵

### 10.1 前端

- 设置页渲染、字段校验、测试中禁用按钮、成功保存后清空 Key。
- 未配置状态自动导航；就绪状态不强制导航。
- Web 和 Electron 使用同一业务方法，错误提示一致。
- 侧栏视觉与现有暖色三栏工作台保持一致，375 px 窄屏可操作。

### 10.2 Electron

- safeStorage 可用时密文保存和读取成功。
- safeStorage 不可用时保存拒绝且不创建明文文件。
- 密文文件不包含原始 API Key。
- renderer 输入不能覆盖 token、URL、headers 或文件路径。
- 测试失败不写入新配置；重启失败恢复旧配置。
- 启动命令、日志、IPC 响应和构建产物不包含 API Key。
- 未来桌宠 namespace 不能访问模型配置 IPC。

### 10.3 后端

- 生产 PUT 不写明文 `.env`。
- POST 测试使用候选配置但不持久化。
- `/health/ready` 在无模型配置时返回结构化 503，在有效配置时返回 ready。
- 模型配置相关业务异常返回结构化错误 envelope；全局 404/422 统一由 T-029 验收。
- 模型认证、权限、模型不存在、429、超时和 SSE 失败都能被前端稳定显示。

### 10.4 发布验收

```text
backend\quick_test.ps1
cd a3-front\a3-front && npm run test
cd a3-front\a3-front && npm run build
cd a3-front\a3-front && npm run build:desktop
cd a3-front\a3-front && npm run desktop:pack
cd a3-front\a3-front && npm run desktop:dist
```

额外执行全新 userData 隔离启动：无环境变量时应用自动进入模型设置；使用测试网关成功配置后，重启应用能保持模型就绪；故意提供错误配置时旧配置可恢复。

## 11. 完成标准

- 全新安装版可以在应用内完成模型配置，不需要用户手动编辑 `.env`。
- API Key 只存在于设置输入的短生命周期、Electron 主进程内存和系统加密存储中。
- 模型配置测试、保存、重启、回滚和 ready 状态均有自动化回归。
- 现有诊断、画像、资源、SSE、答题、复习和 Electron 生命周期测试不回归。
- 当前界面保持 openhanako 参考的暖色桌面工作台方向，并为桌宠留下隔离扩展边界。
- 当前不出现登录、注册或账号同步入口，但未来可通过独立账号边界接入，不与模型凭据或桌面令牌耦合。
