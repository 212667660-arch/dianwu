# A3 基于大模型的个性化资源生成与学习多智能体系统

## 项目简介

本项目是一个面向学习场景的后端原型系统。系统通过“画像 Agent”和“资源生成 Agent”协作，先用多轮对话了解学习者，再生成结构化学习画像、学习笔记、分层练习题和解析。模型输出采用可读的纯文本协议，便于调试、校验和前端渲染。

当前应用已完成核心 P0 能力：多轮诊断、画像生成、资源生成、协议校验、错误映射、SSE 流式输出、取消生成、会话历史、本地知识库、桌面端多模型配置与自动故障转移。

学习资源生成后，系统会把练习题结构化保存并分配题目 ID。学生提交答案后，后端会更新知识点掌握度、错题记录和复习时间；后续资源生成会使用这些真实学习状态调整内容和难度。

后端还会给出可解释的下一步学习动作：到期任务优先复习，其余按掌握度进入基础纠错、渐进练习、综合巩固或挑战迁移。生成资源会记录质量分和问题码，未达到最低质量门槛时自动请求模型修复一次。

## 技术栈

- Python 3.9+
- FastAPI + Uvicorn
- SQLAlchemy + SQLite
- Pydantic Settings
- 双网关模型层：OpenAI 兼容接口与 Anthropic Messages API
- pytest
- Electron + Vue 3 + Pinia
- PyMuPDF、python-docx、python-pptx、openpyxl
- SQLite FTS5 + 可选 NumPy 本地语义索引

## 目录结构

| 目录 | 作用 |
| --- | --- |
| `backend/routers/` | HTTP、SSE 和会话管理路由 |
| `backend/services/` | 编排器、模型网关、Agent 与数据库仓储 |
| `backend/protocols/` | 诊断、画像、资源协议模型、解析和序列化 |
| `backend/models/` | API 请求与响应模型 |
| `backend/evaluation/` | 固定样例和效果评分工具 |
| `backend/knowledge/` | 本地对象解析、切片、FTS、可选 OCR/语义包与引用上下文 |
| `backend/tests/` | 离线单元测试与接口测试 |
| `a3-front/a3-front/` | Vue/Electron 桌面端、暖色三栏工作台与知识库界面 |
| `codex/architecture/` | 架构设计与复审材料 |

## 本地启动

### 1. 安装依赖

在项目根目录执行：

```powershell
cd E:\软件杯
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### 2. 配置模型服务

复制 `backend/.env.example` 为 `backend/.env`，选择一个网关：

```dotenv
# OpenAI 兼容网关：适用于 OpenAI、DeepSeek 和兼容 Chat Completions 的自定义服务
MODEL_PROVIDER=openai
MODEL_API_KEY=替换为实际密钥
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-pro

