# A3 Multi-API Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不泄露模型密钥、不破坏现有学习流程的前提下，实现多 API 加密配置、热切换、受控故障转移、模型选择和推理强度控制。

**Architecture:** Electron 负责版本化 `safeStorage` 配置保险库和受信配置事务；FastAPI 后端使用原子 `RuntimeSnapshot`、独立客户端池、熔断器和能力适配器执行模型请求；Vue 只读取脱敏元数据，并保存全局默认与学习空间覆盖。旧单配置接口保留兼容，直到新链路完整验收。

**Tech Stack:** Electron 32、Node.js `node:test`、Vue 3、Pinia、Vitest、FastAPI、Pydantic 2、httpx/OpenAI SDK、SQLAlchemy、SQLite、PyInstaller。

---

## 文件职责

### 后端新增

- `backend/services/model_capabilities.py`：标准推理档位、能力声明与供应商参数映射。
- `backend/services/model_resilience.py`：错误分类、总尝试预算、退避和熔断状态机。
- `backend/services/model_runtime.py`：不可变运行快照、配置选择、客户端生命周期和普通/流式路由。
- `backend/routers/model_runtime.py`：仅 Electron 主进程可用的 bootstrap/test/snapshot/status 接口。
- `backend/routers/model_preferences.py`：学习空间模型偏好读写接口。
- `backend/tests/fake_model_gateway.py`：可脚本化的无网络假网关。
- `backend/tests/test_model_capabilities.py`
- `backend/tests/test_model_resilience.py`
- `backend/tests/test_model_runtime.py`
- `backend/tests/test_model_runtime_routes.py`
- `backend/tests/test_model_preferences.py`

### Electron 新增

- `a3-front/a3-front/electron/model-profile-vault.mjs`：版本 2 保险库、版本 1 迁移、原子密文保存。
- `a3-front/a3-front/electron/model-profile-vault.test.mjs`
- `a3-front/a3-front/electron/model-profile-controller.mjs`：候选测试、保存、应用和回滚事务。
- `a3-front/a3-front/electron/model-profile-controller.test.mjs`

### 前端新增

- `a3-front/a3-front/src/components/model/ModelProfileList.vue`
- `a3-front/a3-front/src/components/model/ModelProfileEditor.vue`
- `a3-front/a3-front/src/components/model/ModelSelectionPopover.vue`
- 对应三个 `.test.ts` 文件。

现有 `model-config.*` 在迁移期保留，只承担版本 1 解密和兼容入口；新代码不得复制一份旧密钥存储逻辑。

---

### Task 1: 定义多配置与模型能力契约

**Files:**
- Create: `backend/services/model_capabilities.py`
- Modify: `backend/models/schemas.py`
- Create: `backend/tests/test_model_capabilities.py`

- [ ] **Step 1: 写推理档位与适配器失败测试**

```python
from backend.services.model_capabilities import effective_effort, reasoning_payload


def test_reasoning_effort_uses_nearest_supported_lower_level() -> None:
    assert effective_effort("xhigh", ["off", "low", "medium", "high"]) == "high"
    assert effective_effort("auto", ["off", "medium", "high"]) == "auto"


def test_openai_adapter_emits_only_whitelisted_reasoning_field() -> None:
    assert reasoning_payload("openai_reasoning_effort", "high") == {"reasoning_effort": "high"}
    assert reasoning_payload("none", "high") == {}
```

- [ ] **Step 2: 运行测试并确认因模块缺失失败**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_capabilities.py`

Expected: FAIL，包含 `ModuleNotFoundError: backend.services.model_capabilities`。

- [ ] **Step 3: 实现白名单能力映射**

```python
from __future__ import annotations

from typing import Literal

ReasoningEffort = Literal["auto", "off", "low", "medium", "high", "xhigh"]
ReasoningAdapter = Literal["none", "openai_reasoning_effort", "anthropic_thinking"]

_ORDER = ("off", "low", "medium", "high", "xhigh")


def effective_effort(requested: ReasoningEffort, supported: list[ReasoningEffort]) -> ReasoningEffort:
    if requested == "auto":
        return "auto"
    if requested in supported:
        return requested
    requested_index = _ORDER.index(requested)
    candidates = [value for value in supported if value in _ORDER and _ORDER.index(value) < requested_index]
    return candidates[-1] if candidates else "off"


def reasoning_payload(adapter: ReasoningAdapter, effort: ReasoningEffort) -> dict[str, object]:
    if adapter == "none" or effort in {"auto", "off"}:
        return {}
    if adapter == "openai_reasoning_effort":
        return {"reasoning_effort": effort}
    budgets = {"low": 1024, "medium": 4096, "high": 8192, "xhigh": 16384}
    return {"thinking": {"type": "enabled", "budget_tokens": budgets[effort]}}
```

同时在 `backend/models/schemas.py` 定义并严格禁止额外字段：

```python
class ModelDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    provider_model_name: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    max_output_tokens: int = Field(default=4096, ge=512, le=32768)
    supported_reasoning_efforts: list[Literal["auto", "off", "low", "medium", "high", "xhigh"]]
    reasoning_adapter: Literal["none", "openai_reasoning_effort", "anthropic_thinking"]


