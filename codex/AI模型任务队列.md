# A3 模型任务队列

> 项目：基于大模型的个性化资源生成与学习多智能体系统开发
> 队列位置：E:\软件杯\codex\AI模型任务队列.md
> 当前模型批次：Sol（S-019/T-036 第二阶段角色导入与独立声音控制进行中）
> 最后审视日期：2026-07-16

## 一、使用规则

1. 本文件是软件杯项目任务状态的单一真实来源，新对话开始时先读取本文件。
2. 新任务先登记到“收件箱”，再标注目标模型、优先级、依赖和验收结果。
3. 当前模型只批量执行属于该模型且状态为“就绪”的任务。
4. 不属于当前模型的任务先保留，不要求立即切换；当前批次做完或被依赖阻塞时，再提醒用户切换。
5. 模型切换由用户手动完成。切换后更新“当前模型批次”，并继续该模型优先级最高的就绪任务。
6. 完成任务后必须填写修改文件、验证命令和结果，再把状态改为“完成”。
7. 若任务依赖前置设计，状态设为“阻塞”，不得绕过依赖直接实现。
8. 用户自 2026-07-15 起明确不考虑模型成本，后续未完成任务默认登记到 Sol 批次并由 Sol 设计、实现、调试、验证和审查。

## 二、状态定义

| 状态 | 含义 |
| --- | --- |
| 收件箱 | 已记录，尚未完成模型和依赖判断 |
| 就绪 | 可以由目标模型直接开始 |
| 进行中 | 当前正在执行，只允许每个模型批次有一个主任务 |
| 阻塞 | 等待其他任务、用户信息或外部条件 |
| 待验证 | 实现完成，等待测试或人工验收 |
| 完成 | 已实现并记录验证结果 |
| 保留 | 经审视确认暂时无需修改 |

## 三、现有实现审视

### 建议保留

- FastAPI 按 routers、services、models 分层，结构适合继续扩展。
- config.py 使用环境变量加载 OpenAI 兼容模型配置，真实 .env 已被 .gitignore 忽略。
- 画像 Agent 与资源 Agent 已分离，并通过纯文本标记传递结果，符合赛题方向。
- SQLite 会话、消息、画像和资源模型已经具备原型所需的持久化基础。
- 普通接口、画像接口、资源接口和 SSE 接口均可导入，根健康检查返回 200。

### 必须改进

- 首条消息会立即生成画像，不符合“通过简短对话诊断”的多轮流程，需要明确状态机。
- 当前 SSE 先等待完整结果，再切成小块发送，不是真正的大模型流式输出。
- llm_service 把错误转换成普通文本并返回 200，业务层只能靠关键词识别错误。
- 画像和资源输出依赖字符串字段解析，缺少正式协议版本、字段校验和修复策略。
- requirements.txt 缺少代码直接依赖的 SQLAlchemy，环境无法可靠复现。
- 绝对式模块导入依赖从 backend 目录启动，不利于 Electron 打包和模块化运行。
- async 路由中执行同步数据库操作，未来并发时可能阻塞事件循环。
- init_db 在导入和请求中重复调用，应该迁移到 FastAPI lifespan。
- CORS、请求字段、session_id 和资源元数据缺少生产级约束。
- 当前没有自动化测试，也没有固定的模型效果评测样例。

## 四、Sol 队列

| ID | 优先级 | 状态 | 任务 | 依赖 | 验收产物 |
| --- | --- | --- | --- | --- | --- |
| S-001 | P0 | 完成 | 设计多轮诊断状态机与 Agent 边界 | 无 | 状态图、状态转换、异常分支和接口契约 |
| S-002 | P0 | 完成 | 设计版本化纯文本协议及校验策略 | 无 | 画像协议、资源协议、解析与修复规则 |
| S-003 | P0 | 完成 | 设计真实流式编排与取消机制 | S-001、S-002 | SSE 事件协议、断开处理和持久化时机 |
| S-004 | P0 | 完成 | 设计模型错误语义与降级策略 | S-002 | 异常类型、重试边界和 HTTP 映射 |
| S-005 | P1 | 完成 | 建立模型效果评测方案 | S-002 | 固定样例、评分维度和回归门槛 |
| S-006 | P1 | 完成 | 审视提示词注入与隐私边界 | 无 | 风险清单和输入输出防护方案 |
| S-007 | P1 | 完成 | 确定 Electron 后端启动与数据目录架构 | 无 | 进程、端口、配置和数据库路径方案 |
| S-008 | P0 | 完成 | 设计生产本地 API 鉴权与模型配置安全边界 | S-006、S-007 | 统一令牌中间件、密钥存储边界、网关地址校验和 Terra 实现清单 |
| S-009 | P0 | 完成 | 设计并实现学习掌握度、答题反馈与自适应复习闭环 | L-009 | 知识点状态模型、答题评估协议、复习调度、接口契约、迁移策略和回归测试 |
| S-010 | P1 | 完成 | 实现自适应下一步建议与资源质量门槛 | S-009 | 下一步学习决策、题目难度覆盖、重复题检测、质量结果和测试台验收 |
| S-011 | P0 | 完成 | 细化 Electron 主进程 HTTP/SSE IPC 代理与令牌隔离方案 | S-007、S-008、T-028 当前实现 | 普通请求、SSE、取消、错误、窗口生命周期和参数校验的 IPC 契约；确保 renderer 不接触 token |
| S-012 | P0 | 完成 | 诊断并收敛 T-028 Electron 测试模式退出残留 | T-028 当前实现 | 定位完整主应用调用 `process.exit(0)` 后进程树仍存活的根因，给出可回归修复或明确的运行时边界与验收方案 |
| S-013 | P0 | 完成 | 复核前端、Electron 代理与 FastAPI 的接口契约 | 无 | 路径与方法清单、请求/响应/SSE 契约对比、前后端自动化测试结果及明确问题清单 |
| S-014 | P0 | 完成 | 实现安装版安全模型配置闭环 | S-008、S-011、T-028 | 前端模型配置与连通性测试、Electron `safeStorage` 凭据保存、主进程启动注入、受控 IPC 路由及全新安装就绪验收 |
| S-015 | P1 | 完成 | 建立项目 Git 安全基线 | S-014 | 根目录单仓库、敏感/生成文件忽略规则、首个本地 main 基线提交及仓库状态验收 |
| S-016 | P1 | 完成 | 连接 GitHub 私有远程仓库 | S-015 | 本地提交身份、`origin`、`main` 上游分支、远程提交一致性和推送验收 |
| S-017 | P0 | 完成 | 设计稳定优先的多 API 配置、故障转移、模型切换与推理强度架构 | S-014、T-032、用户已确认“手动主配置 + 自动备用切换 + 可关闭自动切换” | Electron 版本 2 加密保险库、后端内存路由器、原子热应用、主备与熔断、普通/流式边界、全局与学习空间覆盖、模型能力和推理强度适配、13 项 TDD 实施计划 |
| S-018 | P0 | 完成 | 设计本地知识库、文件导入、解析、索引与学习流程接入 | 现有 FastAPI/SQLite/Electron、安全边界、用户新增需求 | 支持格式与限额、文件存储和解析隔离、文本切片/检索、引用溯源、会话/资源接入、删除与重建、接口/UI、测试和打包方案 |
| S-019 | P1 | 进行中 | 设计可扩展桌宠、用户形象导入、学习进度感知与语音鼓励 | S-009、S-010、T-030、用户新增需求 | 第一阶段 MVP 已完成；第二阶段采用主进程受控角色目录导入、本地 Web Audio 动作音效、系统 speechSynthesis 语音鼓励，音效与语音独立开关/音量且不联网 |
| T-033 | P0 | 完成 | 实现多 API 配置、高可用切换、模型选择与推理强度控制 | S-017 | 版本 2 加密多配置、原子热应用与回滚、3 次/2 配置预算、Retry-After/熔断、普通与流式故障边界、全局/学习空间模型和思考强度选择、兼容迁移、真实桌面 5/5 连接及完整打包回归 |
| T-035 | P0 | 完成 | 实现本地知识库与安全文件导入 | S-018 | 已完成文件选择/拖放、七格式与限额校验、隔离解析 worker、SQLite 元数据/FTS/可选语义索引、可追溯引用、学习助手绑定与隐私模式、删除/重建、恶意文件/性能/打包测试及 Windows 桌面安装包验收 |
| T-036 | P1 | 进行中 | 实现桌宠形象包、用户上传、进度事件与语音鼓励 | S-019 | 第一阶段可用 MVP 已完成并打包验收；自定义 `userData/pets/current` 角色目录与安全回退已具备，用户上传管理 UI、语音鼓励和全面素材审计保留后续 |

## 五、Terra 队列