# Anthropic Messages 网关：适用于 Anthropic 格式 API
# MODEL_PROVIDER=anthropic
# MODEL_API_KEY=替换为实际密钥
# MODEL_BASE_URL=https://api.deepseek.com/anthropic
# MODEL_NAME=deepseek-v4-pro
# ANTHROPIC_VERSION=2023-06-01
```

`MODEL_BASE_URL` 和 `MODEL_NAME` 均可按用户所使用的平台自定义。`MODEL_PROVIDER=openai` 需要 Chat Completions 兼容接口；`MODEL_PROVIDER=anthropic` 使用 `/v1/messages` 和 Anthropic SSE 事件格式。

不要把真实密钥写入代码、提交到版本库或发送到前端。

开发模式默认使用 `APP_ENV=development`。配置 `DESKTOP_TOKEN` 后，所有 `/api/*` 接口和 `/health/ready` 都必须携带 `X-A3-Desktop-Token`；生产模式始终要求该令牌，缺失时会拒绝业务请求。Electron 正式版应由主进程每次启动生成短期令牌，并通过受保护通道传给后端，renderer 不持有令牌。

生产模式不允许后端通过 `PUT /api/settings/model` 将 API Key 明文写入 `.env`；请使用 Electron `safeStorage` 或 Windows Credential Manager 保存密钥，再在启动时注入模型配置。生产模式仅接受 HTTPS 公网模型网关，默认拒绝 localhost、私网、链路本地地址和非标准端口。开发环境需要测试本地网关时，显式设置 `ALLOW_LOCAL_MODEL_GATEWAY=true`。

### 桌面端多配置与思考强度

正式 Electron 桌面端使用版本 2 加密保险库管理多套模型配置。模型设置页可新增、复制、测试、启停和删除非默认配置，并指定全局默认配置、备用顺序和是否自动切换；API Key 只进入主进程与后端内存，不回填到表单，也不进入 renderer、URL、普通日志或学习数据库。旧版单配置密文会在启动时仅于内存迁移，首次明确保存后才写入新版保险库。

学习空间可以继承全局策略，也可以单独选择配置、模型和 `auto/off/low/medium/high/xhigh` 思考强度。实际档位会按模型声明的能力安全降档。普通请求只对超时、连接错误、429、502、503、504 等可重试故障使用备用配置；401、403、404、参数错误和本地校验错误直接返回，不用备用配置掩盖错误配置。

每个请求最多尝试 3 次、最多涉及 2 套配置。429 会读取并限制上游 `Retry-After`：若一次等待仍在总截止时间内，则可等待并重试同一配置；否则立即转向备用配置或失败。每套配置独立熔断，429 的冷却时间优先采用上游值。流式请求在首个有效文本前可以自动切换；一旦已输出文本，只保留已有内容并发送 `interrupted`，由用户明确选择“使用备用配置继续”，不会把两个模型的文本静默拼接。

配置 `DESKTOP_TOKEN` 或使用生产模式时，后端会对高成本接口执行滑动窗口限流：`API_RATE_LIMIT_PER_MINUTE=10` 控制对话、流式对话、画像与资源生成，`WEB_SEARCH_RATE_LIMIT_PER_MINUTE=30` 控制公开网络检索。达到上限时返回 `429 REQUEST_RATE_LIMITED` 和 `Retry-After` 响应头。诊断上下文默认保留首条学习目标和最近消息，边界可通过 `DIAGNOSIS_HISTORY_MESSAGE_LIMIT=12` 与 `DIAGNOSIS_HISTORY_MAX_CHARACTERS=48000` 调整。

### 3. 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

启动后访问：

- 健康检查：`http://127.0.0.1:8000/health/live`
- 就绪检查：`http://127.0.0.1:8000/health/ready`
- Swagger：`http://127.0.0.1:8000/docs`
- 功能测试台：`http://127.0.0.1:8000/test`

### 3.1 启动 Electron 桌面端

桌面端会自行启动打包后的本地后端；开发与解压运行命令如下：

```powershell
cd E:\软件杯\a3-front\a3-front
npm install
npm run desktop:dev

# 生成解压版后直接运行
npm run desktop:pack
.\release\win-unpacked\智学协作台.exe
```

`desktop:dev` 和 `desktop:pack` 需要 `a3-front/a3-front/desktop-backend/api.exe` 已存在。模型配置、知识库、桌宠设置与学习数据均写入 Electron userData，不写入安装目录。

### 4. 运行测试

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend
.\.venv\Scripts\python.exe -m pytest -q backend
```

当前离线测试覆盖诊断状态机、协议解析、错误响应、会话接口、流式事件、取消、七格式知识解析、恶意文件隔离、检索性能和评测工具。真实模型联调需要有效的 `MODEL_API_KEY`，不会在离线测试中自动发起。

也可以直接双击运行 `backend\quick_test.bat`，自动完成语法检查和全部后端测试；双击 `backend\quick_package_test.bat` 可额外重建 `api.exe` 并执行启动自检。两个入口会优先使用项目内的 `backend\competition` Python 环境。

## 核心流程

1. 客户端向 `POST /api/chat` 或 `POST /api/chat/stream` 发送学习目标和回答。
2. 画像 Agent 根据对话输出诊断决策；必要时继续追问，最多五轮。
3. 画像 Agent 输出并校验 `learner-profile/v1`。
4. 资源生成 Agent 根据画像输出 `learning-resource/v1`。
5. 后端校验、规范化并持久化画像或资源。
6. 客户端通过会话接口读取历史、资源和当前画像。

## 常见问题

- `503 model_not_configured`：检查 `backend/.env` 的 `MODEL_PROVIDER`、`MODEL_API_KEY`、`MODEL_BASE_URL` 和 `MODEL_NAME`。
- `422`：检查消息是否为空、是否超过 8000 字，或 `session_id` 是否只包含字母、数字、下划线和连字符。
- `502`：模型返回不符合协议，系统会尝试一次格式修复；仍失败时查看错误代码。
- SSE 没有实时分片：确认客户端使用 `/api/chat/stream`，并关闭代理层缓冲。
- 数据库位置：开发模式默认是 `backend/app.db`；桌面版保存在 Electron userData 的 `backend/app.db`，知识对象保存在同一 userData 的 `knowledge/objects`。

## 本地知识库

桌面端“本地知识库”支持 PDF、DOCX、PPTX、XLSX、TXT、Markdown 和 CSV。文件选择和拖放都由 Electron 主进程完成：主进程校验普通文件、扩展名、签名、单文件 100 MiB、最多 50 个文件和批次 500 MiB，然后以 SHA-256 去重复制到 `userData/knowledge/objects`。renderer 和普通 HTTP API 不接收用户原路径。

- 左侧集合用于整理课程资料，中间显示文档与导入进度，右侧显示安全元数据、OCR 提示、重建、删除和只读预览。
- 学习空间可绑定多个集合。`allow_model_context` 只向当前模型服务发送最多 8 个相关片段；`local_search_only` 只做本机检索，不把资料正文发送给模型。
- 模型收到的片段被标记为不可信资料，不能覆盖系统指令；模型引用必须匹配本次检索产生的 `[资料N]`，历史和导出保存同一份受控引用快照。
- 图片型 PDF 在没有本地 OCR 包时进入 `OCR_REQUIRED`，不影响其他文档和主学习服务。语义包缺失或损坏时自动退回关键词检索。
- A3 不会自动下载或随安装包分发 OCR/语义模型权重。首次启动会创建 `userData/knowledge/packs/README.txt`；只应安装具有明确许可、兼容范围和 SHA-256 的本地包。
- 删除文档会清理数据库、FTS/语义索引和无引用对象；应用异常退出时进行中的任务标记为 `INTERRUPTED`，可由用户重试。

## 桌面学习伙伴

Electron 启动时会同时创建独立的透明、无边框、置顶桌宠窗口。默认原创角色“墨团”支持空闲、左右移动、挥手、跳跃、失败、等待、执行和检查动画；学习生成、协议校验、完成与失败会自动切换任务状态。单击挥手、双击跳跃，按住拖动可移动到其他显示器；位置、显示开关、缩放和速度会保存在 `userData/pet-settings.json`。隐藏时暂停动画，空闲 60 秒后降低刷新频率。

书桌右栏的“桌面学习伙伴”卡片可显示/隐藏桌宠，并选择 50%–150% 缩放和 0.5×–2× 动画速度。Web 浏览器模式只显示说明，不尝试调用桌面能力。

替换角色素材时，在 `%APPDATA%\A3LearningAgent\pets\current\` 放置：

- `pet.json`
- `spritesheet.webp`

重启应用后会优先读取该目录；清单、精灵图缺失或规格非法时自动回退内置“墨团”。兼容规格固定为单格 192×208、8 列×9 行、总尺寸 1536×1872，未使用格必须完全透明。动画行依次为 `idle`、`running-right`、`running-left`、`waving`、`jumping`、`failed`、`waiting`、`running`、`review`。内置范例位于 `a3-front/a3-front/electron/pets/motuan/`，可用 `tools/pet/generate_motuan.py` 重新生成。

atlas 校验工具来自 Apache-2.0 的 `openai/skills` hatch-pet，原 LICENSE 与来源说明保存在 `tools/pet/third_party/hatch-pet/`。项目没有复用 OpenAI/Codex 名称、Logo 或角色素材。

## 资源缓存

当同一会话、同一画像版本再次提交完全相同的资源请求时，后端会直接复用已校验并持久化的资源，避免重复调用模型。默认有效期为 24 小时，可在 `backend/.env` 设置：

`RESOURCE_CACHE_TTL_SECONDS=86400`

设置为 `0` 可以关闭缓存。普通 `POST /api/chat` 响应中的 `cached` 字段标识是否命中缓存；SSE 会额外发送 `cache` 事件。重新诊断会产生新的画像版本，不会误用旧资源。

## 打包为 api.exe

后端可独立打包为 Windows 可执行程序：

```powershell
.\backend\build_api.ps1 -Python .\backend\competition\Scripts\python.exe
.\backend\verify_api_package.ps1 -Python .\backend\competition\Scripts\python.exe
```

产物位于 `dist/api/api.exe`。验证脚本会先以 `api.exe --knowledge-worker` 解析七种最小样本，再启动 HTTP 服务检查 `/health/live` 和 `/test`。运行后默认监听 `127.0.0.1:8000`；可用 `A3_PORT` 修改端口。打包版会将数据库和模型配置保存到 `%LOCALAPPDATA%\A3LearningAgent`，避免写入安装目录；也可通过 `A3_DATA_DIR` 指定自定义数据目录。

## 离线评测

固定样例、基线和可运行的评测命令位于 `backend/evaluation/`。评测命令读取 `case_id -> 模型输出文本` 的 JSON 文件，可用于保存真实模型结果并进行回归比较：

```powershell
.\backend\competition\Scripts\python.exe -m backend.evaluation.cli --outputs backend\evaluation\sample_outputs.json --baseline backend\evaluation\baseline.json --report backend\evaluation\latest-report.json
```

当样例缺失，或平均分/协议通过率低于基线时，命令会返回非零退出码。

## 真实模型评测

当本机模型配置有效时，可显式运行以下命令，对当前 `MODEL_PROVIDER` 和 `MODEL_NAME` 执行完整固定样例评测。它会保存模型原始协议输出、逐项耗时、失败代码和评分报告；该命令会实际调用模型服务。

```powershell
.\backend\competition\Scripts\python.exe -m backend.evaluation.live --report backend\evaluation\live-evaluation-report.json --outputs backend\evaluation\live-evaluation-outputs.json
```

模型未配置时命令会直接拒绝执行，不会尝试网络请求。每次运行还会向 `live-evaluation-history/` 写入带 UTC 时间戳的报告，自动与上一次报告比较；平均分下降超过 `--max-drop`（默认 3 分）、协议通过率下降或调用失败时，命令返回非零退出码。报告中的 `failure_summary` 会列出失败样例及原因。

## 质量约束

- 画像 Agent 会保留用户明确表达的当前水平、学科、学习风格和目标；当前水平不会被模型擅自升降级。
- 资源协议要求同时含有非空学习笔记和分层练习，避免只给题目或空笔记的低质量输出。
- 固定离线评测集现覆盖 7 个画像/资源样例，可用于提示词或模型切换后的回归检查。

## 运行可靠性

- 桌面模型设置页通过固定 IPC 测试候选配置并热应用新版快照，不重启后端；Web 开发模式仍可调用 `POST /api/settings/model/test`，该兼容入口已经转接同一运行时测试器且不会保存候选配置。
- 多配置运行时按请求固定一份原子快照；配置保存、后端热应用和失败回滚串行执行，旧快照会等活动请求结束后再释放连接。
- 上游限流、超时和临时不可用只在总尝试预算内重试/切换；认证、权限和模型不存在会标记配置需要处理，并禁止自动备用。
- 会话和资源导出路由会校验路径参数，避免非法会话 ID 或资源 ID 进入业务层。
- 应用停止时会关闭模型客户端并清理内存中的生成取消标记、会话锁，适合桌面端反复启动和退出。
- 生产模式下，除 `/health/live` 外的业务请求都由本地桌面令牌保护；令牌错误、缺失或非本机连接会返回 `DESKTOP_AUTH_REQUIRED`。
- 取消流式任务必须同时提交生成 ID 与原始会话 ID；限流状态会在应用停止时清理，不会跨桌面端启动累积。

## 在线检索

后端支持查询公开网络资料，并将来源摘要作为资源生成的受限参考上下文。默认使用固定的搜狗、DuckDuckGo 与 Bing RSS 回退链路，不需要额外密钥，也不接受任意搜索服务 URL。

- `POST /api/web/search`：直接返回标题、链接和摘要，网络不可用时返回 `503 WEB_SEARCH_UNAVAILABLE`。
- `POST /api/resource`：默认启用在线检索，响应内的 `sources` 返回本次引用来源；检索失败时会自动以空来源继续生成，不影响已有学习流程。
- 经由会话生成的资源会持久化本次检索的标题、链接和摘要；缓存命中、会话历史、普通对话响应和 SSE 的 `sources` 事件均返回同一份来源快照。导出 Markdown/TXT 时会在资源正文后附上“参考来源”部分。
- 环境变量：`WEB_SEARCH_ENABLED`、`WEB_SEARCH_TIMEOUT_SECONDS`、`WEB_SEARCH_MAX_RESULTS`、`WEB_SEARCH_PROVIDERS=sogou,duckduckgo,bing`。

已在开发机完成真实联机验证：中文查询“一次函数 数学 教学资料”返回 5 条相关公开来源。搜狗作为中文检索首选；DuckDuckGo 与 Bing 保留回退，且会过滤与完整查询无关的低质量结果。
## 后续工作

- 按新增供应商和模型的官方能力继续扩充推理参数适配器与真实流式回归。
- 继续完善桌宠角色导入 UI、素材安全检查、语音鼓励、完整视觉 QA 与全面许可证审计；账号体系继续只保留扩展边界。
- 根据真实模型输出扩充评测集和评分基线。
- 按 `codex/AI模型任务队列.md` 管理后续模型任务。
