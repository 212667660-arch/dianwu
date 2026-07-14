# S-007 Electron 后端启动与数据目录架构

## 1. 目标

让 Windows 用户双击桌面应用即可启动 Electron 和 FastAPI 后端，无需安装 Python、配置命令行或手动选择端口；同时保证本地 API 不被其他网页随意调用，用户数据在升级和重装后仍可管理。

## 2. 推荐总体结构

Electron main process 负责：

- 启动和停止后端进程。
- 生成本次启动的本地认证令牌。
- 管理端口、健康检查、崩溃重启和日志路径。
- 使用 safeStorage 保存加密后的模型配置。
- 通过 preload 暴露有限 IPC API 给 renderer。

Electron renderer 负责：

- 展示诊断、画像、资源和历史记录。
- 通过 preload API 请求 main process，不直接访问 localhost。
- 渲染安全 Markdown，不接触 API Key、本地认证令牌和文件系统。

FastAPI backend 负责：

- Agent 编排、模型调用、协议校验、数据库和 SSE 事件。
- 只绑定 127.0.0.1，不监听局域网地址。
- 校验 Electron main process 注入的本地认证令牌。
- 使用应用数据目录，不写程序安装目录。

## 3. 开发与打包模式

### 开发模式

- Electron main 启动 backend 虚拟环境中的 Python。
- 工作目录明确设置为 backend。
- 前端开发服务器可以直连后端，但只允许配置中的开发来源。
- 支持后端单独运行和 pytest。

### 打包模式

- 使用 PyInstaller onedir 打包后端，优先于 onefile。
- onedir 启动更快、资源路径更清晰，也更容易排查缺失依赖。
- Electron 安装包把后端目录放入 resources/backend，不作为可写目录。
- main process 使用 process.resourcesPath 定位后端可执行文件。
- 启动子进程时设置 windowsHide=true，不弹出控制台窗口。

## 4. 数据目录

Electron 通过 app.getPath('userData') 得到用户数据根目录，并传给后端环境变量 A3_DATA_DIR。

建议结构：

A3 userData/
- database/app.db
- logs/backend.log
- logs/electron.log
- cache/
- exports/
- config/settings.enc
- migrations/

规则：

- 数据库、日志和配置不得写入 resources、安装目录或源码目录。
- 后端启动时创建目录并检查可写性。
- 导出文件由用户主动选择位置，临时文件先写 cache 后原子移动。
- 卸载程序默认不删除 userData；应用内提供“清除本地数据”。
- 数据库迁移前创建可恢复备份，并限制备份数量。

## 5. 端口与启动握手

推荐流程：

1. main process 生成 256 位随机 local_token。
2. main process 查找一个空闲高位端口，并保留最多三次重试能力。
3. 通过环境变量传入 A3_HOST=127.0.0.1、A3_PORT、A3_DATA_DIR 和短期启动标识。
4. local_token 不放命令行；通过子进程 stdin 在启动时发送一次，后端只保存在内存。
5. 后端完成数据库初始化和路由加载后，在 stdout 输出单行 A3_BACKEND_READY，包含 port 和 pid，不包含密钥。
6. main process 收到握手后请求 /health/ready，并附加本地认证头。
7. 验证成功后才创建或显示主窗口。
8. 超过 20 秒未就绪则终止进程，记录错误并允许用户重试。

若端口被占用，后端应以明确退出码结束，main process 选择新端口重试，最多三次。

## 6. 本地 API 认证

- 除 /health/live 外，所有接口要求 X-A3-Desktop-Token。
- token 每次应用启动重新生成，不写入磁盘。
- renderer 不持有 token，由 main process 代理请求。
- 后端只接受 Host 为 127.0.0.1 或 localhost 的请求。
- 生产模式默认不启用宽泛 CORS；renderer 通过 IPC 访问 main process。
- 开发模式可以配置明确的前端来源，不能同时使用 allow_origins=* 和凭据。

## 7. Renderer 到后端的通信

推荐使用 preload + contextBridge：

- renderer 调用 window.learningApi.chat、stream、history、cancel。
- preload 只暴露固定方法，不暴露 ipcRenderer 全对象。
- main process 验证参数后请求本地 FastAPI。
- 普通请求通过 IPC invoke 返回。
- 流式请求由 main process 消费 SSE，再用带 generation_id 的 IPC 事件转发给指定窗口。
- 窗口关闭或用户取消时，main process 调用后端取消接口并停止转发。