| ID | 优先级 | 状态 | 任务 | 依赖 | 验收产物 |
| --- | --- | --- | --- | --- | --- |
| T-001 | P0 | 完成 | 修复依赖清单和包导入方式 | 无 | 可从项目根启动并全新安装依赖 |
| T-002 | P0 | 完成 | 实现多轮诊断状态机 | S-001 | 会话状态、追问、画像生成和重诊断流程 |
| T-003 | P0 | 完成 | 实现纯文本协议解析与校验 | S-002 | 稳定解析、缺字段修复和版本兼容 |
| T-004 | P0 | 完成 | 实现模型异常与 HTTP 错误映射 | S-004 | 非文本错误传播、统一响应和日志 |
| T-005 | P0 | 完成 | 实现真实 SSE 流式输出 | S-003、T-004 | 模型分片直传、完成、错误和取消事件 |
| T-006 | P0 | 完成 | 建立后端测试基础 | 无 | pytest 配置、健康检查和仓储测试 |
| T-007 | P1 | 完成 | 将数据库初始化迁移到 lifespan | 无 | 启动初始化且请求不重复建表 |
| T-008 | P1 | 完成 | 加强请求模型和 session_id 校验 | 无 | 长度、空值、格式和错误响应测试 |
| T-009 | P1 | 完成 | 修复仓储事务与消息序号并发风险 | 无 | 原子提交、回滚和稳定序号策略 |
| T-010 | P1 | 完成 | 收紧 CORS 与环境配置 | 无 | 开发和打包环境配置可切换 |
| T-011 | P1 | 完成 | 接入模型效果回归测试 | S-005、T-006 | 固定输入可重复评分和比较 |
| T-012 | P2 | 完成 | 增加历史记录与会话管理接口 | T-008、T-009 | 查询、删除和重新诊断接口 |
| T-013 | P1 | 完成 | 增加资源结果缓存与缓存命中标识 | T-012 | 同会话、同画像版本、同请求命中 SQLite 持久化缓存；支持 TTL、普通接口与 SSE 缓存标识 |
| T-014 | P1 | 完成 | PyInstaller 打包并验证独立 api.exe | S-007 | build/verify 脚本、onedir api.exe、20 秒健康检查通过、用户数据目录隔离 |
| T-015 | P1 | 完成 | 增加已生成资源导出接口 | T-012 | 可导出 Markdown/TXT，资源归属校验和接口测试 |
| T-016 | P1 | 完成 | 增加离线评测命令与基线比较 | T-011 | 可读入样例输出，生成报告并按基线判定 |
| T-017 | P1 | 完成 | 增加真实模型批量评测与耗时报告 | T-016 | 显式命令调用当前模型，保存输出、评分与失败原因 |
| T-018 | P1 | 完成 | 按真实评测结果收紧提示词与资源质量校验 | T-017 | 用户明确画像字段映射、学习笔记非空校验和回归样例 |
| T-019 | P1 | 完成 | 增加真实评测趋势记录与失败摘要 | T-017 | 带时间戳报告、上次结果比较、失败样例可读摘要 |
| T-020 | P1 | 完成 | 增加候选模型配置连通性检测 | T-010 | 不落盘测试网关、认证和模型名，返回安全延迟结果 |
| T-021 | P2 | 完成 | 收紧会话路径参数并释放运行时资源 | T-012 | 路由层 ID 校验、停机关闭模型客户端和清空内存状态 |
| T-022 | P1 | 完成 | 增加公开网络检索与学习资源参考上下文 | T-018 | 固定搜狗/DuckDuckGo/Bing 回退、来源结果、生成降级、离线与真实联机验证 |
| T-023 | P1 | 完成 | 持久化在线来源快照并贯通缓存、历史和导出 | T-022 | SQLite 来源快照、普通/SSE 响应、缓存一致性、会话历史和导出引用 |
| T-024 | P0 | 完成 | 落地生产本地鉴权、网关安全与流式错误修复 | S-008 | 生产 token 保护、base_url 校验、SSE 403/404 映射、练习协议与运行时清理测试 |
| T-025 | P1 | 完成 | 增加生成任务归属、请求限流与诊断上下文边界 | S-008 | 生成归属校验、按客户端限流、历史窗口与回归测试 |
| T-026 | P1 | 完成 | 完成 A3 前端真实联调与回归测试 | L-010 | 六个页面连接真实后端；诊断、SSE、取消、资源、答题和复习全流程浏览器验收；补充前端自动化回归；生产构建通过 |
| T-027 | P2 | 完成 | 收敛 A3 前端生产产物与体验细节 | T-026 | 处理超过 500 kB 的主包告警，复核加载、错误和窄屏体验，保留实际收益并记录指标 |
| T-028 | P2 | 完成 | 接入 Electron 前端壳并打包验收 | T-026、用户确认桌面端范围、S-011 | 主进程、无令牌预加载 IPC、前端产物加载和安装包验收；以 openhanako 作为交互与视觉参考 |
| T-029 | P1 | 完成 | 统一 FastAPI、Web 与 Electron 的错误响应契约 | S-013 | 404/422 与业务异常统一可解析错误信封，Web/Electron 显示一致且覆盖回归测试 |
| T-030 | P1 | 完成 | 以 openhanako 为参考重做 A3 陪伴式学习工作台界面 | T-029、用户视觉确认 | 三栏工作台、欢迎式对话入口、书桌/便签信息面板、暖色浪漫视觉、账号与桌宠扩展边界；Vitest、Web/桌面构建和浏览器窄屏验收 |
| T-031 | P0 | 完成 | 修复 Electron 沙箱预加载桥接缺失导致桌面后端误判离线 | T-030、体验测试截图 | 沙箱兼容 preload、桌面 IPC 桥接可用、模型设置与健康检查恢复、Electron/前端回归和真实窗口验收 |
| T-032 | P0 | 完成 | 修复桌面模型连接失败、环境密钥污染与首次配置误判 | T-031、模型连接体验截图 | 模型 HTTP 客户端绕过错误系统代理；Electron 不继承终端模型密钥；空 Key 交由主进程安全存储解析；DeepSeek 真实测试、保存、重启与留空复测全部成功 |
| T-034 | P0 | 完成 | 建立当前 API 连接稳定性与延迟基线并修复可复现缺陷 | T-032 | 11 次真实调用全部成功；后端连续 5 次 P50 1329 ms、P95 2108 ms，桌面全链路 3/3 成功；客户端复用、2 次自动重试和 60 秒超时生效；无可复现连接 Bug，不提前实现 S-017 架构范围 |

## 六、Luna 队列

| ID | 优先级 | 状态 | 任务 | 依赖 | 验收产物 |
| --- | --- | --- | --- | --- | --- |
| L-001 | P0 | 完成 | 编写后端启动与环境配置 README | T-001 | 从零启动步骤和常见错误说明 |
| L-002 | P1 | 完成 | 补充 API 请求响应示例 | T-008 | 普通、画像、资源和 SSE 示例 |
| L-003 | P1 | 完成 | 补充 .gitignore 的数据库和日志规则 | 无 | app.db、日志和临时文件不进入版本控制 |
| L-004 | P1 | 完成 | 整理 Agent 协议说明文档 | S-002 | 可读协议示例和字段解释 |
| L-005 | P1 | 完成 | 准备模型效果评测样例文本 | S-005 | 不同学科、水平和学习风格样例 |
| L-006 | P2 | 完成 | 更新开发总结和演示说明 | 核心 P0 完成 | 与实际代码一致的展示材料 |
| L-007 | P1 | 完成 | 编写后端快捷测试程序 | T-025 | 双击或单命令执行语法检查、自动化测试与可选打包自检 |
| L-008 | P1 | 完成 | 提供后端功能测试界面 | L-007 | 浏览器访问 /test，执行健康检查、普通/SSE 对话、取消生成、会话历史和在线检索 |
| L-009 | P1 | 完成 | 对比学习软件并形成后端优化方案 | L-008 | 竞品能力矩阵、现有差距、Sol 实施任务和验收指标 |
| L-010 | P1 | 完成 | 记录 A3 前端已完成部分与续作清单 | 无 | `codex/前端续作清单.md`：实际代码盘点、验证边界、剩余任务与下次执行规则 |

## 七、收件箱

| ID | 建议模型 | 状态 | 任务 | 备注 |
| --- | --- | --- | --- | --- |
| INBOX-001 | Sol | 保留 | 决定是否保留 competition 虚拟环境目录 | 保留：约 74.26 MB，供测试、评测和 PyInstaller 打包复现；已被 `.gitignore` 排除，不进入发布包 |
| INBOX-002 | Terra | 完成 | 验证用户自定义 API 的实际模型能力 | 已验证 DeepSeek OpenAI 兼容网关的普通调用、真实 SSE 分片、诊断自动修复、画像和资源协议；Anthropic 网关具备离线测试覆盖，待用户配置对应有效密钥时可直接使用。 |
| INBOX-003 | Luna | 完成 | 编写后端快捷测试程序 | 已分流至 L-007：提供适合本地验收的一键测试入口。 |
| INBOX-004 | Luna | 完成 | 提供后端功能测试界面 | 已分流至 L-008：提供浏览器内的后端验收界面。 |
| INBOX-005 | Luna/Sol | 完成 | 对比学习软件并优化后端学习闭环 | L-009 完成竞品与差距分析；S-009 已完成掌握度、答题反馈、复习调度和自适应生成上下文。 |
| INBOX-006 | Sol | 完成 | 继续优化后端学习效果 | S-010 已完成下一步学习决策、资源质量评分、低质量自动修复和测试台验收。 |
| INBOX-007 | Luna/Terra | 完成 | 盘点 A3 前端并准备续作任务 | 已分流至 L-010；后续实施为 T-026、T-027，Electron 接入待用户确认后解锁 T-028。 |
| INBOX-008 | Sol | 完成 | 检查前后端接口是否存在问题 | S-013 已完成：当前学习主流程接口匹配且回归通过；发现安装版模型配置闭环缺失与错误信封不一致，分别登记为 S-014、T-029。 |

## 八、当前执行顺序

Sol 已完成 T-035 的 12 个 TDD 任务：知识库采用 Electron userData 本地对象存储与 SHA-256 去重、隔离 parser worker、SQLite FTS5 必选索引、可选本地 OCR/语义包、学习空间集合绑定、两种隐私模式、可追溯引用和不可信资料防护。暖色三栏界面延续 openhanako 式陪伴工作台，并保留账号与桌宠扩展边界。

