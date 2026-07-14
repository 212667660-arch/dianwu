# A3 学习助手前端

Vue 3 + TypeScript + Pinia + Element Plus 构建的 A3 学习多智能体系统前端，连接本项目的 FastAPI 后端。

## Web 开发

先在项目根目录启动后端 `127.0.0.1:8000`，再执行：

```powershell
cd E:\软件杯\a3-front\a3-front
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。Vite 会将 `/api` 和 `/health` 代理到后端。

## 构建

```powershell
npm run build
```

该命令用于 Web 部署，保留以 `/assets/` 为根的资源路径和 Web History。产物位于当前目录的 `dist/`。

## Electron 桌面端

桌面端源码和发布产物均在本目录：`electron/` 保存主进程与 preload，`release/` 保存解压验证产物或安装包。界面以 HanaAgent/openhanako 的三栏工作区布局为参考，保留 A3 的学习诊断、资源和复习流程。

```powershell
cd E:\软件杯\a3-front\a3-front
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

当前版本仅为未来桌宠和账号体系保留隔离的窗口、IPC、状态事件与账号提供者边界；不显示桌宠、登录、注册或同步入口。

preload 仅暴露固定桥接方法：`request`、`startStream`、`cancelStream`、`onStreamEvent`、`onBackendExit`、`modelConfigTest` 和 `modelConfigSave`。主进程为普通 HTTP、SSE 与模型配置执行来源校验、固定路由、令牌注入、请求体限制和窗口关闭清理。独立 Web 开发仍可通过 Vite 代理访问 `http://127.0.0.1:8000`；Electron 不依赖固定端口。