这样可以隐藏端口和 token，减少 CORS 与恶意网页访问面。

## 8. 模型配置与密钥

- renderer 只负责输入密钥，不保存和显示完整密钥。
- main process 使用 Electron safeStorage 加密后保存到 settings.enc。
- 启动后端时，main process 解密配置，通过 stdin 或本地认证配置接口传入内存。
- 密钥不出现在命令行参数、URL、日志和崩溃报告中。
- 更新密钥后由 main process 通知后端重建 ModelGateway，不必重启整个应用。
- 用户可清除密钥，后端 readiness 显示模型未配置，但应用仍可查看历史资源。

## 9. 进程生命周期

- 应用启动只允许一个后端实例，使用 Electron single instance lock。
- 主窗口创建前确认后端 ready。
- before-quit 先请求后端优雅关闭，等待最多 5 秒后再强制终止。
- 后端收到 SIGTERM 或 Windows 终止信号时停止接收新任务、取消生成并关闭数据库连接。
- main process 监控 exit 事件；非主动退出时记录代码并最多自动重启一次。
- 自动重启后重新生成 token，并恢复到最后稳定数据库状态。
- 连续崩溃不无限重启，显示诊断页面和日志目录入口。

## 10. 日志与诊断

- Electron 和后端分别记录滚动日志，单文件建议不超过 5 MB，保留 3 到 5 份。
- 日志包含版本、启动阶段、端口、退出码和错误代码，不包含密钥与完整对话。
- 提供“导出诊断信息”，只打包脱敏日志、版本和健康状态。
- 后端 stdout 只用于握手和必要运行信息，生产模式不输出模型正文。

## 11. 数据库迁移与升级

- 引入 Alembic 或等价迁移工具，不依赖 create_all 处理版本升级。
- 启动时先读取 schema_version，再执行向前迁移。
- 迁移前复制 app.db 为带版本和日期的备份。
- 迁移失败时不启动主业务，提示恢复备份或导出诊断信息。
- 新版本程序必须能读取旧画像和资源的 protocol_version。

## 12. 打包清单

后端：

- 明确 Python 最低版本并固定直接依赖。
- 使用相对包导入，支持 python -m backend.main 或打包入口。
- PyInstaller spec 包含证书、必要动态库和迁移文件。
- 不把开发虚拟环境 competition 直接作为发布内容。

Electron：

- resources/backend 包含后端 onedir 产物。
- preload 使用 contextIsolation，renderer 关闭 nodeIntegration。
- 安装包签名条件允许时启用代码签名。
- 安装和升级后验证 userData、后端启动和数据库迁移。

## 13. 故障场景

- 后端文件缺失：显示安装损坏，不创建空白主窗口。
- 端口连续冲突：提示重试并导出日志。
- 数据目录不可写：提示用户选择或修复权限。
- 密钥缺失：允许进入应用查看历史，但禁用生成按钮并显示配置入口。
- 模型不可用：保留本地功能和历史，允许重试。
- 数据库迁移失败：停止业务启动，保护原数据库和备份。
- renderer 崩溃：后端任务按 generation_id 取消或继续由 main 决策，不能失控。

## 14. Terra 实现清单

- 后端增加 A3_DATA_DIR、A3_HOST、A3_PORT 和本地 token 配置。
- 数据库路径改为 userData/database/app.db。
- 新建桌面认证中间件和 readiness 接口。
- 增加可打包的后端启动入口与就绪握手。
- 建立 PyInstaller spec 和打包验证脚本。
- 前端侧实现 main/preload 的后端进程管理和 IPC 代理。
- 增加启动超时、端口重试、退出和崩溃恢复测试。
- 引入数据库迁移并验证旧版本升级。

## 15. 验收标准

- 全新 Windows 用户无需 Python 即可启动应用。
- 后端只监听 127.0.0.1，未带 token 的请求不能访问业务接口。
- renderer 不持有 API Key、本地 token 和 Node.js 权限。
- 数据库与配置位于 userData，升级程序不会覆盖用户数据。
- 后端异常退出有受限重启和清晰诊断，不出现无限循环。
- 关闭应用后没有残留后端进程。
- 打包版本可以完成诊断、画像、资源流式生成、历史读取和取消任务。