Task 12 发布收尾已通过：完整后端测试在启用打包 `api.exe` worker 后为 216 passed；前端为 Electron Node 82 passed、Vitest 56 passed；`build:desktop` 通过，主包 343.92 kB、知识库页面 12.97 kB，无 500 kB 告警。10 MiB PDF 导入 2.491 秒，10,000 chunks/100 次 FTS 查询 P95 77.847 ms，真实 worker 取消 0.002 秒，导入期间 100 次 `/health/live` P95 1.394 ms。打包后端七格式 worker 7 passed，`/health/live` 与 `/test` 启动检查通过；`app.asar` 与 renderer 密钥/令牌/路径扫描无命中，计划占位符扫描和 `git diff --check` 通过。

发布产物：`a3-front/a3-front/release/win-unpacked/智学协作台.exe`，解压目录 470.85 MiB；`a3-front/a3-front/release/智学协作台 Setup 0.0.0.exe`，安装包 136.92 MiB；`dist/api/api.exe` 所在后端包 161.66 MiB。默认 Electron 图标与未配置代码签名仍是已知非阻塞发行限制。生成目录均被 Git 忽略，不进入提交。

用户已要求继续下一项，Sol 现执行 T-033 多 API 高可用实现。既有 S-017 设计与 13 项 TDD 计划保持有效，当前分支为 `codex/multi-api-stability`；启动基线为后端 209 passed、7 skipped，Electron Node 82 passed、Vitest 56 passed。S-019 仍为就绪、T-036 仍因 S-019 阻塞，账号体系继续只保留扩展边界。INBOX-002 当前使用 DeepSeek OpenAI 兼容配置与 deepseek-v4-pro；旧混元和 OpenAI Terra 联调记录仅供历史追溯。

T-033 Task 1 已完成：新增严格的多配置、模型能力和运行快照契约，以及 `auto/off/low/medium/high/xhigh` 推理档位与 OpenAI/Anthropic 白名单适配器。重复配置/模型 ID、默认模型或默认配置缺失、控制字符、任意额外字段和缺少 `auto` 档位均被拒绝；全新安装空快照保持合法。聚焦 pytest 12 passed。

T-033 Task 2 已完成：新增可重试/终止错误分类、默认 3 次/2 配置总尝试预算，以及 30/60/120/240/300 秒渐进冷却的 closed/open/half-open 熔断器；half-open 探测单飞，终止错误不污染普通熔断计数。补齐八个稳定运行时错误码，聚焦 pytest 30 passed。

T-033 Task 3 已完成：`ModelGateway` 支持显式模型、白名单推理参数与最大输出 token；OpenAI `reasoning_effort` 和 Anthropic `thinking` 均与 `temperature` 正确互斥，Anthropic 保证输出 token 大于思考预算。OpenAI SDK 隐式重试设为 0，网关内部重复重试移除，连接池仍按 Key/base URL/超时签名复用；聚焦 pytest 15 passed。

T-033 Task 4 已完成：新增原子 `ModelRuntimeRouter`、脚本化假网关、配置候选选择、模型/推理档位实际映射、普通请求终止/可重试边界和备用切换。候选快照构建失败不影响旧运行时，活动请求持有快照租约，旧客户端仅在租约归零后关闭；画像、资源、独立 profile/resource 接口和协议修复共用运行时选择闭包，不再各自持有全局模型客户端。相关回归 36 passed。

T-033 Task 5 已完成：流式请求在首个有效 delta 前允许切换备用，并只发送实际配置的一个 `meta`；一旦已有输出，任何可重试断流都保留已有文本、禁止静默拼接备用内容，发送 `MODEL_STREAM_INTERRUPTED` 与 `done.status=interrupted`。取消仍直接传播，SSE 元数据包含实际配置、模型、请求/生效推理档位和 failover 标志；相关回归 12 passed。

T-033 Task 6 已完成：新增隐藏的 `/internal/model-runtime/bootstrap|test|snapshot|status` 控制面，强制 loopback、非空桌面令牌、严格字段和 128 KiB 请求限制；renderer IPC 明确拒绝 `/internal/*`。`/health/ready` 改由运行时快照决定，开发无桌面令牌时兼容旧单配置内存 bootstrap，production 只等待 Electron 注入；后端聚焦 19 passed，Electron 契约 17 passed。

T-033 Task 7 已完成：新增 `session_model_preferences` 一对一持久化、默认继承、严格 profile/model/reasoning/failover 枚举接口和会话删除级联。偏好只保存脱敏 ID，不因配置暂时不存在而丢失；普通与流式编排在每次请求开始读取一次学习空间偏好并映射为同一 `RuntimeSelection`。相关回归 21 passed。

T-033 Task 8 已完成：新增 Electron `safeStorage` 版本 2 多配置保险库，支持全新安装空快照、版本 1 单配置内存迁移、最多 16 配置/每配置 64 模型、严格能力白名单、密文原子保存和字节快照恢复。迁移不主动重写旧文件，首次显式保存才生成 `model-profiles.enc`；新旧保险库 Node 8 passed，明文 Key 扫描断言通过。

T-033 Task 9 已完成：Electron 主进程在后端 live 后通过专用 `/internal/model-runtime/bootstrap` 注入版本 2 保险库快照，renderer 创建前完成启动应用；新配置测试、增删改、策略与运行状态使用固定 IPC 和独立字段白名单，后端不再接收模型环境变量或因保存配置而重启。配置写入与运行时热应用共用串行事务，成功/失败并发不会丢失已提交更新；保险库或运行时回滚任一失败会返回安全恢复错误并锁定后续修改，等待应用重启/bootstrap 恢复。旧设置页测试与保存也复用同一多配置队列，保留额外模型及推理能力元数据；冷启动兼容 GET 优先读取已 bootstrap 的运行时默认配置，显式开发环境配置仍优先。完整前端为 Electron Node 103 passed、Vitest 56 passed；隔离数据目录完整后端为 257 passed、7 skipped；`git diff --check` 通过。下一项为 Task 10 前端类型、API 与 Pinia 状态。

T-033 Task 10 已完成：renderer 新增多配置、模型能力、运行状态与学习空间偏好类型；桌面模式只调用六个固定模型配置桥接方法，桥接缺失时拒绝退回通用 IPC，Web 模式仅使用公开单配置兼容接口且不访问 `/internal/*`。Pinia 提供配置刷新、测试、增删改、策略保存和会话偏好读写；配置刷新与变更串行，状态请求部分失败不清空已有列表，A→B→A 会话切换、重叠加载和连续保存均以版本号与已提交快照抵御迟到响应，忙碌状态使用计数器覆盖排队操作。聚焦 API/store 21 passed，IPC 契约 20 passed；完整前端为 Electron Node 103 passed、Vitest 65 passed；`build:desktop` 与 `git diff --check` 通过。下一项为 Task 11 多配置模型设置界面。

T-033 Task 11 已完成：模型设置页重做为 openhanako 风格暖色连接工作台，左侧配置卡片支持选择、新建、复制、默认星标、启停、测试、删除确认和备用顺序，中间编辑器支持多模型、固定推理适配器与 `auto/off/low/medium/high/xhigh` 白名单档位，右侧显示运行、安全与切换说明。新配置必须输入 Key，旧配置不回填 Key，草稿修改后必须重新测试，测试/保存失败和保存完成均清空 Key；默认配置不能直接停用或删除。主进程允许故障中的已有非默认配置直接停用，重新启用仍必须通过连接测试。浏览器在 1440px 与 375px 验证无横向溢出，窄屏菜单和首配引导可见，控制台无错误；完整前端为 Electron Node 104 passed、Vitest 71 passed，`build:desktop` 与 `git diff --check` 通过。下一项为 Task 12 学习空间模型与推理强度选择器。

T-033 Task 12 已完成：学习助手输入区新增本空间模型选择器，支持跟随全局或手动配置/模型、`auto/off/low/medium/high/xhigh` 思考强度及继承/开启/关闭单空间自动备用；按钮显示实际模型与按能力降档后的生效强度，不支持档位在弹层中禁用。SSE `meta` 更新实际配置、模型、推理档位与自动切换提示；输出后 `interrupted` 保留已有文字并提供“使用备用配置继续”，点击后把中断内容固定为只读历史并发起新的普通学习请求，不拼接旧消息或携带 API 配置。会话切换清除上一空间的实际模型与中断状态。浏览器在 1440px 与 375px 验证输入区无横向溢出、选择按钮可见且控制台无错误；完整前端为 Electron Node 104 passed、Vitest 75 passed，`build:desktop` 与 `git diff --check` 通过。下一项为 Task 13 兼容迁移、故障注入和完整桌面验收。

T-033 Task 13 与整项任务已完成：旧 `GET /api/settings/model` 返回运行时默认配置脱敏视图，旧连接测试转接统一 runtime tester，生产保存继续拒绝明文 `.env`。429 会安全解析并限制数字 `Retry-After`，在剩余截止时间内最多等待重试一次，否则立即转备用；熔断器采用同一冷却。认证/权限失败后的主配置进入 `needs_attention`，后续请求不再重复触碰无效凭据，直到新快照应用。故障矩阵覆盖连接/超时、408/429/502/503/504、401/403/404、零输出/已输出流、half-open、取消和 3 次/2 配置预算。隔离完整后端 281 passed、7 skipped；Electron Node 104 passed、Vitest 75 passed；`build:desktop`、PyInstaller 七格式 worker 与两次包启动检查通过。最新 unpacked 应用测试模式启动/退出无残留且日志无密钥命中；旧版加密配置真实桌面迁移为运行时版本 2，最终连接测试 5/5 成功，P50 1519 ms、P95 2105 ms，实际 `legacy-profile/legacy-model/deepseek-v4-pro/auto`，未输出 Key 或回复正文。账号与桌宠范围保持不变，S-019/T-036 继续暂停等待用户恢复。

