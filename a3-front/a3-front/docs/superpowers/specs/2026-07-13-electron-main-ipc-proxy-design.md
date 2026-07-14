# Electron 主进程 HTTP/SSE IPC 代理设计

> 任务：S-011 细化 Electron 主进程 HTTP/SSE IPC 代理与令牌隔离方案  
> 日期：2026-07-13  
> 范围：`E:\软件杯\a3-front\a3-front`

## 1. 目标

最终交付物是 Windows Electron 应用。Electron renderer 不持有 FastAPI 地址、本地桌面令牌或任意请求头；Electron main process 持有运行期地址和令牌，验证 renderer 请求后代理普通 HTTP 与 SSE。浏览器直连只作为开发调试回退，不作为桌面交付架构。

本设计延续 S-007、S-008 的信任边界，同时保留当前 Vue 页面与 `backendApi` 调用形态，避免页面组件感知 IPC 细节。

## 2. 不在本任务范围内

- 不改变 FastAPI 路由、学习状态机、SSE 事件字段或数据库结构。
- 不新增远程服务、自动更新、账号体系或多窗口业务。
- 不在 IPC 中提供任意 URL、任意请求头、文件系统或通用 `ipcRenderer` 能力。
- 不在本任务中重做模型密钥 UI；模型设置继续使用现有后端接口边界。

## 3. 方案选择

采用“受限通用传输 + 路由白名单”方案：renderer 使用统一的 request/stream/cancel 接口，main process 只允许项目已使用的 method/path 组合。相比逐接口 IPC，它减少重复映射；相比向 renderer 注入 token，它满足既有安全设计。

桌面与浏览器共用 `backendApi` 业务方法，但传输层分离：

- Electron：`DesktopTransport` 调用 preload 暴露的固定 IPC。
- 浏览器开发：`WebTransport` 使用 Axios/fetch 直连开发后端。
- 页面与 Pinia store 不读取运行地址、令牌或 IPC channel。

## 4. 组件边界

### 4.1 Electron main process

新增独立代理模块，职责包括：

- 保存仅存在于 main process 内存的 `baseUrl` 与 `desktopToken`。
- 验证 method、path、query、body、sender、frame URL 和窗口归属。
- 注入 `X-A3-Desktop-Token`，请求固定的 `127.0.0.1` 后端。
- 将普通响应转换为统一 envelope。
- 读取、解析 SSE 并向所属窗口转发结构化事件。
- 管理 streamId、AbortController 和窗口销毁清理。

`electron/main.mjs` 只负责进程生命周期、窗口创建和 IPC handler 注册；HTTP/SSE 细节放入小型模块，避免主文件继续膨胀。

### 4.2 Preload

`preload.mjs` 只暴露以下固定能力：

```ts
interface A3DesktopBridge {
  request(input: DesktopRequest): Promise<DesktopResponse>
  startStream(streamId: string, input: DesktopRequest): void
  cancelStream(streamId: string): void
  onStreamEvent(listener: (message: DesktopStreamMessage) => void): () => void
  onBackendExit(listener: (payload: { code: number | null }) => void): () => void
}
```

不得暴露 `apiBaseUrl`、`desktopToken`、任意 IPC channel、Node 对象或外链打开方法。preload 负责隐藏真实 channel 名称，并返回事件退订函数。

### 4.3 Renderer transport

新增传输抽象，业务 API 只依赖：

```ts
interface BackendTransport {
  request<T>(input: TransportRequest): Promise<T>
  stream(
    input: TransportRequest,
    onEvent: (event: StreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<void>
}
```

Electron 存在 `window.a3Desktop` 时使用 DesktopTransport；否则使用 WebTransport。桌面流使用 renderer 生成的非安全性唯一 `streamId`，先注册事件监听，再发送 start；收到 done/error 后退订。AbortSignal 触发 `cancelStream`。

## 5. IPC 契约

### 5.1 普通请求

renderer 只能发送结构化字段：

```ts
interface DesktopRequest {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  path: string
  query?: Record<string, string | number | boolean>
  body?: unknown
}

type DesktopResponse =
  | { ok: true; status: number; data: unknown }
  | { ok: false; status: number; error: DesktopError }

interface DesktopError {
  code: string
  message: string
  retryable: boolean
  requestId?: string
}
```

renderer 不得传递完整 URL、认证头或其他 header。main process 对 JSON 编码后的 query/body 设 64 KiB 输入上限，对普通响应设 5 MiB 上限。

### 5.2 路由白名单

S-011 初始只允许当前前端实际使用的路由：

