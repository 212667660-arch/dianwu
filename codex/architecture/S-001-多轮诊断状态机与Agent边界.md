# S-001 多轮诊断状态机与 Agent 边界

## 1. 目标

将当前“首条消息立即生成画像”的流程改为可解释、可恢复的多轮诊断。协调层负责状态和路由，Agent 只完成单一职责，任何 Agent 都不能自行改变会话状态或直接写数据库。

## 2. 当前问题

- 首条用户消息会直接生成画像，缺少简短追问和诊断证据。
- diagnosed 布尔值无法表达诊断中、生成中、失败和待重试等状态。
- 画像 Agent 同时承担总结、补弱点和推断风格，边界不清晰。
- 路由层直接编排数据库与 Agent，后续增加取消、重试和流式事件会变得脆弱。

## 3. 会话状态

| 状态 | 含义 | 允许的下一状态 |
| --- | --- | --- |
| NEW | 新会话，尚无有效诊断信息 | DIAGNOSING |
| DIAGNOSING | 正在收集学习者信息并决定是否追问 | DIAGNOSING、PROFILE_READY、FAILED |
| PROFILE_READY | 信息充分，等待生成画像 | PROFILED、FAILED |
| PROFILED | 画像已验证，可生成学习资源 | GENERATING、DIAGNOSING、FAILED |
| GENERATING | 正在生成学习资源 | PROFILED、FAILED |
| FAILED | 最近一步失败，保留可恢复上下文 | 失败前稳定状态、DIAGNOSING |

数据库中保存稳定状态，不保存短暂的网络分片状态。GENERATING 只在任务执行期间写入，任务完成或失败后必须离开该状态。

## 4. 诊断完成条件

诊断 Agent 不以固定轮数决定结束，而是同时满足以下条件：

- 已明确学科或学习主题。
- 已明确学习目标。
- 至少获得一条当前水平或薄弱点证据。
- 已获得学习偏好证据，或明确标记为未观察到。
- 关键字段置信度达到 0.65。

保护规则：

- 最少追问 1 轮，避免仅凭一句话过度推断。
- 最多追问 5 轮，超过后使用已知信息生成低置信度画像。
- 每轮只问一个最能减少不确定性的问题。
- 用户明确要求跳过诊断时，可以提前生成画像，但必须标记低置信度和待确认字段。

## 5. Agent 职责

### Coordinator

- 读取会话状态、消息历史和已保存画像。
- 根据状态选择诊断、画像或资源 Agent。
- 校验 Agent 输出协议并决定状态转换。
- 负责数据库事务、重试次数、取消和事件发布。
- 不生成教学内容，不自行推断画像字段。

### Diagnosis Agent

- 输入：最近有效对话、已收集字段和轮数。
- 输出：诊断决策协议，状态只能是 CONTINUE 或 COMPLETE。
- CONTINUE 时仅给出一个下一问题。
- COMPLETE 时给出字段证据、缺失字段和完成理由。
- 不生成最终画像，不调用资源 Agent。

### Profile Agent

- 仅在状态为 PROFILE_READY 时运行。
- 根据对话证据生成 learner-profile/v1 协议。
- 不负责追问，不直接写数据库。
- 输出必须经过协议校验器，失败时最多修复一次。

### Resource Agent

- 仅接受已验证的 learner-profile/v1 和用户资源请求。
- 输出 learning-resource/v1 协议。
- 不修改画像，不重新诊断用户。

### Protocol Validator

- 负责解析、字段校验、版本检查和错误定位。
- 返回结构化内部对象或明确异常。
- 不调用模型；协议修复由 Coordinator 决定是否触发。

## 6. 状态转换

| 当前状态 | 事件 | 动作 | 下一状态 |
| --- | --- | --- | --- |
| NEW | 用户发言 | 保存消息，调用 Diagnosis Agent | DIAGNOSING |
| DIAGNOSING | CONTINUE | 保存诊断快照，返回下一问题 | DIAGNOSING |
| DIAGNOSING | COMPLETE | 保存诊断证据 | PROFILE_READY |
| PROFILE_READY | 画像验证成功 | 保存画像与版本 | PROFILED |
| PROFILE_READY | 画像验证失败 | 修复一次，仍失败则记录错误 | FAILED |
| PROFILED | 用户请求学习资源 | 创建生成任务 | GENERATING |
| GENERATING | 资源验证成功 | 保存资源并返回 | PROFILED |
| GENERATING | 模型、协议或持久化失败 | 记录失败阶段 | FAILED |
| 任意稳定状态 | 重新诊断 | 保留旧画像快照，开启新诊断版本 | DIAGNOSING |
| FAILED | 用户重试 | 从 last_stable_state 恢复 | 失败前稳定状态 |

## 7. 数据模型调整建议

ChatSession 增加：

- state：NEW、DIAGNOSING、PROFILE_READY、PROFILED、GENERATING、FAILED。
- diagnosis_turns：已完成的诊断追问轮数。
- profile_version：当前画像版本号。
- last_stable_state：失败前的稳定状态。
- last_error_code：最近错误代码，不保存敏感异常全文。

新增 DiagnosisSnapshot：

- session_id、turn、decision_text、missing_fields、confidence、created_at。

Resource 增加：

- protocol_version、profile_version、status、error_code。

## 8. API 行为

POST /api/chat：

- NEW 或 DIAGNOSING：返回下一诊断问题或最终画像。
- PROFILED：把普通学习请求交给资源 Agent。
- GENERATING：返回任务正在执行，避免同会话重复生成。
- FAILED：返回可重试错误和恢复动作。

POST /api/chat/stream：

- 先发 phase 事件说明 diagnosis、profile 或 resource。
- 诊断追问可一次性发送；画像与资源生成使用真实模型分片。
- 结束前必须发送 validated 事件，再发送 done。

保留 /api/profile 和 /api/resource 作为调试接口，但默认产品流程只使用 /api/chat 和 /api/chat/stream。

## 9. 不变量

- 未验证的画像不能保存为当前有效画像。
- 资源必须记录所使用的 profile_version。
- 同一 session 同时最多有一个 GENERATING 任务。
- Agent 不能直接提交数据库事务。
- 失败不能覆盖最后一个有效画像或已完成资源。
- 重新诊断必须创建新画像版本，不原地破坏旧版本。

## 10. Terra 实现清单

- 用枚举替换 diagnosed 布尔状态，保留兼容迁移。
- 新建 orchestrator 服务，路由只负责协议适配。
- 新建 DiagnosisSnapshot 模型和仓储函数。
- 实现状态转换校验，非法转换抛出 DomainStateError。
- 为每条状态转换编写单元测试。
- 增加同会话重复生成和失败恢复测试。

## 11. 验收标准

- 新用户至少经过一次追问后才生成画像。
- 五轮内必定结束诊断或给出低置信度画像。
- 每个状态都有明确输入、输出和失败去向。
- 画像和资源 Agent 无数据库写入权限。
- 重新诊断、生成失败和用户重试不会丢失最后有效数据。