用户已于 2026-07-16 恢复桌宠任务并明确授权按建议直接设计。Sol 当前在 `codex/desktop-pet-mvp` 分支执行 S-019/T-036 第一阶段：参考 Apache-2.0 的 openai/skills `hatch-pet` 固定 8×9、192×208 精灵图契约和校验思路，创建本项目原创角色；优先交付独立透明置顶窗口、拖动位置、多屏/DPI、九动画状态、任务联动、点击/双击、显示/隐藏/缩放/速度及空闲节流。全面许可证审计、完整视觉 QA、全部状态人工核对、用户形象导入和语音鼓励按用户要求保留后续。

S-019/T-036 第一阶段桌宠 MVP 已完成：Electron 独立 sandbox 窗口与 preload、pet.json/spritesheet.webp 严格读取和非法自定义回退、原创“墨团”九行动画、拖动与位置持久化、多显示器/DPI 约束、点击挥手/双击跳跃、显示/隐藏/缩放/速度、隐藏暂停与长空闲降频均已落地。主应用书桌卡可控制设置，SmartTutor 的生成/校验/完成/失败及全局加载可自动驱动 running/review/waiting/failed/idle。真实 Windows unpacked 验收发现并修复缩放后立即拖动可能读取原生瞬态 bounds 的问题；最终显示隐藏、缩放恢复、立即拖动、双击和五任务状态均通过。后续保留角色导入 UI、语音鼓励、全面许可证审计、完整视觉 QA 和九状态逐帧人工核对。

Luna 批次已完成并通过复审。README、API 示例、协议说明、评测样例和开发总结已同步当前代码。L-007、L-008、L-009 已完成：快捷测试入口和浏览器测试台均已通过自动化测试、浏览器检查及打包启动自检；竞品对照和后端优化方案已形成。S-009 已就绪，等待切换 Sol 后实施跨模块学习闭环代码。

INBOX-002 已联调：后端已支持用户自定义 OpenAI 兼容或 Anthropic 网关。DeepSeek OpenAI 兼容路径已完成真实普通调用、SSE 分片与协议联调；后续可转入前端或 Electron 集成阶段。

前端续作已完成：L-010 的临时清单已用于完成 T-026/T-027，并按约定删除；前端的长期交付状态与验证结果见本队列完成记录。仅在用户确认需要桌面安装包时，才解除 T-028。

Terra 前端批次已完成 T-026 与 T-027：真实模型驱动的诊断、画像、资源、答题、复习与六页响应式界面均已验收；前端新增流式错误恢复和 Vitest 回归。Element Plus 改为按需引入后，主 JavaScript 从 1,099.07 kB（gzip 365.04 kB）降至 309.13 kB（gzip 114.46 kB），主样式从 365.09 kB（gzip 49.96 kB）降至 59.72 kB（gzip 9.42 kB），已消除大包告警。用户已确认需要 Electron 桌面端，并指定 openhanako 为参考；T-028 已解除阻塞并进入实现。

T-030 已完成：应用壳改为 openhanako 式三栏陪伴工作台，左侧为学习空间/对话导航，中间为欢迎式学习对话，右侧为今日书桌、学习便签、下一步与来源信息；暖色纸张、墨色文字、蓝绿与琥珀点缀已经统一。账号和桌宠仍未实现，但分别保留账号入口和桌宠插槽；现有 FastAPI、SSE、Electron IPC、模型设置自动引导和令牌隔离未改变。代码审查后补齐同路由建议更新、生成期间会话归属、模型设置入口、共享便签状态、移动端会话切换和抽屉可访问名称。桌面 1440×900 与窄屏 375×812 浏览器验收无横向滚动，完整 Electron Node 69 项、Vitest 33 项、Web 和桌面构建均通过。

T-031 已完成：体验测试截图中的“服务离线”并非 `api.exe` 未启动，而是 `sandbox: true` 窗口加载 ESM `preload.mjs` 后没有暴露 `window.a3Desktop`，渲染器因此误退回 Web 传输。预加载改为沙箱兼容的 CommonJS `preload.cjs`，固定 IPC 能力和令牌隔离边界保持不变。真实桌面窗口重启后，Electron 日志确认渲染器依次访问 `/health/live`、`/health/ready`、`/api/settings/model` 并返回 200；完整 Electron Node 70 项、Vitest 33 项通过。

T-028 已完成：Electron 主进程统一代理普通 HTTP/SSE 并独占动态后端地址和短期 token；preload 只暴露固定请求、流、取消和后端退出桥接；renderer 不接触 token。S-012 定位到退出残留的根因是 `closed` 回调读取已销毁 `BrowserWindow.webContents`，触发 `Object has been destroyed` 并中断退出；改为窗口创建时缓存 `webContents` 后，开发版和 unpacked 版测试模式均退出码 0 且无残留。完整 Node 49 项、Vitest 14 项、Web/桌面构建、unpacked、NSIS 与渲染器密钥扫描全部通过。发布包仍使用默认 Electron 图标且未配置代码签名/作者元数据，列为后续品牌与正式发行优化，不阻塞当前功能交付。

S-013 已完成：前端实际使用的 13 组 HTTP/SSE 路径与 FastAPI 路由、Electron 白名单一致，后端快捷测试 80 项、Electron Node 49 项及 Vitest 14 项通过。专项复核同时确认两项交付缺口：全新安装版无模型密钥时 `/health/ready` 返回 503，而前端与 Electron 未开放配置保存/连通性测试，生产后端也禁止明文 `.env` 落盘；FastAPI 的 `detail` 错误与业务 `{code,message}` 错误在 Web/Electron 的解析不一致。前者登记 S-014，后者登记 T-029。

S-014 已完成：安装版首次无配置自动进入模型设置；测试成功后才可保存，主进程使用 Electron `safeStorage` 加密持久化并以环境变量注入后端，ready 失败恢复旧密文和旧后端；renderer 不接触桌面令牌、持久化密钥或配置路径。桌面与窄屏视觉已按 openhanako 参考验收，账号体系和桌宠仅保留模块化扩展边界。最终回归为后端 80 项、Electron Node 66 项、Vitest 23 项；Web/desktop/unpacked/NSIS 全部通过。当前 Sol 批次完成，下一项 T-029 属于 Terra。

S-015 已完成：`E:\软件杯` 已初始化为本地 `main` 单仓库，根级 `.gitignore` 排除真实 `.env`、密钥文件、数据库、虚拟环境、依赖、构建/安装产物、桌面后端和临时 `.superpowers` 目录；`.gitattributes` 固定源码 LF、Windows 脚本 CRLF 和二进制文件属性。首个基线提交已创建，未连接远程仓库，也未写入永久 Git 身份配置。当前 Sol 批次完成，下一项仍为 Terra 的 T-029。

S-016 已完成：本仓库提交身份已设置为 `Wei kb <212667660@qq.com>`；私有远程 `origin` 指向 `https://github.com/212667660-arch/a3-learning-agents.git`，本地 `main` 已建立 `origin/main` 上游并完成首次推送。GitHub 页面已显示两条基线提交；完成记录提交后再次推送并核对本地、上游与远程哈希一致。当前 Sol 批次完成，下一项仍为 Terra 的 T-029。

## 九、任务完成记录