- `GET /health/live`
- `GET /health/ready`
- `GET /api/settings/model`
- `POST /api/chat`
- `DELETE /api/generations/{generation_id}`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/rediagnose`
- `GET /api/sessions/{session_id}/progress`
- `GET /api/sessions/{session_id}/next-action`
- `GET /api/sessions/{session_id}/reviews`
- `GET /api/sessions/{session_id}/mistakes`
- `POST /api/sessions/{session_id}/questions/{question_id}/attempts`
- `POST /api/chat/stream`，仅允许作为流请求

path 必须是以 `/` 开头的相对 API 路径，不得包含 scheme、host、fragment、反斜杠、编码后的路径穿越或 `..` 段。动态 `session_id`、`generation_id` 和数字 ID 使用与后端一致的正则和长度限制。

### 5.3 SSE

SSE 使用三个内部 channel：start、cancel、event。它们只在 main/preload 之间出现，不暴露给页面源码。

主进程维护：

```text
(webContents.id, streamId) -> {
  controller,
  sessionId,
  generationId?,
  startedAt
}
```

转发消息为：

```ts
type DesktopStreamMessage =
  | { streamId: string; type: 'event'; event: StreamEvent }
  | { streamId: string; type: 'done' }
  | { streamId: string; type: 'error'; error: DesktopError }
```

main process 解析 SSE block 后再转发，不把原始响应对象或 header 交给 renderer。单个 SSE 事件上限 256 KiB，未完成缓冲上限 512 KiB；超过限制时中止该流并返回稳定错误。每个窗口最多同时存在 4 个流。

### 5.4 取消与清理

- renderer 的 AbortSignal、页面卸载或用户本地取消会发送 cancelStream。
- main process 只允许原始 sender 取消自己创建的 streamId。
- cancelStream 调用 AbortController；FastAPI 的 `request.is_disconnected` 负责停止流式生成。
- 已获得 generation_id 时，现有显式取消 API 仍可通过普通代理调用；重复取消返回的 404 按现有前端错误规则处理。
- stream done/error、webContents destroyed、非预期导航、后端退出和 app quit 都必须删除映射并中止未完成请求。

## 6. Sender 与导航校验

所有普通请求、start 和 cancel 都必须同时满足：

1. `event.sender === mainWindow.webContents`。
2. `event.senderFrame.url` 精确匹配已加载的 `dist/index.html` file URL。
3. sender 尚未 destroyed。

不因 renderer 提供的 streamId、session_id 或 URL 字符串推断信任。IPC handler 不记录 token、完整请求体或模型密钥。

## 7. 错误处理

main process 优先解析后端的 `{code, message, retryable, request_id}`；无法解析时按 HTTP 状态映射为稳定错误。网络失败、响应过大、SSE 格式错误、窗口销毁和主动取消使用不同错误码。

建议的桌面代理错误码：

- `DESKTOP_REQUEST_DENIED`
- `DESKTOP_REQUEST_INVALID`
- `DESKTOP_BACKEND_UNAVAILABLE`
- `DESKTOP_RESPONSE_TOO_LARGE`
- `DESKTOP_STREAM_INVALID`
- `DESKTOP_STREAM_LIMITED`
- `DESKTOP_STREAM_CANCELLED`

错误只向 renderer 暴露安全消息；详细异常写入 Electron 日志，但不得包含 token、Authorization、API Key 或完整学习内容。

## 8. 开发模式

普通浏览器开发仍可使用 Vite 代理和 WebTransport。它不影响 Electron 的安全验收；生产安装包始终选择 DesktopTransport。WebTransport 不读取 `a3Desktop` token，也不作为生产桌面后备路径。如果桌面 bridge 缺失，桌面构建应显示明确启动错误，不静默回退到 `127.0.0.1:8000`。

## 9. 测试与验收

至少覆盖：

1. preload 和 renderer 源码、构建产物都不包含 `desktopToken` 或 `apiBaseUrl` 注入。
2. 任意 URL、错误 method、未知 path、路径穿越、超大 body 和错误 sender 均被拒绝。
3. 允许的普通 GET/POST/DELETE 请求由 main 注入 token，renderer 输入无法覆盖 header。
4. HTTP 错误和网络错误映射为稳定 envelope，不泄露内部地址或令牌。
5. SSE delta、replace、sources、error、done 按顺序转发，分块边界不影响解析。
6. streamId 只能由所属窗口取消；取消、窗口销毁、后端退出后没有残留 controller 或监听器。
7. Electron 与浏览器传输对同一 `backendApi` 返回相同业务类型。
8. 现有 Node、Vitest、Web build、desktop build、desktop:pack 和 NSIS 构建全部通过。
9. 测试模式实际启动 Electron，日志出现 backend ready，自动退出后无 `api.exe` 残留。

## 10. 实施顺序

1. 先建立共享 IPC 类型、路由白名单和失败测试。
2. 实现普通 HTTP 代理及错误 envelope。
3. 实现 SSE parser、stream registry、取消与窗口清理。
4. 收紧 preload，删除 runtime-info/token/baseUrl 注入。
5. 将前端 API 改为 DesktopTransport/WebTransport 双适配。
6. 增加 renderer、main、SSE 和安全回归测试。
7. 重新执行桌面运行、unpacked 与 NSIS 验收。

## 11. 完成标准

- Electron renderer、preload 暴露对象和前端构建产物均不持有本地 token。
- renderer 无法借 IPC 请求白名单外地址、路由或 header。
- 普通学习流程、流式生成、取消、错题、复习和历史在安装包中可用。
- 关闭应用后没有残留后端或流式请求。
- S-007/S-008 的 renderer/main/backend 信任边界与实际代码一致。
