# 前端 API 层

`backend.ts` 与 FastAPI 接口一一对应，不使用静态 mock 回退。

- Web 模式使用 `WebTransport`，由 Vite 将 `/api` 和 `/health` 代理至 `127.0.0.1:8000`。
- Electron 模式使用 `DesktopTransport`，通过固定的 `window.a3Desktop` 桥接方法访问主进程 HTTP/SSE 代理。
- 模型连接测试和安全保存使用 `modelConfigTest`、`modelConfigSave` 固定 bridge；候选 API Key 不进入通用 URL、header 或路由代理能力。
- 后端地址和短期 `desktopToken` 只由 Electron 主进程保存；渲染进程、preload 和桌面前端包不接收这些值。
- 桌面端由主进程使用 `safeStorage` 保存模型密文并在后端启动时注入；Web 开发模式才使用后端 POST/PUT 设置接口。
- 桌面 SSE 事件通过 preload 转发；普通请求和流式请求均由主进程执行白名单校验、令牌注入和错误映射。
- API 错误会显示给用户，不会静默替换为假数据。