| 日期 | 任务 ID | 模型 | 修改文件 | 验证结果 |
| --- | --- | --- | --- | --- |
| 2026-07-16 | S-019 / T-036 第一阶段 | Sol | a3-front/a3-front/electron/pet-*、electron/pet/、electron/pets/motuan/、tools/pet/、src/components/pet/、src/pet/、electron/main.mjs、preload.cjs、ipc-contract.mjs、src/api/、DeskPanel.vue、AppLayout.vue、SmartTutor.vue 及测试；README.md、src/api/README.md、codex/AI模型任务队列.md | 交付原创“墨团”透明置顶桌宠 MVP：严格 8×9 atlas 清单、非法自定义回退、拖动/位置、多屏/DPI、九状态、任务联动、点击/双击、显示/隐藏/缩放/速度及资源节流。上游 Apache-2.0 validator 验证 1536×1872 RGBA WebP、透明残留 0、错误 0；完整 `npm test` 为 Electron 121 passed、Vitest 84 passed，修复真实 Windows 缩放后立即拖动的瞬态 bounds 回归并新增控制器测试；`build:desktop`、`desktop:pack` 通过。unpacked 同时加载主界面/学习伙伴，canvas 非透明像素 25,043，DPI 1.5 backing 288×312；显示隐藏、1.25×/1.5×设置、恢复后立即拖动、双击事件和 running/review/waiting/failed/idle 固定 IPC 均通过，测试进程和临时设置已清理。完整视觉/许可证 QA、逐帧状态核对、导入 UI 与语音留后续。 |
| 2026-07-16 | T-033 Task 13 / T-033 完成 | Sol | backend/errors.py、services/llm_service.py、model_resilience.py、model_runtime.py、model_settings.py 及测试；README.md、backend/API示例.md、a3-front/a3-front/src/api/README.md、codex/AI模型任务队列.md | 旧接口兼容测试转接统一运行时；新增有界 Retry-After、同配置一次等待重试、截止时间切备用和熔断冷却；认证/权限失败后主配置进入 needs_attention，避免重复无效调用。故障矩阵覆盖连接/超时、408/429/502/503/504、401/403/404、流边界、half-open、取消与尝试预算。隔离后端 281 passed/7 skipped，Electron 104 passed、Vitest 75 passed，桌面构建、后端七格式打包和启动检查通过；unpacked 测试启动无残留，最终真实加密配置 5/5 成功，P50 1519 ms、P95 2105 ms；密钥与回复正文未输出。 |
| 2026-07-16 | T-033 Task 12 | Sol | a3-front/a3-front/src/components/model/ModelSelectionPopover.vue 及测试、src/views/SmartTutor.vue 及测试、src/api/types.ts、codex/AI模型任务队列.md | 输入区新增学习空间配置/模型/思考强度/自动备用偏好；模型能力过滤与 `xhigh→high` 实际显示有回归。SSE 自动切换显示非阻断提示，输出后中断保留文字并通过新请求续写，会话切换清除旧空间实际模型。浏览器 1440px/375px 无横向溢出、控制台无错误；完整 `npm test` 为 Electron Node 104 passed、Vitest 75 passed；`build:desktop` 和 `git diff --check` 通过。 |
| 2026-07-16 | T-033 Task 11 | Sol | a3-front/a3-front/src/components/model/ModelProfileList.vue 及测试、ModelProfileEditor.vue 及测试、src/views/ModelSettings.vue 及测试；electron/model-profile-controller.mjs 及测试；codex/AI模型任务队列.md | 以暖色连接工作台替换单配置页面，支持配置选择、新建、复制、默认、启停、测试、删除、备用排序、多模型与推理能力白名单；Key 不回填，未测试草稿不能保存，失败/保存后清空。故障中的非默认配置可离线停用，重新启用仍需测试。浏览器 1440px 与 375px 无横向溢出且控制台无错误；完整 `npm test` 为 Electron Node 104 passed、Vitest 71 passed；`build:desktop` 和 `git diff --check` 通过。 |
| 2026-07-16 | T-033 Task 10 | Sol | a3-front/a3-front/src/api/types.ts、backend.ts、backend.test.ts、transport.ts；src/stores/backend.ts、backend.test.ts；electron/ipc-contract.mjs、ipc-contract.test.mjs；codex/AI模型任务队列.md | renderer 已具备脱敏多配置、运行状态与学习空间偏好类型/API/Pinia 状态；桌面固定桥接缺失时安全拒绝，Web 仅走公开兼容接口。配置刷新与变更串行，A→B→A 加载、重叠保存、失败回滚与忙碌计数均有并发回归。聚焦 API/store 21 passed，IPC 20 passed；完整 `npm test` 为 Electron Node 103 passed、Vitest 65 passed；`build:desktop` 和 `git diff --check` 通过。 |
| 2026-07-16 | T-033 Task 9 | Sol | a3-front/a3-front/electron/model-profile-controller.mjs 及测试、electron/ipc-contract.mjs 及测试、electron/main.mjs、electron/preload.cjs、electron/runtime.test.mjs、package.json；backend/services/model_runtime.py、backend/services/model_settings.py、backend/tests/test_model_settings.py；codex/AI模型任务队列.md | 完成版本 2 保险库启动 bootstrap、固定多配置 IPC、严格输入白名单、无重启热应用、串行配置事务、失败回滚与恢复锁。旧设置页复用同一事务队列并保留多模型/推理能力元数据；冷启动 GET 读取运行时默认配置且不返回 Key。三轮代码审查的并发覆盖、回滚误报和旧 UI 破坏性兼容问题均已修复，最终复审无 Critical/Important。`npm test` 为 Electron Node 103 passed、Vitest 56 passed；隔离 `A3_DATA_DIR` 的完整后端为 257 passed、7 skipped；`git diff --check` 通过。 |
| 2026-07-15 | T-035 Task 12 / T-035 完成 | Sol | backend/knowledge/import_service.py、parsers.py、worker_main.py、run.py、build_api.ps1、verify_api_package.ps1、backend/tests/knowledge/test_malicious_documents.py、test_knowledge_performance.py、test_packaged_worker.py；a3-front/a3-front/electron/knowledge-import.mjs 及测试、electron/main.mjs、package.json；README.md、backend/API示例.md、src/api/README.md、codex/AI模型任务队列.md | frozen 后端改用 `api.exe --knowledge-worker`，worker JSONL 固定 UTF-8，XLSX 从无扩展名已校验对象流解析，PyInstaller 显式收集七格式依赖，桌面首次创建可选 pack 安装说明。最终 `compileall` 和完整 pytest 216 passed；Electron Node 82 passed、Vitest 56 passed；打包 worker 7 passed 且 `/health/live`、`/test` 通过；`build:desktop` 通过。性能为 10 MiB PDF 2.491 秒、FTS P95 77.847 ms、取消 0.002 秒、健康检查 P95 1.394 ms。安装包 136.92 MiB、解压应用 470.85 MiB、内嵌后端 161.66 MiB；密钥、renderer/asar 路径令牌、计划占位符和差异扫描通过。 |
| 2026-07-15 | T-035 Task 11 | Sol | a3-front/a3-front/src/views/KnowledgeLibrary.vue 及测试、src/components/knowledge/ 及测试、src/views/SmartTutor.vue 及测试、src/router/index.ts、src/layouts/AppLayout.vue、src/components/workspace/ConversationRail.vue、src/styles/global.scss、src/api/types.ts | 提交 `fdfcc04`；实现 openhanako 风格暖色三栏本地知识库与窄屏双抽屉，集合切换按集合加载且忽略迟到响应，桌面导入进度终态刷新，学习助手支持集合绑定、local_search_only 与 allow_model_context 隐私模式，并将本地引用路由到知识库 inspector 后按安全 locator 打开只读副本。路径/令牌扫描只命中否定测试；`git diff --check` 通过；`npm run test` 为 Electron Node 81 passed、Vitest 56 passed；`npm run build:desktop` 通过，最大主包 343.92 kB。 |
| 2026-07-15 | S-018 | Sol | a3-front/a3-front/docs/superpowers/specs/2026-07-15-local-knowledge-base-design.md、docs/superpowers/plans/2026-07-15-local-knowledge-base-plan.md、codex/AI模型任务队列.md | 采用 Electron userData 本地对象存储、SHA-256 去重、隔离 parser worker、七格式限制、SQLite FTS5 + CJK token、可选 OCR/NumPy 语义包、RRF、学习空间集合绑定、隐私模式和可追溯引用。实施计划拆为 12 个 TDD 任务、79 个步骤和 12 个提交点；占位符、类型、路径、限额、稳定错误码、24 小时孤立清理、PyInstaller 与桌面发布门槛均完成自审；T-035 已解除阻塞。按用户要求 S-019/T-036 保持不变，本轮不设计桌宠。 |
| 2026-07-15 | S-017 | Sol | a3-front/a3-front/docs/superpowers/specs/2026-07-15-multi-api-stability-design.md、docs/superpowers/plans/2026-07-15-multi-api-stability-plan.md、codex/AI模型任务队列.md | 用户确认稳定优先、手动主配置 + 自动备用切换、全局默认 + 学习空间覆盖、流式已输出后不静默换模型，并授权后续设计直接采纳。设计采用 Electron `safeStorage` 版本 2 保险库 + 后端原子内存路由器，规定可重试错误、3 次/2 配置总预算、熔断冷却、密钥边界、模型能力声明、推理档位映射、兼容迁移和发布门槛。实施计划拆为 13 个 TDD 任务、91 个步骤和 13 个提交点；占位符、矛盾、类型一致性和需求覆盖自审通过，T-033 已解除阻塞。 |
| 2026-07-15 | T-034 | Terra | codex/AI模型任务队列.md；本地桌面运行日志与临时基线脚本（未落盘） | 使用正确项目配置连续执行后端真实调用 5 次，5/5 成功，延迟 1065–2108 ms、P50 1329 ms、P95 2108 ms；同一客户端首次 2004 ms、空闲 7 秒后 1002 ms、立即复用 1125 ms，无空闲重连退化。Electron → safeStorage → IPC → FastAPI → DeepSeek 全链路连续测试 3 次，3/3 成功，接口延迟 1230–1775 ms、端到端 1429–1947 ms。日志无认证、连接、超时或 SDK 重试错误；确认 OpenAI 客户端复用、默认 2 次重试和 60 秒超时生效。累计 11 次真实调用全部成功，未发现可复现连接 Bug，参数优化留给 S-017 稳定优先架构。 |
| 2026-07-15 | T-032 | Terra | backend/services/llm_service.py、backend/tests/test_llm_gateway.py；a3-front/a3-front/electron/main.mjs、electron/model-config.mjs、electron/model-config.test.mjs；src/stores/backend.ts、src/views/ModelSettings.vue、src/views/ModelSettings.test.ts；desktop-backend；codex/AI模型任务队列.md | 根因包括 Windows 将普通 HTTP CONNECT 代理登记为 HTTPS、Electron 继承终端 `OPENAI_API_KEY` 覆盖项目配置，以及渲染器自行误判首次配置。OpenAI/Anthropic 客户端统一 `trust_env=False`；桌面启动环境移除所有模型变量，仅允许 safeStorage 显式注入；配置加载期间禁用测试，空 Key 委托主进程安全存储。新 `api.exe` 启动自检通过；真实桌面完成正确 Key 内存迁移、连接测试 1591 ms、加密保存、后端重启及留空复测 1557 ms，未输出 Key。最终 `pytest -q backend` 88 passed；Electron Node 71 passed；Vitest 35 passed；`npm run build:desktop` 退出码 0。 |
| 2026-07-15 | T-031 | Terra | a3-front/a3-front/electron/main.mjs、electron/preload.cjs（替代 preload.mjs）、electron/runtime.test.mjs、codex/AI模型任务队列.md | 修复 Electron 沙箱不加载 ESM preload 导致 `window.a3Desktop` 缺失、渲染器误走 Web 传输并显示“服务离线”。新增 CommonJS preload 回归；`npm run test` 为 Electron Node 70 passed、Vitest 33 passed。真实窗口日志确认 `/health/live`、`/health/ready`、`/api/settings/model` 均经 IPC 代理访问并返回 200，应用保持运行供用户继续测试。 |
| 2026-07-15 | T-030 | Terra | a3-front/a3-front/src/components/workspace/ConversationRail.vue、DeskPanel.vue 及测试；src/layouts/AppLayout.vue 与测试；src/views/SmartTutor.vue 与测试；src/views/Dashboard.vue；src/styles/global.scss；设计与实施计划；codex/AI模型任务队列.md | 以 openhanako 为参考完成暖色三栏陪伴式工作台，保留真实后端、SSE、模型安全流程，并预留账号和桌宠扩展边界。TDD 新增 5 项前端行为回归；代码审查问题已收敛，包括同路由建议更新、生成取消会话归属、模型设置入口、双书桌共享便签、移动会话切换和抽屉名称。`npm run test` 为 Electron Node 69 passed、Vitest 33 passed；`npm run build` 与 `npm run build:desktop` 退出码 0。浏览器 1440×900 确认左右栏分别 220/290 px，375×812 确认左右栏收起、菜单和输入区可见且无横向滚动。 |
| 2026-07-15 | T-029 | Terra | backend/main.py、backend/errors.py、backend/routers/chat.py、backend/routers/sessions.py、backend/routers/learning.py、backend/tests/error_assertions.py 及错误回归；a3-front/a3-front/electron/backend-proxy.mjs、electron/backend-proxy.test.mjs、src/api/transport.ts、src/api/desktop-transport.ts、src/api/desktop-transport.test.ts、README 文档 | 统一 `code/message/retryable/request_id` 错误信封，覆盖 FastAPI 404/405/422/500/503、业务资源 404、非法 CORS 预检和非 JSON 错误，同时保留合法 3xx 跳转；Electron SSE 建流失败保留 404/422/503 状态，Web/Electron 均转换为 `BackendApiError`。完整后端 `compileall` 与 pytest 87 passed（工作区独立 basetemp），Electron Node 69 passed，Vitest 28 passed，`npm run build` 与 `npm run build:desktop` 均退出码 0。 |
| 2026-07-14 | S-016 | Sol | .git/config、codex/AI模型任务队列.md、GitHub `212667660-arch/a3-learning-agents` | 设置仓库级提交身份 `Wei kb <212667660@qq.com>`；确认 `origin` 为 GitHub 私有仓库，`git push -u origin main` 退出码 0并建立上游；GitHub 页面显示 `main`、2 commits 和项目文件。完成记录提交后再次推送，并使用 `git fetch`、`git rev-parse HEAD`、`git rev-parse origin/main`、`git ls-remote origin refs/heads/main` 验证三方哈希一致；工作区保持干净。 |
| 2026-07-14 | S-015 | Sol | .gitignore、.gitattributes、codex/AI模型任务队列.md、Git 仓库元数据 | 在 `E:\软件杯` 初始化 `main` 单仓库；候选集审计后提交 156 个源码、测试、文档及小型验收文件，无超过 10 MiB 文件；真实 `backend/.env`、`backend/competition`、`node_modules`、`dist`、`release`、`desktop-backend`、数据库、凭据文件和 `.superpowers` 临时目录均不在索引。密钥特征扫描无命中；后端快捷测试 80 passed，`npm run test` 为 Electron Node 66/66、Vitest 23/23。首个提交 `16619b1`（`chore: establish A3 project baseline`）使用一次性本地 Codex 署名，未配置远程。 |
| 2026-07-14 | S-014 | Sol | a3-front/a3-front/electron/model-config.mjs、electron/model-config-controller.mjs 及测试、electron/main.mjs、electron/preload.mjs、electron/ipc-contract.mjs、electron/runtime.test.mjs、src/api/、src/stores/backend.ts、src/layouts/AppLayout.vue、src/views/ModelSettings.vue、src/views/SmartTutor.vue 及测试、README.md、src/api/README.md、docs/superpowers/specs/2026-07-14-secure-model-settings-design.md、docs/superpowers/plans/2026-07-14-secure-model-settings-plan.md、release/、codex/AI模型任务队列.md | 新增 `safeStorage` 密文存储、固定受信 IPC、启动注入、测试后保存、ready 回滚、首次引导与未配置发送锁定；自审补充损坏凭据结构化错误和测试期间表单修改竞态回归。`backend/quick_test.ps1` 80 passed；`npm run test` 为 Node 66/66、Vitest 23/23；`npm run build`、`npm run build:desktop`、`npm run desktop:pack`、`npm run desktop:dist` 均退出码 0。全新隔离 userData 的 unpacked 启动退出码 0，ready/stop/forced-exit 日志齐全，`backend/app.db` 位于隔离目录，无 `model-settings.enc`，残留进程 0。安装包 `release/智学协作台 Setup 0.0.0.exe` 为 103,725,300 bytes；视觉截图保留于 `codex/artifacts/S-014-model-settings-desktop.png` 和 `S-014-model-settings-narrow.png`。 |
| 2026-07-14 | S-013 / INBOX-008 | Sol | codex/AI模型任务队列.md | 静态核对前端 API、Electron 路由白名单、FastAPI 路由及请求/响应/SSE 字段；`backend/quick_test.ps1` 80 passed，前端 `npm run test` 为 Node 49/49、Vitest 14/14。隔离数据目录启动打包后端：`/health/live` 200，`/health/ready` 503，`api_key_configured=false`；Node 直接验证 `PUT /api/settings/model` 与 `POST /api/settings/model/test` 均被 Electron 拒绝。确认核心学习主流程无路径/方法错位，安装版模型配置闭环与错误信封一致性分别转入 S-014、T-029。 |
| 2026-07-14 | S-012 | Sol | a3-front/a3-front/electron/main.mjs、a3-front/a3-front/electron/runtime.test.mjs、codex/AI模型任务队列.md | 根据用户截图定位 `Object has been destroyed`：`closed` 回调在窗口已销毁后读取 `mainWindow.webContents`，异常中断 `process.exit(0)`；新增先红后绿回归并缓存创建时的 `webContents`。`node --test electron/runtime.test.mjs` 11/11 通过；开发 Electron 测试模式退出码 0，后端 ready/stop 日志完整且 Electron/Node/api.exe 无残留。 |
| 2026-07-14 | T-028 | Terra/Sol | a3-front/a3-front/electron/backend-proxy.mjs、electron/ipc-contract.mjs、electron/main.mjs、electron/preload.mjs、electron/runtime.test.mjs、electron/backend-proxy.test.mjs、src/api/transport.ts、src/api/desktop-transport.ts、src/api/web-transport.ts、src/api/backend.ts、src/api/client.ts、src/api/README.md、src/env.d.ts、src/layouts/AppLayout.vue、src/views/SmartTutor.vue、README.md、package.json、release/、codex/AI模型任务队列.md | 主进程 HTTP/SSE 代理、路由/来源/体积校验、流归属与取消、token/地址隔离、桌面/Web transport 和关闭恢复完成。`npm run test`：Node 49/49、Vitest 14/14；`npm run build`、`npm run build:desktop`、`npm run desktop:pack`、`npm run desktop:dist` 全部退出码 0；unpacked 应用测试模式退出码 0、内嵌 `resources/backend/api.exe`、无残留；renderer token 扫描干净。生成 `release/win-unpacked/智学协作台.exe` 与 `release/智学协作台 Setup 0.0.0.exe`（103,688,784 bytes）。 |
| 2026-07-13 | S-011 | Sol | a3-front/a3-front/docs/superpowers/specs/2026-07-13-electron-main-ipc-proxy-design.md、a3-front/a3-front/docs/superpowers/plans/2026-07-13-electron-main-ipc-proxy-plan.md、codex/AI模型任务队列.md | 用户确认桌面优先的主进程 HTTP/SSE 统一代理；明确普通请求、SSE、取消、错误、窗口归属、路由白名单、流缓冲/并发边界与开发回退，保证 renderer 不接触 token/地址。计划为 Terra 提供按 TDD 执行的文件、代码骨架、测试命令和打包验收步骤；文档自检无 TBD/TODO/模糊占位。当前目录不是 Git 仓库，未执行提交。 |
| 2026-07-13 | T-028（部分完成，下载阻塞） | Terra | a3-front/a3-front/electron/main.mjs、electron/preload.mjs、src/api/client.ts、src/layouts/AppLayout.vue、src/styles/global.scss、README.md、package.json、package-lock.json、.gitignore、codex/AI模型任务队列.md | 参考 openhanako 的暖色三栏工作台完成 A3 界面适配；主进程具备动态端口、短期 token、FastAPI 生命周期、userData、preload、单实例和打包配置，源码 `node --check` 通过；前端 `npm run test` 5 passed、`npm run build` 通过，浏览器预览正常。Electron 二进制安装两次失败（HTTPS ETIMEDOUT），本机无缓存/现成 electron.exe，故桌面运行、unpacked 包和 NSIS 安装包验收待网络恢复。 |
| 2026-07-13 | T-027 | Terra | a3-front/a3-front/src/main.ts、vite.config.ts、package.json、package-lock.json | 使用 `unplugin-vue-components` 按需加载 Element Plus，保留消息提示样式，并使该插件避开 Vitest 环境；前端 `npm run test` 5 passed、`npm run build` 通过；主 JS 从 1,099.07 kB 降至 309.13 kB，主 CSS 从 365.09 kB 降至 59.72 kB，Vite 大包告警消失；浏览器复核总览正常。 |
| 2026-07-13 | T-026 | Terra | a3-front/a3-front/src/api/backend.ts、src/api/backend.test.ts、src/stores/backend.test.ts、src/views/SmartTutor.vue、src/views/SmartTutor.test.ts、src/views/ProfileBuilder.vue、src/layouts/AppLayout.vue、src/tests/setup.ts、vite.config.ts、tsconfig.app.json、package.json、package-lock.json、backend/protocols/parser.py、backend/services/profile_agent.py、backend/services/learning.py、backend/tests/test_protocols.py、backend/tests/test_learning_progress.py | 新增前端 Vitest 回归（5 passed）、流式错误保留与重新编辑；真实浏览器完成诊断、画像、资源、错题、复习和正确答题，六路由及 375 px 窄屏验证通过；兼容“第 2 轮”/“80%”协议数字，修复 `|k|` 被误分割导致的正确答案误判。完整后端 pytest 80 passed，前端 `npm run test` 5 passed，生产构建通过。 |
| 2026-07-13 | L-010 / INBOX-007 | Luna | codex/前端续作清单.md、codex/AI模型任务队列.md | 盘点 `a3-front/a3-front`：Vue 3、Pinia、Element Plus、六个真实后端页面及 SSE/答题接口均已存在；`npm run build` 通过。当前后端未运行，`/health/live` 无法连接，因此真实接口和浏览器全流程留给 T-026；当前没有前端测试目录，生产主包 1,098.79 kB（gzip 364.92 kB）触发 Vite 告警，登记为 T-027。 |
| 2026-07-11 | S-010 | Sol | backend/services/resource_quality.py、backend/services/db.py、backend/services/learning.py、backend/services/resource_agent.py、backend/services/orchestrator.py、backend/database.py、backend/models/schemas.py、backend/routers/learning.py、backend/routers/sessions.py、backend/test_console.html、backend/tests/test_resource_quality.py、backend/tests/test_learning_progress.py、backend/API示例.md、README.md、codex/architecture/S-010-自适应下一步与资源质量门槛.md、codex/AI模型任务队列.md | 新增 REVIEW/START_PRACTICE/REMEDIATE/PRACTICE/CONSOLIDATE/CHALLENGE 下一步决策；资源质量检查难度覆盖、题量、重复题和笔记长度，低于 60 分自动修复；持久化质量分和问题码并回填旧资源；浏览器验证下一步与质量结果；compileall 通过，pytest 78 passed，api.exe 重建并启动检查通过。 |
| 2026-07-11 | S-009 | Sol | backend/protocols/models.py、backend/protocols/parser.py、backend/protocols/__init__.py、backend/database.py、backend/services/db.py、backend/services/learning.py、backend/services/resource_agent.py、backend/services/orchestrator.py、backend/models/schemas.py、backend/routers/learning.py、backend/routers/sessions.py、backend/main.py、backend/test_console.html、backend/tests/test_learning_progress.py、backend/tests/test_protocols.py、backend/tests/test_resource_cache.py、backend/tests/test_web_resource_integration.py、backend/API示例.md、README.md、codex/architecture/S-009-学习掌握度答题反馈与自适应复习闭环.md、codex/AI模型任务队列.md | 新增知识点、结构化题目、答题记录和复习任务；实现幂等答题、规则判分、掌握度更新、错题/进度/复习接口、旧数据回填、学习状态缓存失效和自适应资源上下文；浏览器完成正确答题、掌握度和复习队列实测；compileall 通过，pytest 75 passed，api.exe 重建并启动检查通过。 |
| 2026-07-11 | L-009 | Luna | codex/竞品对比与后端优化方案.md、codex/AI模型任务队列.md | 完成 Quizlet 类记忆学习、Khanmigo 类 AI 导学、Duolingo 类技能树、Anki 类间隔复习和题目型学习产品的能力对照；确认 A3 的 P0 短板为知识点掌握度、答题反馈、练习题结构化和复习调度，并登记 Sol 的 S-009 实施任务。 |
| 2026-07-11 | L-008 | Luna | backend/main.py、backend/test_console.html、backend/build_api.ps1、backend/verify_api_package.ps1、backend/tests/test_api.py、README.md、codex/AI模型任务队列.md | 新增同源浏览器测试台 `/test`，支持健康检查、模型状态、普通对话、SSE 流式对话、生成取消、会话读取和在线检索；HTML 已纳入 PyInstaller；浏览器实测 `/health/live` 与 `/health/ready` 正常，完整快捷测试 70 passed，打包后的测试台加载检查通过。 |
| 2026-07-11 | L-007 | Luna | backend/quick_test.ps1、backend/quick_test.bat、backend/quick_package_test.bat、README.md、codex/AI模型任务队列.md | 新增自动寻找项目 Python 环境的快捷测试脚本；默认执行 compileall 与完整 pytest，Package 模式额外执行 PyInstaller 和 api.exe 启动自检；常规入口验证 69 passed，完整入口验证 69 passed、打包成功、Package launch check passed。 |
| 2026-07-11 | T-025 | Terra | backend/main.py、backend/config.py、backend/errors.py、backend/routers/chat.py、backend/services/db.py、backend/services/orchestrator.py、backend/services/rate_limit.py、backend/tests/test_api.py、backend/tests/test_orchestrator.py、backend/tests/test_rate_limit.py、backend/tests/test_security.py、backend/tests/test_streaming.py、backend/.env.example、README.md、backend/API示例.md、codex/AI模型任务队列.md | 取消接口要求并校验 session_id，拒绝跨会话取消；生产或配置桌面令牌时，对聊天、画像、资源和检索接口执行不记录原始令牌的滑动窗口限流，并返回 429/Retry-After；诊断历史保留首条学习目标且受消息数、字符数边界约束。compileall 通过，聚焦 pytest 19 passed，完整 pytest 69 passed，api.exe 重建并启动检查通过。 |
| 2026-07-11 | T-024 | Terra | backend/services/security.py、backend/main.py、backend/config.py、backend/errors.py、backend/services/model_settings.py、backend/services/llm_service.py、backend/services/orchestrator.py、backend/services/profile_agent.py、backend/services/resource_agent.py、backend/services/db.py、backend/protocols/parser.py、backend/tests/test_security.py、backend/tests/test_model_settings.py、backend/tests/test_llm_gateway.py、backend/tests/test_protocols.py、backend/tests/test_streaming.py、backend/tests/test_runtime_cleanup.py、backend/.env.example、README.md、backend/API示例.md、codex/AI模型任务队列.md | 新增生产 token 中间件、开发兼容策略、生产明文密钥落盘阻止、base_url scheme/IP/DNS 校验、OpenAI SSE 403/404 映射、未知 SSE 错误事件、至少一道练习题校验及三类模型网关和会话锁清理；compileall 通过，pytest 65 passed，api.exe 重建并启动验证通过。 |
| 2026-07-11 | S-008 | Sol | codex/architecture/S-008-生产本地API鉴权与模型配置安全边界.md、codex/AI模型任务队列.md | 完成生产本地 API 鉴权、Electron token 生命周期、模型密钥存储、base_url SSRF 防护、generation 归属、限流和 Terra 实现清单；复核验证 compileall 通过、pytest 55 passed、api.exe 启动检查通过、当前模型网关 connected。 |
| 2026-07-11 | INBOX-001 | Sol | codex/AI模型任务队列.md | 检查 `backend/competition` 结构、大小和全部引用：9325 个文件、约 74.26 MB；README、评测命令和打包命令均直接使用该环境；`.gitignore` 已排除；结论为保留，未执行删除。 |
| 2026-07-11 | T-023 | Terra | backend/database.py、backend/services/db.py、backend/services/orchestrator.py、backend/models/schemas.py、backend/routers/chat.py、backend/routers/sessions.py、backend/tests/test_resource_cache.py、backend/tests/test_export_and_evaluation_cli.py、README.md、backend/API示例.md、codex/AI模型任务队列.md | 资源表新增兼容迁移 `sources_json`，持久化公开标题/链接/摘要；普通响应、SSE `sources`、缓存命中、会话历史和导出引用使用同一份来源快照。compileall 通过；pytest -q backend 55 passed；api.exe 重建并健康启动验证通过。 |
| 2026-07-10 | BACKEND-DELIVERY-REVIEW | Terra | backend/main.py、backend/errors.py、backend/services/llm_service.py、backend/services/model_settings.py、backend/routers/model_settings.py、backend/tests/test_api.py、backend/tests/test_llm_gateway.py、backend/tests/test_model_settings.py、README.md、backend/API示例.md、codex/AI模型任务队列.md | 修复模型设置 PUT 的 CORS 支持、OpenAI 兼容网关 403/404 错误映射、无桌面令牌时的本机访问限制及 README 安装命令；`compileall` 通过，`pytest -q backend` 30 passed，/health/live、/health/ready、/docs 和 CORS 预检通过。 |
| 2026-07-10 | INBOX-002-SUCCESS | Terra | backend/.env、backend/config.py、backend/errors.py、backend/services/llm_service.py、backend/tests/test_llm_gateway.py、codex/AI模型任务队列.md | 标准 MODEL_* 配置下 DeepSeek OpenAI 兼容网关真实普通调用与 SSE 分片成功；画像、资源协议首次校验通过，诊断协议经自动修复后通过。新增模型访问/不存在/请求无效诊断和客户端关闭方法；`compileall` 通过，`pytest -q backend` 26 passed。 |
| 2026-07-11 | T-022-LIVE-VERIFY | Terra | backend/services/web_search.py、backend/config.py、backend/.env.example、backend/tests/test_web_search.py、README.md、backend/API示例.md、codex/AI模型任务队列.md | 修正临时控制台中文编码干扰后，真实查询“一次函数 数学 教学资料”成功返回 5 条相关搜狗来源；新增搜狗首选中文检索和相关性过滤，DuckDuckGo/Bing 保留回退。pytest -q backend 51 passed。 |
| 2026-07-11 | T-022 | Terra | backend/services/web_search.py、backend/services/resource_agent.py、backend/services/orchestrator.py、backend/routers/web.py、backend/routers/resource.py、backend/models/schemas.py、backend/config.py、backend/.env.example、backend/tests/test_web_search.py、backend/tests/test_web_router.py、backend/tests/test_web_resource_integration.py、README.md、backend/API示例.md、codex/AI模型任务队列.md | 实现固定 DuckDuckGo/Bing RSS 公开检索回退、来源返回、资源生成参考上下文和网络失败降级。compileall 通过；pytest -q backend 50 passed。真实验证未完成：本机无代理，Bing、百度和 DuckDuckGo 均 ConnectError，等待外网恢复。 |
| 2026-07-10 | T-020/T-021 | Terra | backend/models/schemas.py、backend/services/model_settings.py、backend/routers/model_settings.py、backend/routers/sessions.py、backend/services/orchestrator.py、backend/main.py、backend/tests/test_model_settings.py、backend/tests/test_errors_and_sessions.py、backend/tests/test_runtime_cleanup.py、README.md、backend/API示例.md、codex/AI模型任务队列.md | 新增候选模型配置不落盘连通性检测；收紧会话/资源导出路径参数；应用生命周期结束时关闭模型客户端并清空内存运行态。compileall 通过；pytest -q backend 41 passed；api.exe 健康检查通过。 |
| 2026-07-10 | T-019 | Terra | backend/evaluation/history.py、backend/evaluation/live.py、backend/tests/test_evaluation_history.py、README.md、.gitignore、codex/AI模型任务队列.md | 真实评测新增 UTC 时间戳历史报告、与上次结果的回退比较和 failure_summary；分数/协议回退或调用失败会返回非零退出码。compileall 通过；pytest -q backend 40 passed。 |
| 2026-07-10 | T-018 | Terra | backend/services/profile_agent.py、backend/services/resource_agent.py、backend/protocols/parser.py、backend/evaluation/cases.json、backend/evaluation/sample_outputs.json、backend/tests/test_protocols.py、backend/tests/test_live_evaluation.py、backend/协议说明.md、README.md、codex/AI模型任务队列.md | 根据真实评测扣分收紧画像水平映射提示词，要求资源同时拥有非空笔记和分层练习；新增二次函数笔记回归样例。compileall 通过；pytest -q backend 38 passed；离线评测 7/7、平均分 100。 |
| 2026-07-10 | T-017 | Terra | backend/evaluation/live.py、backend/tests/test_live_evaluation.py、README.md、.gitignore、codex/AI模型任务队列.md | 新增显式真实模型评测命令：按固定样例调用当前网关，保存协议输出、单例耗时、失败代码及评分报告；未配置模型时直接拒绝执行。compileall 通过；真实调用由用户按命令触发，离线替身测试覆盖成功和未配置保护。 |
| 2026-07-10 | T-015/T-016 | Terra | backend/routers/sessions.py、backend/services/db.py、backend/evaluation/cli.py、backend/evaluation/sample_outputs.json、backend/evaluation/baseline.json、backend/tests/test_export_and_evaluation_cli.py、README.md、backend/API示例.md、.gitignore、codex/AI模型任务队列.md | 新增会话内学习资源 Markdown/TXT 导出；新增 JSON 输出离线评测命令、样例与基线比较。compileall 通过；pytest -q backend 34 passed；评测 6/6 覆盖、协议通过率 100%、平均分 100。 |
| 2026-07-10 | T-013/T-014 | Terra | backend/config.py、backend/database.py、backend/services/db.py、backend/services/orchestrator.py、backend/run.py、backend/build_api.ps1、backend/verify_api_package.ps1、backend/tests/test_resource_cache.py、README.md、backend/API示例.md、backend/requirements.txt、.gitignore、codex/AI模型任务队列.md | 实现同会话/同画像版本/同请求的 SQLite 持久化资源缓存（默认 24 小时、可关闭、HTTP/SSE 命中标识）；新增桌面数据目录隔离和 PyInstaller onedir 打包。compileall 与 pytest -q backend 32 passed；dist/api/api.exe 启动健康检查通过。 |
| 2026-07-10 | CUSTOM-GATEWAY-FEATURE | Terra | backend/config.py、backend/services/llm_service.py、backend/services/model_settings.py、backend/routers/model_settings.py、backend/models/schemas.py、backend/tests/test_llm_gateway.py、backend/tests/test_model_settings.py、backend/.env.example、README.md、backend/API示例.md、codex/AI模型任务队列.md | 支持 MODEL_PROVIDER=openai|anthropic、用户自定义 API 地址/模型名/密钥；新增本地 GET/PUT /api/settings/model（密钥脱敏、可选桌面令牌、更新后立即生效且保留其他 .env 配置）。`compileall` 通过；`pytest -q backend` 22 passed。 |
| 2026-07-10 | DEEPSEEK-V4-PRO-CONFIG | Terra | backend/.env、backend/.env.example、backend/config.py、README.md、codex/AI模型任务队列.md | OpenAI 兼容地址配置为 https://api.deepseek.com，模型为 deepseek-v4-pro；未认证端点返回 401 表明网络可达，最小真实调用返回 MODEL_AUTHENTICATION_ERROR；`compileall` 与 `pytest -q backend`（15 passed）通过。 |
| 2026-07-10 | INBOX-002-NETWORK-RETRY | Terra | codex/AI模型任务队列.md | 重试 api.openai.com:443：HTTPS 连接 12 秒超时，TCP 443 失败；未发起携带密钥的模型请求。等待网络或代理恢复。 |
| 2026-07-10 | OPENAI-TERRA-CONFIG | Terra | backend/.env、backend/.env.example、backend/config.py、backend/services/llm_service.py、README.md、codex/AI模型任务队列.md | 本地模型配置迁移到 OPENAI_*，默认模型为 gpt-5.6-terra；保留 HY_* 回退兼容。真实 API 权限和流式能力仍受 api.openai.com 连接超时阻塞。 |
| 2026-07-10 | INBOX-002-AUTH（旧混元配置） | Terra | backend/.env、backend/tests/test_errors_and_sessions.py、codex/AI模型任务队列.md | 混元端点可达（未认证探测 401）；最小真实调用返回 MODEL_AUTHENTICATION_ERROR，当前密钥无效或不属于混元。修复配置后的测试隔离问题；`compileall` 和 `pytest -q backend`（15 passed）通过。 |
| 2026-07-10 | INBOX-002-CHECK | Terra | codex/AI模型任务队列.md | 配置安全检查确认 `HY_API_KEY` 未配置；`GET /health/ready` 返回 503 `model_not_configured`；`pytest -q backend` 15 passed。真实 API、SSE 分片与取消等待有效配置。 |
| 2026-07-10 | LUNA-REVIEW | Luna | README.md、backend/API示例.md、backend/协议说明.md、backend/evaluation/cases.json、backend/evaluation/runner.py、.gitignore、学习智能体系统_开发总结报告.docx、codex/AI模型任务队列.md | L-001 至 L-006 已完成；JSON、README 命令检查通过；`compileall` 通过；`pytest -q backend`（15 passed）。DOCX 已结构更新，渲染因环境缺少 LibreOffice/soffice 未完成。 |
| 2026-07-10 | TERRA-REVIEW（旧混元表述） | Terra | backend/__init__.py、backend/main.py、backend/config.py、backend/database.py、backend/errors.py、backend/models/schemas.py、backend/protocols/、backend/services/、backend/routers/、backend/evaluation/、backend/tests/、codex/AI模型任务队列.md | T-001 至 T-012 已完成；`python -m compileall -q backend`、`python -m pytest -q backend`（15 passed）和应用导入检查通过。真实混元 API 分片联调保留为 INBOX-002。 |
| 2026-07-10 | SOL-REVIEW | Sol | codex/architecture/README.md、codex/architecture/Sol任务完成复审报告.md | Sol 任务 7/7 完成，验收 7/7 通过，相关 Terra/Luna 依赖已解除 |
| 2026-07-10 | S-007 | Sol | codex/architecture/S-007-Electron后端启动与数据目录架构.md | 进程、端口认证、IPC、userData、密钥、升级与打包方案齐全 |
| 2026-07-10 | S-005 | Sol | codex/architecture/S-005-模型效果评测方案.md | 测试集、评分、硬门槛、分层回归和发布标准齐全 |
| 2026-07-10 | S-006 | Sol | codex/architecture/S-006-提示词注入与隐私边界.md | 信任边界、会话隔离、渲染、密钥和注入测试齐全 |
| 2026-07-10 | S-003 | Sol | codex/architecture/S-003-真实SSE流式编排与取消机制.md | 事件协议、真实分片、断开取消、持久化与幂等方案齐全 |
| 2026-07-10 | S-004 | Sol | codex/architecture/S-004-模型错误语义与降级策略.md | 异常层次、HTTP/SSE 映射、重试、日志和健康检查齐全 |
| 2026-07-10 | S-001 | Sol | codex/architecture/S-001-多轮诊断状态机与Agent边界.md | 状态、边界、转换、不变量和 Terra 实现清单齐全 |
| 2026-07-10 | S-002 | Sol | codex/architecture/S-002-版本化纯文本协议规范.md | 三类协议、解析、校验、修复和版本策略齐全 |
| 2026-07-10 | QUEUE-INIT | Sol | AGENTS.md、codex/AI模型任务队列.md | 完成业务代码盘点、Python 编译、应用导入和根接口 200 验证 |
