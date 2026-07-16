# 前端 API 层

`backend.ts` 与 FastAPI 接口一一对应，不使用静态 mock 回退。

- Web 模式使用 `WebTransport`，由 Vite 将 `/api` 和 `/health` 代理至 `127.0.0.1:8000`。
- Electron 模式使用 `DesktopTransport`，通过固定的 `window.a3Desktop` 桥接方法访问主进程 HTTP/SSE 代理。
- 旧单配置兼容入口使用 `modelConfigTest`、`modelConfigSave`；正式多配置使用 `modelProfilesList`、`modelProfileTest`、`modelProfileUpsert`、`modelProfileDelete`、`modelProfilePolicySave` 和 `modelRuntimeStatus` 固定 bridge。候选 API Key 不进入通用 URL、header 或路由代理能力。
- 后端地址和短期 `desktopToken` 只由 Electron 主进程保存；渲染进程、preload 和桌面前端包不接收这些值。
- 桌面端由主进程使用版本 2 `safeStorage` 保险库保存多配置密文，在 renderer 创建前 bootstrap 后端运行时，并通过串行事务热应用和回滚；Web 开发模式才使用公开单配置 POST/PUT 设置接口。
- renderer 只接收脱敏配置、能力声明和运行状态。学习空间偏好只保存 profile/model ID、思考强度和自动备用覆盖，不保存密钥；`/internal/model-runtime/*` 永远不经通用 transport 暴露。
- SSE `meta` 返回实际配置、模型、请求/生效思考强度和是否使用备用。首个 delta 前可自动切换；已有输出后只返回 `interrupted`，前端保留部分文本并通过新的明确请求使用备用继续。
- 桌面 SSE 事件通过 preload 转发；普通请求和流式请求均由主进程执行白名单校验、令牌注入和错误映射。
- 知识库集合、文档状态、搜索和学习空间绑定可经普通 API 管理；Web 模式不上传文件或文件路径，只能管理已经由桌面端导入的资料。
- 文件选择与拖放导入只能调用固定的 `knowledgeChooseFiles` / `knowledgeImportDroppedFiles` bridge。Electron 主进程复制并哈希文件后只向后端提交 manifest，renderer 不接触原路径、对象路径或桌面令牌。
- 本地引用只包含受控文档 ID、显示名和 page/slide/sheet_rows/paragraph locator。点击引用先进入知识库详情；桌面端可再请求主进程打开临时只读副本。
- API 错误会显示给用户，不会静默替换为假数据。

## 统一错误对象

后端 HTTP 非 2xx 响应固定为 `{ code, message, retryable, request_id }`。`WebTransport` 和 `DesktopTransport` 都会把它转换为 `BackendApiError`：

- `status`：HTTP 状态码；
- `code`、`message`、`retryable`：与后端原样对应；
- `requestId`：后端 `request_id` 的驼峰字段。

`DesktopApiError` 是 `BackendApiError` 的兼容导出。仅包含完整固定字段的错误响应会被保留；网络故障、非 JSON 或字段不完整的响应会降级为不含上游细节的通用错误。SSE 建流失败沿用同一转换规则，正常 SSE 事件协议不变。