class ModelProfileSecret(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    label: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    provider: Literal["openai", "anthropic"]
    base_url: str = Field(min_length=8, max_length=512)
    api_key: str = Field(min_length=1, max_length=512, repr=False)
    anthropic_version: str = Field(default="2023-06-01", min_length=1, max_length=32)
    request_timeout_seconds: float = Field(default=60, ge=5, le=300)
    default_model_id: str = Field(min_length=1, max_length=128)
    models: list[ModelDefinition] = Field(min_length=1, max_length=64)


class ModelRuntimeSnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_profile_id: str | None = Field(default=None, min_length=1, max_length=64)
    auto_failover: bool = True
    fallback_profile_ids: list[str] = Field(max_length=16)
    profiles: list[ModelProfileSecret] = Field(max_length=16)
```

- [ ] **Step 4: 增加重复 ID、默认模型不存在和任意适配器字段拒绝测试**

在 `test_model_capabilities.py` 使用 `pytest.raises(ValidationError)` 验证 `extra="forbid"`；拒绝 `provider_model_name` 中的 NUL/CR/LF；要求每个模型的档位包含 `auto`。为快照增加 `model_validator`，要求配置 ID 唯一、模型 ID 在单配置内唯一、默认配置启用、默认模型存在、备用 ID 均存在且不重复。另测全新安装的空快照合法且 ready=false；只要 profiles 非空就必须有默认配置。

- [ ] **Step 5: 运行测试**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_capabilities.py backend/tests/test_model_settings.py`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add backend/services/model_capabilities.py backend/models/schemas.py backend/tests/test_model_capabilities.py
git commit -m "feat: define model profile capabilities"
```

---

### Task 2: 实现错误分类与熔断器

**Files:**
- Create: `backend/services/model_resilience.py`
- Create: `backend/tests/test_model_resilience.py`
- Modify: `backend/errors.py`

- [ ] **Step 1: 写假时钟熔断测试**

```python
from backend.services.model_resilience import CircuitBreaker, RetryClass


def test_breaker_opens_after_three_retryable_failures_and_half_opens_once() -> None:
    now = [100.0]
    breaker = CircuitBreaker(clock=lambda: now[0])
    for _ in range(3):
        breaker.record_failure(RetryClass.RETRYABLE)
    assert breaker.state == "open"
    assert breaker.allow_request() is False
    now[0] += 31
    assert breaker.allow_request() is True
    assert breaker.allow_request() is False
    breaker.record_success()
    assert breaker.state == "closed"
```

- [ ] **Step 2: 写错误分类与尝试预算测试**

验证网络、超时、408/429/502/503/504 为 `RETRYABLE`；400/401/403/404/422 为 `TERMINAL`；总预算默认 `max_attempts=3`、`max_profiles=2`，截止时间耗尽时拒绝下一次尝试。

- [ ] **Step 3: 运行测试并确认失败**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_resilience.py`

Expected: FAIL，模块尚不存在。

- [ ] **Step 4: 实现状态机与预算**

`model_resilience.py` 必须公开：

```python
class RetryClass(StrEnum):
    RETRYABLE = "retryable"
    TERMINAL = "terminal"


@dataclass
class AttemptBudget:
    deadline: float
    max_attempts: int = 3
    max_profiles: int = 2
    attempts: int = 0
    profile_ids: set[str] = field(default_factory=set)

    def consume(self, profile_id: str, now: float) -> bool:
        if now >= self.deadline or self.attempts >= self.max_attempts:
            return False
        if profile_id not in self.profile_ids and len(self.profile_ids) >= self.max_profiles:
            return False
        self.attempts += 1
        self.profile_ids.add(profile_id)
        return True
```

`CircuitBreaker` 使用连续失败阈值 3，冷却序列 30/60/120/240/300 秒，half-open 只允许一个请求。终止类错误不增加普通熔断计数；401/403 由调用者标记 `needs_attention`。

- [ ] **Step 5: 在 `backend/errors.py` 增加规范中的 7 个稳定错误类**

每个类继承 `AppError`，使用固定 code、中文公开消息、正确 HTTP 状态；`MODEL_FAILOVER_EXHAUSTED` 和 `MODEL_STREAM_INTERRUPTED` 标记 `retryable=True`，配置校验与能力错误标记 `False`。

- [ ] **Step 6: 运行测试**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_resilience.py backend/tests/test_errors_and_sessions.py`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add backend/services/model_resilience.py backend/errors.py backend/tests/test_model_resilience.py
git commit -m "feat: add model retry and circuit breaker policy"
```

---

### Task 3: 让模型网关支持显式模型和推理参数

**Files:**
- Modify: `backend/services/llm_service.py`
- Modify: `backend/tests/test_llm_gateway.py`

- [ ] **Step 1: 写 OpenAI 与 Anthropic payload 失败测试**

```python
def test_gateway_payload_uses_selected_model_and_reasoning_without_mutating_messages() -> None:
    gateway = configured_gateway()
    messages = [{"role": "user", "content": "hello"}]
    payload = gateway._openai_payload(messages, 0.2, "reasoning-model", {"reasoning_effort": "high"})
    assert payload["model"] == "reasoning-model"
    assert payload["reasoning_effort"] == "high"
    assert messages == [{"role": "user", "content": "hello"}]
```

Anthropic 测试断言 `thinking` 位于请求顶层、显式 thinking 时不发送 `temperature`，并且 `max_tokens > budget_tokens`；普通 `none` 适配器不发送任何推理字段。OpenAI 显式 `reasoning_effort` 时不发送 `temperature`，避免已知推理模型拒绝该参数。

- [ ] **Step 2: 运行测试并确认签名不匹配失败**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_llm_gateway.py`

Expected: FAIL，`_openai_payload()` 不接受模型与推理参数。

- [ ] **Step 3: 扩展网关公开签名**

```python
async def complete(
    self,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    *,
    model_name: str | None = None,
    reasoning: dict[str, object] | None = None,
    max_output_tokens: int = 4096,
) -> str:
    selected_model = model_name or self.settings.resolved_model_name
    selected_reasoning = reasoning or {}
    if self.settings.resolved_provider == "anthropic":
        return await self._complete_anthropic(messages, temperature, selected_model, selected_reasoning, max_output_tokens)
    if self.settings.resolved_provider == "openai":
        return await self._complete_openai(messages, temperature, selected_model, selected_reasoning)
    raise ConfigurationError("MODEL_PROVIDER 仅支持 openai 或 anthropic。")


async def stream(
    self,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    *,
    model_name: str | None = None,
    reasoning: dict[str, object] | None = None,
    max_output_tokens: int = 4096,
) -> AsyncIterator[str]:
    selected_model = model_name or self.settings.resolved_model_name
    selected_reasoning = reasoning or {}
    if self.settings.resolved_provider == "anthropic":
        async for delta in self._stream_anthropic(messages, temperature, selected_model, selected_reasoning, max_output_tokens):
            yield delta
        return
    if self.settings.resolved_provider == "openai":
        async for delta in self._stream_openai(messages, temperature, selected_model, selected_reasoning):
            yield delta
        return
    raise ConfigurationError("MODEL_PROVIDER 仅支持 openai 或 anthropic。")
```

实现中使用 `selected_model = model_name or self.settings.resolved_model_name`；`reasoning` 只允许调用 `model_capabilities.reasoning_payload()` 产生的顶层白名单键。构造请求 kwargs 时，如果存在 `reasoning_effort` 或 `thinking` 就省略 `temperature`；Anthropic thinking 使用 `max(max_output_tokens, budget_tokens + 2048)`。构造 OpenAI 客户端时显式 `max_retries=0`，避免与路由器预算相乘；保留 `trust_env=False` 和 60 秒现有默认超时。

- [ ] **Step 4: 增加客户端签名测试**

断言同配置重复调用复用同一客户端；关闭后签名清空；不同 base URL、Key 或超时创建新客户端；测试输出和异常不包含 Key。

- [ ] **Step 5: 运行测试**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_llm_gateway.py`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add backend/services/llm_service.py backend/tests/test_llm_gateway.py
git commit -m "feat: support selected models and reasoning payloads"
```

---

### Task 4: 实现原子运行快照与普通请求故障转移

**Files:**
- Create: `backend/services/model_runtime.py`
- Create: `backend/tests/fake_model_gateway.py`
- Create: `backend/tests/test_model_runtime.py`
- Modify: `backend/services/orchestrator.py`
- Modify: `backend/services/profile_agent.py`
- Modify: `backend/services/resource_agent.py`
- Modify: `backend/tests/test_protocols.py`
- Modify: `backend/tests/test_resource_quality.py`

- [ ] **Step 1: 创建脚本化假网关**

`fake_model_gateway.py` 提供 `ScriptedGateway`，构造参数为普通响应队列和流事件队列；记录每次 `model_name`、`reasoning`、`messages`；异常对象从队列抛出；`aclose()` 设置 `closed=True`。测试不得访问网络。

- [ ] **Step 2: 写候选顺序、终止错误和备用成功测试**

```python
async def test_retryable_primary_failure_uses_backup_once() -> None:
    router, primary, backup = runtime_with_scripts(
        primary=[ModelTimeoutError()],
        backup=["OK"],
    )
    result = await router.complete(selection=auto_selection(), messages=user_messages())
    assert result.text == "OK"
    assert result.profile_id == "backup"
    assert result.failover_used is True
    assert len(primary.calls) == 1
    assert len(backup.calls) == 1


async def test_authentication_error_does_not_use_backup() -> None:
    router, primary, backup = runtime_with_scripts(
        primary=[ModelAuthenticationError()],
        backup=["must-not-run"],
    )
    with pytest.raises(ModelAuthenticationError):
        await router.complete(selection=auto_selection(), messages=user_messages())
    assert backup.calls == []
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_runtime.py`

Expected: FAIL，runtime 模块不存在。

- [ ] **Step 4: 实现运行路由器**

`ModelRuntimeRouter` 必须提供以下精确公开方法：`apply_snapshot(value: ModelRuntimeSnapshotInput) -> RuntimeStatus`、`test_profile(profile: ModelProfileSecret) -> ModelConnectionTestResponse`、`complete(selection: RuntimeSelection, messages: list[dict[str, str]], temperature: float) -> RoutedCompletion`、`stream(selection: RuntimeSelection, messages: list[dict[str, str]], temperature: float) -> AsyncIterator[RoutedStreamEvent]`、`close() -> None` 和同步 `status() -> RuntimeStatus`。

实现要求：候选快照完整构造后再交换；请求获取快照租约；按 Task 2 预算选择候选；返回实际 profile/model/reasoning；旧快照租约归零后关闭客户端；状态日志只使用 profile ID 和安全错误码。

- [ ] **Step 5: 增加快照更新不关闭活动客户端测试**

使用 `asyncio.Event` 暂停旧网关响应，应用新快照后断言旧网关未关闭；释放事件并等待旧请求结束后断言旧网关关闭，新请求使用新网关。

- [ ] **Step 6: 移除三个模块级网关并注入同一选择闭包**

`orchestrator.py` 从仓储读取一次 `RuntimeSelection`，构造以下闭包并传给 profile/resource Agent，保证首次生成和协议修复使用同一学习空间策略：

```python
async def selected_complete(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    result = await model_runtime_router.complete(selection, messages, temperature)
    return result.text
```

`profile_agent.generate_diagnosis_decision()`、`profile_agent.generate_profile()` 和 `resource_agent.generate_resources()` 增加必需的 `complete` callable 参数；各自 `_repair()` 使用同一个 callable。删除两文件中的 `_gateway` 与 `close_runtime()`，`orchestrator.close_runtime()` 只关闭 `model_runtime_router`。同步更新协议和资源质量测试，显式传入假 complete callable；禁止保留第二套全局 `ModelGateway`。

- [ ] **Step 7: 运行聚焦测试**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_runtime.py backend/tests/test_orchestrator.py backend/tests/test_runtime_cleanup.py`

Expected: PASS。

- [ ] **Step 8: 提交**

```powershell
git add backend/services/model_runtime.py backend/services/orchestrator.py backend/services/profile_agent.py backend/services/resource_agent.py backend/tests/fake_model_gateway.py backend/tests/test_model_runtime.py backend/tests/test_orchestrator.py backend/tests/test_runtime_cleanup.py backend/tests/test_protocols.py backend/tests/test_resource_quality.py
git commit -m "feat: add atomic model runtime router"
```

---

### Task 5: 实现流式故障边界和中断事件

**Files:**
- Modify: `backend/services/model_runtime.py`
- Modify: `backend/services/orchestrator.py`
- Modify: `backend/models/schemas.py`
- Modify: `backend/tests/test_model_runtime.py`
- Modify: `backend/tests/test_streaming.py`

- [ ] **Step 1: 写零输出自动切换测试**

主配置流在第一个 delta 前抛出 `ModelUnavailableError`，备用配置输出 `A`、`B`；断言路由器只产出一个 `meta`（实际备用配置）和 `delta A/B`，不产出中断事件。

- [ ] **Step 2: 写已输出后禁止静默切换测试**

主配置先输出 `partial` 再抛出连接错误；断言备用网关未调用，路由器输出：

```python
[
    {"event": "meta", "profile_id": "primary", "model_id": "model-a"},
    {"event": "delta", "content": "partial"},
    {"event": "interrupted", "code": "MODEL_STREAM_INTERRUPTED", "can_continue_with_backup": True},
]
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_runtime.py -k stream`

Expected: FAIL，当前流没有路由事件和中断语义。

- [ ] **Step 4: 实现 `RoutedStreamEvent` 与 emitted 标记**

路由器在读取任何上游 delta 前可重试/切换；第一次 delta 后将 `emitted=True`，后续可重试异常转换为一次 `interrupted` 并结束。取消异常始终直接传播，不进入备用链路。

- [ ] **Step 5: 在 orchestrator SSE 中转发 `meta` 和 `interrupted`**

`meta` 至少包含 `profile_id`、`model_id`、`requested_reasoning_effort`、`effective_reasoning_effort`、`failover_used`；`interrupted` 保留已发文本，不调用 `replace`，最终 `done.status="interrupted"`。

- [ ] **Step 6: 运行流式回归**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_runtime.py backend/tests/test_streaming.py`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add backend/services/model_runtime.py backend/services/orchestrator.py backend/models/schemas.py backend/tests/test_model_runtime.py backend/tests/test_streaming.py
git commit -m "feat: enforce safe streaming failover boundaries"
```

---

### Task 6: 增加内部运行时接口和 ready 语义

**Files:**
- Create: `backend/routers/model_runtime.py`
- Create: `backend/tests/test_model_runtime_routes.py`
- Modify: `backend/main.py`
- Modify: `backend/services/security.py`
- Modify: `backend/tests/test_security.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: 写内部接口鉴权失败测试**

验证 `/internal/model-runtime/*` 在无令牌、错误令牌、非 loopback、额外字段和超过大小限制时返回统一 4xx 错误；任何响应正文不得包含测试 Key。

- [ ] **Step 2: 写 bootstrap 与原子 apply 测试**

使用假 router：空快照 bootstrap 后 `/health/ready` 为 503；有效快照 bootstrap 后为 200；应用候选快照失败时旧 status 保持 active，接口返回 `MODEL_RUNTIME_APPLY_FAILED`。另测非桌面 development 启动时，现有 `backend/.env` 单配置会在 lifespan 中转换成一个 legacy 内存快照；production 不允许从 `.env` 自动 bootstrap。

- [ ] **Step 3: 运行测试并确认 404 失败**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_runtime_routes.py`

Expected: FAIL，内部路由不存在。

- [ ] **Step 4: 实现固定接口**

```python
router = APIRouter(prefix="/internal/model-runtime", include_in_schema=False)

@router.post("/bootstrap")
async def bootstrap(snapshot: ModelRuntimeSnapshotInput) -> RuntimeStatusResponse:
    return RuntimeStatusResponse.model_validate(await model_runtime_router.apply_snapshot(snapshot))

@router.post("/test")
async def test_profile(profile: ModelProfileSecret) -> ModelConnectionTestResponse:
    return await model_runtime_router.test_profile(profile)

@router.put("/snapshot")
async def apply_snapshot(snapshot: ModelRuntimeSnapshotInput) -> RuntimeStatusResponse:
    return RuntimeStatusResponse.model_validate(await model_runtime_router.apply_snapshot(snapshot))

@router.get("/status")
async def runtime_status() -> RuntimeStatusResponse:
    return RuntimeStatusResponse.model_validate(model_runtime_router.status())
```

所有接口复用桌面令牌中间件且只允许 loopback；中间件对 `/internal/model-runtime` 设置 128 KiB 请求体上限。`/health/ready` 改为检查 `model_runtime_router.is_ready`，不再直接读取环境中的单配置 Key。lifespan 仅在 `APP_ENV=development` 且没有桌面令牌时把当前 Settings 转为 ID 为 `legacy-development` 的单配置内存快照，确保 Web 开发模式兼容；production 必须等待 Electron bootstrap。

- [ ] **Step 5: 阻止 renderer 代理 `/internal/*`**

不向 Electron `ALLOWED_ROUTES` 增加任何 internal 路径，并在 `backend-proxy.test.mjs` 增加显式拒绝用例。

- [ ] **Step 6: 运行聚焦测试**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_runtime_routes.py backend/tests/test_security.py backend/tests/test_api.py`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add backend/routers/model_runtime.py backend/main.py backend/services/security.py backend/tests/test_model_runtime_routes.py backend/tests/test_security.py backend/tests/test_api.py a3-front/a3-front/electron/backend-proxy.test.mjs
git commit -m "feat: add protected model runtime control plane"
```

---

### Task 7: 持久化学习空间模型偏好

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/services/db.py`
- Create: `backend/routers/model_preferences.py`
- Create: `backend/tests/test_model_preferences.py`
- Modify: `backend/main.py`
- Modify: `backend/models/schemas.py`

- [ ] **Step 1: 写默认继承和覆盖测试**

测试无记录返回 `profile_mode="auto"`、`reasoning_effort="auto"`、`failover_override="inherit"`；PUT 后同 session 返回覆盖；删除 session 时偏好级联删除；非法 profile ID 格式返回 422 统一信封。

- [ ] **Step 2: 运行测试并确认路由缺失**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_preferences.py`

Expected: FAIL。

- [ ] **Step 3: 新增 ORM 与幂等 SQLite 迁移**

在 `backend/services/db.py` 增加 `SessionModelPreference`，`session_id` 为主键和外键；在 `_sqlite_migrate()` 创建缺失表与索引。字段严格使用规范中的枚举字符串，`preferred_profile_id` 和 `model_id` 可空。

- [ ] **Step 4: 实现仓储与接口**

```python
@router.get("/api/sessions/{session_id}/model-preference")
async def get_preference(session_id: SessionIdPath, db: Session = Depends(get_db)) -> SessionModelPreferenceResponse:
    return SessionModelPreferenceResponse.model_validate(repo.get_model_preference(db, session_id))

@router.put("/api/sessions/{session_id}/model-preference")
async def put_preference(session_id: SessionIdPath, update: SessionModelPreferenceUpdate, db: Session = Depends(get_db)) -> SessionModelPreferenceResponse:
    return SessionModelPreferenceResponse.model_validate(repo.upsert_model_preference(db, session_id, update))
```

偏好接口不校验 profile 是否当前存在；运行时负责失效回退，从而允许停用配置后仍保留用户选择历史。

- [ ] **Step 5: 运行测试**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend/tests/test_model_preferences.py backend/tests/test_errors_and_sessions.py`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add backend/database.py backend/services/db.py backend/routers/model_preferences.py backend/models/schemas.py backend/main.py backend/tests/test_model_preferences.py
git commit -m "feat: persist session model preferences"
```

---

### Task 8: 实现 Electron 版本 2 加密保险库

**Files:**
- Create: `a3-front/a3-front/electron/model-profile-vault.mjs`
- Create: `a3-front/a3-front/electron/model-profile-vault.test.mjs`
- Modify: `a3-front/a3-front/electron/model-config.mjs`

- [ ] **Step 1: 写版本 1 迁移测试**

构造当前 `{version:1,payload}` 密文，调用新 vault `load()`；断言返回版本 2、一个 enabled profile、默认 ID 和相同模型配置；读取新密文原始字节时不得出现 Key。

- [ ] **Step 2: 写多配置原子保存和损坏恢复测试**

验证全新安装无文件时返回空版本 2 保险库；保存第一套配置时自动设为默认；保存 3 套配置后可无损读取；写入过程中 rename 失败时旧文件保持可读；无效 base64、重复 ID、未知字段返回 `MODEL_CREDENTIAL_STORE_INVALID`；日志对象不包含输入。

- [ ] **Step 3: 运行 Node 测试并确认模块缺失**

Run: `E:\Node\node.exe --test electron/model-profile-vault.test.mjs`

Expected: FAIL。

- [ ] **Step 4: 实现 `createModelProfileVault`**

公开 `load() / snapshot() / save() / restore()`；复用现有 `safeStorage` 和原子写入；解密后先验证版本与字段，再返回标准对象。迁移只在内存中完成，首次 `save()` 才写版本 2 文件。

配置 ID 使用 `crypto.randomUUID()`；所有适配器和推理档位采用固定 Set 白名单；最多 16 套配置、每套最多 64 个模型。

- [ ] **Step 5: 运行新旧保险库测试**

Run: `E:\Node\node.exe --test electron/model-config.test.mjs electron/model-profile-vault.test.mjs`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add a3-front/a3-front/electron/model-profile-vault.mjs a3-front/a3-front/electron/model-profile-vault.test.mjs a3-front/a3-front/electron/model-config.mjs
git commit -m "feat: add encrypted multi-profile vault"
```

---

### Task 9: 实现 Electron 配置事务与后端热应用

**Files:**
- Create: `a3-front/a3-front/electron/model-profile-controller.mjs`
- Create: `a3-front/a3-front/electron/model-profile-controller.test.mjs`
- Modify: `a3-front/a3-front/electron/main.mjs`
- Modify: `a3-front/a3-front/electron/ipc-contract.mjs`
- Modify: `a3-front/a3-front/electron/ipc-contract.test.mjs`
- Modify: `a3-front/a3-front/electron/preload.cjs`
- Modify: `a3-front/a3-front/electron/runtime.test.mjs`

- [ ] **Step 1: 写启动 bootstrap 测试**

用假 fetch 和 vault 启动主控制器；断言先请求 `/health/live`，再以桌面令牌调用 `/internal/model-runtime/bootstrap`，成功后才允许创建 renderer；请求体包含完整配置但日志回调只收到事件码。

- [ ] **Step 2: 写保存回滚测试**

候选 test 成功、vault save 成功、runtime snapshot apply 失败时，断言恢复 vault 字节并把旧 snapshot 重新应用；返回 `MODEL_RUNTIME_APPLY_FAILED`，不重启 backend，不返回 Key。

- [ ] **Step 3: 写 CRUD 与删除保护测试**

默认配置不能直接删除；删除被学习空间引用的非默认配置允许，后端偏好读取时按 Task 7 规则回退；停用最后一个可用配置被拒绝；排序只接受现有且唯一的 ID。

- [ ] **Step 4: 运行测试并确认失败**

Run: `E:\Node\node.exe --test electron/model-profile-controller.test.mjs electron/ipc-contract.test.mjs`

Expected: FAIL。

- [ ] **Step 5: 实现固定 IPC**

preload 仅暴露以下方法：

```javascript
modelProfilesList: () => ipcRenderer.invoke('a3:model-profiles-list'),
modelProfileTest: input => ipcRenderer.invoke('a3:model-profile-test', input),
modelProfileUpsert: input => ipcRenderer.invoke('a3:model-profile-upsert', input),
modelProfileDelete: id => ipcRenderer.invoke('a3:model-profile-delete', id),
modelProfilePolicySave: input => ipcRenderer.invoke('a3:model-profile-policy-save', input),
modelRuntimeStatus: () => ipcRenderer.invoke('a3:model-runtime-status'),
```

`ipc-contract.mjs` 对每种输入定义独立白名单，不允许 renderer 提交 runtime status、熔断状态、桌面令牌或任意 JSON 适配参数。

- [ ] **Step 6: 修改 `main.mjs` 启动顺序**

启动 backend 时不再注入模型环境变量；等待 live 后由主进程 bootstrap vault 快照；bootstrap 失败显示启动错误或未配置引导。配置保存改为热 apply，不调用 `restartBackendWithConfig`。保留版本 1 controller 兼容测试直到新 UI 完成。

- [ ] **Step 7: 运行 Electron 测试**

Run: `E:\Node\node.exe --test electron/model-profile-controller.test.mjs electron/ipc-contract.test.mjs electron/runtime.test.mjs electron/backend-lifecycle.test.mjs`

Expected: PASS。

- [ ] **Step 8: 提交**

```powershell
git add a3-front/a3-front/electron/model-profile-controller.mjs a3-front/a3-front/electron/model-profile-controller.test.mjs a3-front/a3-front/electron/main.mjs a3-front/a3-front/electron/ipc-contract.mjs a3-front/a3-front/electron/ipc-contract.test.mjs a3-front/a3-front/electron/preload.cjs a3-front/a3-front/electron/runtime.test.mjs
git commit -m "feat: hot-apply encrypted model profiles"
```

---

### Task 10: 扩展前端类型、API 与 Pinia 状态

**Files:**
- Modify: `a3-front/a3-front/src/api/types.ts`
- Modify: `a3-front/a3-front/src/api/backend.ts`
- Modify: `a3-front/a3-front/src/api/backend.test.ts`
- Modify: `a3-front/a3-front/src/stores/backend.ts`
- Modify: `a3-front/a3-front/src/stores/backend.test.ts`
- Modify: `a3-front/a3-front/src/env.d.ts`

- [ ] **Step 1: 写 API 桥接失败测试**

验证 desktop 模式调用固定 `modelProfilesList/modelProfileTest/modelProfileUpsert/modelProfileDelete/modelProfilePolicySave/modelRuntimeStatus`；Web 模式只使用公开脱敏兼容接口，不能尝试 `/internal/*`。

- [ ] **Step 2: 写 store 原子刷新和会话偏好测试**

测试配置列表与 runtime status 使用 `Promise.allSettled`，单个 status 失败不清空已有配置；切换 session 后加载其偏好；保存偏好后立即更新选择器，失败恢复旧值。

- [ ] **Step 3: 运行 Vitest 并确认类型/方法缺失**

Run: `E:\Node\npm.cmd exec vitest run src/api/backend.test.ts src/stores/backend.test.ts`

Expected: FAIL。

- [ ] **Step 4: 定义前端类型**

新增 `ModelProfileSummary`、`ModelProfileInput`、`ModelRuntimeProfileStatus`、`ModelProfilePolicy`、`SessionModelPreference`、`ReasoningEffort`。任何 summary 类型都不得包含 `api_key`，只有编辑 input 包含一次性的可空 `api_key`。

- [ ] **Step 5: 实现 API 和 store actions**

store 提供：`refreshModelProfiles()`、`testModelProfile()`、`upsertModelProfile()`、`deleteModelProfile()`、`saveModelPolicy()`、`loadSessionModelPreference()`、`saveSessionModelPreference()`；使用一个 `modelProfileBusy` 事务标志，错误通过现有 `BackendApiError` 传播。

- [ ] **Step 6: 运行测试和类型检查**

Run: `E:\Node\npm.cmd exec vitest run src/api/backend.test.ts src/stores/backend.test.ts`

Run: `E:\Node\npm.cmd run build:desktop`

Expected: 两条命令均 PASS/exit 0。

- [ ] **Step 7: 提交**

```powershell
git add a3-front/a3-front/src/api/types.ts a3-front/a3-front/src/api/backend.ts a3-front/a3-front/src/api/backend.test.ts a3-front/a3-front/src/stores/backend.ts a3-front/a3-front/src/stores/backend.test.ts a3-front/a3-front/src/env.d.ts
git commit -m "feat: expose model profiles to the renderer"
```

---

### Task 11: 重做模型设置页为多配置管理

**Files:**
- Create: `a3-front/a3-front/src/components/model/ModelProfileList.vue`
- Create: `a3-front/a3-front/src/components/model/ModelProfileList.test.ts`
- Create: `a3-front/a3-front/src/components/model/ModelProfileEditor.vue`
- Create: `a3-front/a3-front/src/components/model/ModelProfileEditor.test.ts`
- Modify: `a3-front/a3-front/src/views/ModelSettings.vue`
- Modify: `a3-front/a3-front/src/views/ModelSettings.test.ts`

- [ ] **Step 1: 写配置列表交互测试**

覆盖：选中卡片、默认星标、启停、测试、删除确认、备用顺序上移/下移、健康状态；列表 DOM 和事件 payload 不含完整 Key。

- [ ] **Step 2: 写编辑器测试**

覆盖：新建必须输入 Key；编辑留空沿用旧 Key；模型 ID、显示名、适配器和档位白名单；测试成功后才允许保存；保存/失败后清空 Key 输入框。

- [ ] **Step 3: 运行组件测试并确认失败**

Run: `E:\Node\npm.cmd exec vitest run src/components/model/ModelProfileList.test.ts src/components/model/ModelProfileEditor.test.ts src/views/ModelSettings.test.ts`

Expected: FAIL，组件尚不存在。

- [ ] **Step 4: 实现列表与编辑器**

列表只接收 `ModelProfileSummary[]`；编辑器使用本地 reactive 草稿，`api_key` 从不从 props 初始化。适配器使用固定 select：`none/openai_reasoning_effort/anthropic_thinking`；推理档位使用 checkbox 组，至少包含 `auto`。

- [ ] **Step 5: 组合设置页**

桌面宽度使用左侧配置列表 + 中间编辑器 + 右侧状态/安全说明；窄屏改为垂直卡片。顶部提供自动备用开关和默认/备用顺序说明。沿用暖色 openhanako 风格，不改变账号与桌宠预留区。

- [ ] **Step 6: 运行测试与构建**

Run: `E:\Node\npm.cmd exec vitest run src/components/model/ModelProfileList.test.ts src/components/model/ModelProfileEditor.test.ts src/views/ModelSettings.test.ts`

Run: `E:\Node\npm.cmd run build:desktop`

Expected: PASS/exit 0。

- [ ] **Step 7: 提交**

```powershell
git add a3-front/a3-front/src/components/model a3-front/a3-front/src/views/ModelSettings.vue a3-front/a3-front/src/views/ModelSettings.test.ts
git commit -m "feat: add multi-profile model settings UI"
```

---

### Task 12: 增加学习空间模型与推理强度选择器

**Files:**
- Create: `a3-front/a3-front/src/components/model/ModelSelectionPopover.vue`
- Create: `a3-front/a3-front/src/components/model/ModelSelectionPopover.test.ts`
- Modify: `a3-front/a3-front/src/views/SmartTutor.vue`
- Modify: `a3-front/a3-front/src/views/SmartTutor.test.ts`
- Modify: `a3-front/a3-front/src/api/types.ts`

- [ ] **Step 1: 写选择器能力过滤测试**

配置 A 模型支持 low/medium/high，配置 B 模型只支持 auto/off；切换模型后断言不支持档位禁用，当前 xhigh 自动显示为实际 high；“跟随全局”产生 `profile_mode="auto"`。

- [ ] **Step 2: 写自动切换和流中断 UI 测试**

收到 SSE `meta` 且 `failover_used=true` 时显示非阻断提示；收到 `interrupted` 时保留已有文本、停止 generating，并显示“使用备用配置继续”；点击后发送新请求而不是修改旧消息。

- [ ] **Step 3: 运行测试并确认失败**

Run: `E:\Node\npm.cmd exec vitest run src/components/model/ModelSelectionPopover.test.ts src/views/SmartTutor.test.ts`

Expected: FAIL。

- [ ] **Step 4: 实现选择器**

按钮显示 `effective model label + reasoning label`；弹层第一行选择配置/模型，第二行选择推理档位；提供跟随全局和单空间自动备用开关。只提交 profile/model/effort 枚举与 ID。

- [ ] **Step 5: 扩展 `StreamEvent` 并处理事件**

增加 `profile_id/model_id/requested_reasoning_effort/effective_reasoning_effort/failover_used/can_continue_with_backup`；`meta` 更新显示，`interrupted` 不清空已收 delta。继续请求包含普通学习文本提示，不把 API 配置或 Key放入消息。

- [ ] **Step 6: 运行测试与桌面构建**

Run: `E:\Node\npm.cmd exec vitest run src/components/model/ModelSelectionPopover.test.ts src/views/SmartTutor.test.ts`

Run: `E:\Node\npm.cmd run build:desktop`

Expected: PASS/exit 0。

- [ ] **Step 7: 提交**

```powershell
git add a3-front/a3-front/src/components/model/ModelSelectionPopover.vue a3-front/a3-front/src/components/model/ModelSelectionPopover.test.ts a3-front/a3-front/src/views/SmartTutor.vue a3-front/a3-front/src/views/SmartTutor.test.ts a3-front/a3-front/src/api/types.ts
git commit -m "feat: add per-session model reasoning selector"
```

---

### Task 13: 兼容迁移、故障注入和完整桌面验收

**Files:**
- Modify: `backend/routers/model_settings.py`
- Modify: `backend/services/model_settings.py`
- Modify: `backend/tests/test_model_settings.py`
- Modify: `a3-front/a3-front/electron/model-config-controller.mjs`
- Modify: `a3-front/a3-front/electron/model-config-controller.test.mjs`
- Modify: `a3-front/a3-front/src/api/README.md`
- Modify: `backend/API示例.md`
- Modify: `README.md`
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: 写旧接口兼容测试**

旧 `GET /api/settings/model` 返回全局默认配置脱敏视图；旧测试入口转接 runtime test；生产 PUT 不写 `.env`；版本 1 Electron 配置启动后自动迁移且 ready 200。

- [ ] **Step 2: 增加假网关故障矩阵**

参数化覆盖 timeout、连接错误、429+Retry-After、502/503/504、401、403、404、零输出断流、已输出断流、half-open 恢复和取消；断言调用次数不超过预算、终止错误不使用备用、日志无密钥。

- [ ] **Step 3: 运行所有自动化测试**

Run: `E:\软件杯\.venv\Scripts\python.exe -m pytest -q backend`

Run: `E:\Node\npm.cmd test`（工作目录 `E:\软件杯\a3-front\a3-front`）

Expected: 全部 PASS，无失败和未处理异常。

- [ ] **Step 4: 构建并替换桌面后端**

Run: `E:\软件杯\backend\build_api.ps1 -Python E:\软件杯\.venv\Scripts\python.exe`

Run: `E:\软件杯\backend\verify_api_package.ps1 -Executable ..\dist\api\api.exe`

停止当前 A3 Electron/api 进程；验证源和目标绝对路径均在 `E:\软件杯`；先临时备份，再把 `dist/api` 复制到 `a3-front/a3-front/desktop-backend`。新包验证成功后删除备份。

- [ ] **Step 5: 运行桌面构建与打包启动检查**

Run: `E:\Node\npm.cmd run build:desktop`

Run: `E:\Node\npm.cmd run desktop:pack`

Expected: exit 0，unpacked 应用包含新 backend 且测试模式退出无残留。

- [ ] **Step 6: 真实桌面验收**

依次验证：旧配置迁移；新增第二配置；测试后保存；默认/备用排序；不重启后端热切换；全局与学习空间覆盖；模型与推理档位过滤；主配置临时失败时零输出自动备用；已输出流中断不拼接；关闭自动备用时直接报错；应用重启后配置恢复。

真实 API 连续执行至少 5 次，记录成功率、P50/P95、实际配置/模型/推理档位，不输出 Key 和回复正文。

- [ ] **Step 7: 密钥与构建产物扫描**

对 Git diff、renderer 源码、preload、`dist` 和 unpacked 资源执行密钥模式扫描；允许测试中的 `test-secret-key`，拒绝任何真实 `sk-` 长串、桌面令牌、完整 base URL 凭据和 `model-profiles.enc`。

- [ ] **Step 8: 更新文档和任务队列**

README 说明多配置、故障转移、推理档位和安全存储；API 示例记录 internal 接口仅供 Electron 主进程；把 S-017/T-033 验证结果、文件和命令写入队列，确认全部门槛后才标记 T-033 完成。

- [ ] **Step 9: 最终提交**

```powershell
git add README.md backend/API示例.md backend/routers/model_settings.py backend/services/model_settings.py backend/tests/test_model_settings.py a3-front/a3-front/electron/model-config-controller.mjs a3-front/a3-front/electron/model-config-controller.test.mjs a3-front/a3-front/src/api/README.md codex/AI模型任务队列.md
git commit -m "feat: deliver stable multi-api model routing"
```

不得推送远程仓库，除非用户另行明确授权。
