# A3 学习助手前端

Vue 3 + TypeScript + Pinia + Element Plus 构建的 A3 学习多智能体系统前端，连接本项目的 FastAPI 后端。

## Web 开发

先在项目根目录启动后端 `127.0.0.1:8000`，再执行：

```powershell
cd E:\软件杯\front\a3-front
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。Vite 会将 `/api` 和 `/health` 代理到后端。

## 构建

```powershell
npm run build
```

该命令用于 Web 部署，保留以 `/assets/` 为根的资源路径和 Web History。产物位于当前目录的 `dist/`。

## 错误响应约定

后端所有 HTTP 非 2xx 响应均使用同一安全信封，便于 Web 开发模式和 Electron 桌面模式一致处理：

```json
{
  "code": "SESSION_NOT_FOUND",
  "message": "会话不存在。",
  "retryable": false,
  "request_id": "请求追踪标识"
}
```

- `code` 是稳定的程序化错误代码；`message` 可直接展示给用户；`retryable` 表示是否建议稍后重试。
- FastAPI 会为每个错误响应返回相同的 `X-Request-ID` 响应头和 `request_id` 正文值。
- 前端统一转换为 `BackendApiError`（为兼容旧调用，仍可使用别名 `DesktopApiError`），其中 `requestId` 对应后端的 `request_id`。非标准上游响应和网络异常只显示通用安全提示，不展示内部细节。

## Electron 桌面端

桌面端源码和发布产物均在本目录：`electron/` 保存主进程与 preload，`release/` 保存解压验证产物或安装包。界面以 HanaAgent/openhanako 的三栏工作区布局为参考，保留 A3 的学习诊断、资源和复习流程。

```powershell
cd E:\软件杯\front\a3-front
npm run desktop:dev
```

桌面打包只读取项目内的 `desktop-backend/`，其中必须包含 `api.exe` 及其 `_internal/` 目录。每个桌面命令都会先运行 `npm run build:desktop`，生成可由 `file:` 加载的相对资源路径与 hash history。

```powershell
npm run desktop:pack
npm run desktop:dist
```

正式桌面版由 Electron 主进程生成短期本地令牌、动态分配端口并启动 FastAPI。令牌和后端地址只存在于主进程；渲染进程、preload 和打包后的前端资源均不接收它们。

### 安装版模型配置

全新安装且没有模型密钥时，应用会保持本地后端在线并自动进入“模型设置”页。用户可以配置 OpenAI 兼容或 Anthropic 网关，先测试连接，再保存并启用；不需要手工编辑 `.env`。

- Electron 主进程使用 Windows `safeStorage` 加密保存模型配置，密文位于应用 userData 目录。
- API Key 不写入 localStorage、学习数据库、命令行、URL 或普通日志，也不会由后端接口返回原文。
- `safeStorage` 不可用时，生产版拒绝保存，不降级为明文文件。
- 新配置启用失败时会恢复旧密文并重启原后端；没有旧配置时继续停留在未配置状态。
- Web 开发模式仍使用后端 `POST /api/settings/model/test` 和 `PUT /api/settings/model`，这不是生产桌面端的密钥存储路径。

当前版本已提供墨团桌宠、本地知识库、教材目录、学习资源卡片、模型配置和桌面诊断；账号体系仍只保留扩展边界，不显示登录、注册或同步入口。

preload 仅暴露固定的后端请求与流式事件、模型档案、知识库、教材目录、桌面状态/诊断和桌宠桥接能力。主进程统一执行来源校验、固定路由与字段白名单、令牌注入、请求体限制、本地路径隔离和窗口关闭清理；renderer 不接收后端令牌、地址、凭据密文或用户选择的文件路径。独立 Web 开发仍可通过 Vite 代理访问 `http://127.0.0.1:8000`；Electron 不依赖固定端口。
