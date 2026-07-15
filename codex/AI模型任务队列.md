# A3 模型任务队列

> 项目：基于大模型的个性化资源生成与学习多智能体系统开发
> 队列位置：E:\软件杯\codex\AI模型任务队列.md
> 当前模型批次：Terra（T-029 已完成，等待新增任务）
> 最后审视日期：2026-07-14

## 一、使用规则

1. 本文件是软件杯项目任务状态的单一真实来源，新对话开始时先读取本文件。
2. 新任务先登记到“收件箱”，再标注目标模型、优先级、依赖和验收结果。
3. 当前模型只批量执行属于该模型且状态为“就绪”的任务。
4. 不属于当前模型的任务先保留，不要求立即切换；当前批次做完或被依赖阻塞时，再提醒用户切换。
5. 模型切换由用户手动完成。切换后更新“当前模型批次”，并继续该模型优先级最高的就绪任务。
6. 完成任务后必须填写修改文件、验证命令和结果，再把状态改为“完成”。
7. 若任务依赖前置设计，状态设为“阻塞”，不得绕过依赖直接实现。

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

Sol 批次已完成 S-008、S-009、S-010、S-011、S-014 和 S-015：生产安全边界、学习闭环、自适应建议、资源质量门槛、Electron IPC 契约、安装版安全模型配置闭环及项目 Git 安全基线均已落地。INBOX-001 继续保留 `backend/competition`，用于测试、评测和重新打包复现，但该目录不会进入 Git。

Terra 批次已完成 T-024、T-025 和 T-029：流式生成取消已绑定原始会话，高成本接口在桌面令牌保护模式下执行按客户端滑动窗口限流，诊断历史按首条学习目标、最近消息和字符上限裁剪；T-029 已统一 FastAPI、Web 与 Electron 错误响应契约并完成全量回归。当前没有新的 Terra 就绪任务。INBOX-002 当前使用 DeepSeek OpenAI 兼容配置与 deepseek-v4-pro；旧混元和 OpenAI Terra 联调记录仅供历史追溯。

Luna 批次已完成并通过复审。README、API 示例、协议说明、评测样例和开发总结已同步当前代码。L-007、L-008、L-009 已完成：快捷测试入口和浏览器测试台均已通过自动化测试、浏览器检查及打包启动自检；竞品对照和后端优化方案已形成。S-009 已就绪，等待切换 Sol 后实施跨模块学习闭环代码。

INBOX-002 已联调：后端已支持用户自定义 OpenAI 兼容或 Anthropic 网关。DeepSeek OpenAI 兼容路径已完成真实普通调用、SSE 分片与协议联调；后续可转入前端或 Electron 集成阶段。

前端续作已完成：L-010 的临时清单已用于完成 T-026/T-027，并按约定删除；前端的长期交付状态与验证结果见本队列完成记录。仅在用户确认需要桌面安装包时，才解除 T-028。

Terra 前端批次已完成 T-026 与 T-027：真实模型驱动的诊断、画像、资源、答题、复习与六页响应式界面均已验收；前端新增流式错误恢复和 Vitest 回归。Element Plus 改为按需引入后，主 JavaScript 从 1,099.07 kB（gzip 365.04 kB）降至 309.13 kB（gzip 114.46 kB），主样式从 365.09 kB（gzip 49.96 kB）降至 59.72 kB（gzip 9.42 kB），已消除大包告警。用户已确认需要 Electron 桌面端，并指定 openhanako 为参考；T-028 已解除阻塞并进入实现。

T-028 已完成：Electron 主进程统一代理普通 HTTP/SSE 并独占动态后端地址和短期 token；preload 只暴露固定请求、流、取消和后端退出桥接；renderer 不接触 token。S-012 定位到退出残留的根因是 `closed` 回调读取已销毁 `BrowserWindow.webContents`，触发 `Object has been destroyed` 并中断退出；改为窗口创建时缓存 `webContents` 后，开发版和 unpacked 版测试模式均退出码 0 且无残留。完整 Node 49 项、Vitest 14 项、Web/桌面构建、unpacked、NSIS 与渲染器密钥扫描全部通过。发布包仍使用默认 Electron 图标且未配置代码签名/作者元数据，列为后续品牌与正式发行优化，不阻塞当前功能交付。

S-013 已完成：前端实际使用的 13 组 HTTP/SSE 路径与 FastAPI 路由、Electron 白名单一致，后端快捷测试 80 项、Electron Node 49 项及 Vitest 14 项通过。专项复核同时确认两项交付缺口：全新安装版无模型密钥时 `/health/ready` 返回 503，而前端与 Electron 未开放配置保存/连通性测试，生产后端也禁止明文 `.env` 落盘；FastAPI 的 `detail` 错误与业务 `{code,message}` 错误在 Web/Electron 的解析不一致。前者登记 S-014，后者登记 T-029。

S-014 已完成：安装版首次无配置自动进入模型设置；测试成功后才可保存，主进程使用 Electron `safeStorage` 加密持久化并以环境变量注入后端，ready 失败恢复旧密文和旧后端；renderer 不接触桌面令牌、持久化密钥或配置路径。桌面与窄屏视觉已按 openhanako 参考验收，账号体系和桌宠仅保留模块化扩展边界。最终回归为后端 80 项、Electron Node 66 项、Vitest 23 项；Web/desktop/unpacked/NSIS 全部通过。当前 Sol 批次完成，下一项 T-029 属于 Terra。

S-015 已完成：`E:\软件杯` 已初始化为本地 `main` 单仓库，根级 `.gitignore` 排除真实 `.env`、密钥文件、数据库、虚拟环境、依赖、构建/安装产物、桌面后端和临时 `.superpowers` 目录；`.gitattributes` 固定源码 LF、Windows 脚本 CRLF 和二进制文件属性。首个基线提交已创建，未连接远程仓库，也未写入永久 Git 身份配置。当前 Sol 批次完成，下一项仍为 Terra 的 T-029。

S-016 已完成：本仓库提交身份已设置为 `Wei kb <212667660@qq.com>`；私有远程 `origin` 指向 `https://github.com/212667660-arch/a3-learning-agents.git`，本地 `main` 已建立 `origin/main` 上游并完成首次推送。GitHub 页面已显示两条基线提交；完成记录提交后再次推送并核对本地、上游与远程哈希一致。当前 Sol 批次完成，下一项仍为 Terra 的 T-029。

## 九、任务完成记录

| 日期 | 任务 ID | 模型 | 修改文件 | 验证结果 |
| --- | --- | --- | --- | --- |
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
