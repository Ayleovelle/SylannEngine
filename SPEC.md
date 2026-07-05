# SylannEngine SDK 规范

版本：`2.4.0`
协议版本：`sylanne.engine.v1`

> **Scope / 定位**：This document is the **SDK API specification** — public interface, output schema, configuration, and lifecycle.
> For the **theoretical computation standard** (axioms, algebra, conformance levels), see [docs/theoretical_spec.md](docs/theoretical_spec.md).
> For a practical **integration walkthrough** (including multi-plugin sharing), see [AGENT_GUIDE.md](AGENT_GUIDE.md).
>
> 本文档是 **SDK API 规范**——公开接口、输出 schema、配置与生命周期。
> 理论计算标准（公理、代数、一致性等级）见 [docs/theoretical_spec.md](docs/theoretical_spec.md)。
> 实用集成指南（含多插件共享）见 [AGENT_GUIDE.md](AGENT_GUIDE.md)。

---

## 1. Overview / 概述

SylannEngine is an affective computation engine SDK.
SylannEngine 是一个情感计算引擎 SDK。

**Positioning / 定位**: Pure computation black-box. Text in, structured data out. No reply generation, no prompt injection, no message routing.
纯计算黑盒。文本输入，结构化数据输出。不生成回复，不注入 prompt，不管消息收发。

---

## 2. Interface Protocol / 接口协议

### 2.0 Installation / 安装方式

**Preferred (first-class path): install into a shared venv.** Pin
`sylanne-core>=2.4,<3` in `requirements.txt` so every co-deployed plugin resolves
to ONE installed copy — this is what lets `shared()`/`submit()` dedup for real
across plugins with no configuration.
**首选（一等公民路径）：装进共享 venv。** `requirements.txt` 里锁 `sylanne-core>=2.4,<3`，
让所有同宿主插件都解析到**同一份**已装拷贝——这是 `shared()`/`submit()` 能跨插件真正
去重、且零额外配置的前提。

```
# requirements.txt
sylanne-core>=2.4,<3
```

```python
from sylanne_core import SylanneEngine, SylanneConfig

engine = await SylanneEngine.shared(
    SylanneEngine.shared_data_dir(),
    llm=your_own_llm_callback,  # 自行实现 async (str, str) -> str
)
surface = await engine.submit(session_id, text, msg_id=msg_id)
```

**Alternative: vendor a copy** (single-plugin deployments, or hosts that do
not allow shared dependency installation). Cross-copy convergence still works
via the rendezvous cell (§2.1.1), but mixed-version vendored copies are a
load-order lottery (§2.1.2) — the shared-venv path has no such lottery.
**备选：内嵌一份拷贝**（单插件部署，或不允许共享装依赖的宿主）。跨拷贝汇合仍靠
rendezvous cell 生效（§2.1.1），但混版本 vendored 拷贝存在加载顺序抽签（§2.1.2）——
共享 venv 路径没有这个问题。

```bash
git submodule add https://github.com/Ayleovelle/SylannEngine.git deps/sylannengine
```

```python
import sys
sys.path.insert(0, "./deps/sylannengine")

from sylanne_core import SylanneEngine, SylanneConfig

engine = SylanneEngine(
    data_dir="./data/sylannengine",
    llm=your_own_llm_callback,
    config=SylanneConfig(),
)
await engine.start()
```

The SDK has no framework dependency. / SDK 不依赖任何特定框架。

Recommended runtime pin assertion for plugin templates / 插件模板建议加的一行运行时版本断言:

```python
import sylanne_core
assert sylanne_core.__version__.split(".")[0] == "3", (
    f"sylanne-core {sylanne_core.__version__} incompatible; need 3.x"
)
```

### 2.1 Engine Initialization / 引擎初始化

```python
from sylanne_core import SylanneEngine

engine = SylanneEngine(
    data_dir: str | Path,                          # 持久化目录（必填）
    llm: Callable[[str, str], Awaitable[str]],     # LLM 回调函数（必填）
    embedding: Callable[[str], Awaitable[list[float]]] | None = None,  # 向量化回调（可选）
    config: SylanneConfig | None = None,           # 配置覆盖（可选）
    *,
    assessor_llm: Callable[[str, str], Awaitable[str]] | None = None,  # 专用评估器 LLM（可选）
)
```

#### Shared Instance / 共享实例

Use `SylanneEngine.shared()` to deduplicate engines by resolved data_dir within
a process — one persistence directory is owned by exactly one engine, avoiding
state splits and lost updates on flush. The guarantee is **per process**: there is
no cross-process lock, so two OS processes on one data_dir would double-flush —
run one process per data_dir.
用 `SylanneEngine.shared()` 按解析后的 data_dir 在进程内去重——一个持久化目录只由一个引擎拥有，避免状态分裂与 flush 丢更新。该保证是**进程内**的：没有跨进程锁，两个进程指向同一 data_dir 会双写，请一个 data_dir 一个进程。

```python
# 同一 data_dir 总是返回同一已启动实例
engine = await SylanneEngine.shared("./data", llm=my_llm, plugin="my_plugin")

# 应用关闭时显式释放（flush 落盘；无 atexit 自动刷写）——见下方"release_shared 的定位"
await SylanneEngine.release_shared("./data")

# 内省：当前进程有哪些共享引擎
SylanneEngine.list_shared()      # [{"data_dir", "status"}, ...]
SylanneEngine.is_shared("./data")  # bool
```

- 多个下游约定同一 data_dir 并统一走 `shared()`，即可复用单一引擎实例。但**实例去重不等于计算去重**——见下方 submit() 契约，`shared()` 只保证"同一 data_dir 一个引擎"，谁来触发计算靠 `submit()`。
- `plugin: str | None`（可选）：调用方身份字符串，写入 `engine.participants()`，纯诊断，不影响任何去重/共享行为（见 §2.1.3）。
- 不传 `config` 时引擎自读 `<data_dir>/sylanne.config.json`（见 §7），所有下游共享同一份用户可改配置；首次启动写入默认模板。
- 配置冲突：**显式传入**不同 `config` → 抛 `SharedEngineConflictError`；自读（文件被改 / 跨版本 vendored copy）出现差异 → 仅警告并复用运行中的配置（重启生效），不崩后来者。不同 `llm`/`embedding`/`assessor_llm` → 警告并复用原实例（first-builder-wins；`set_llm()` 可事后热替换，见 §2.1.4）。
- 共享实例 **event-loop 亲和**：仅在首次获取的事件循环内使用，跨 loop 使用抛 `RuntimeError`；不要对共享实例用 `async with`。
- `release_shared()` 之后该实例 `closed`；**不要再用已释放的实例**——共享引擎对已释放实例的再次调用会抛 `RuntimeError`（避免在注册表外复活成第二个引擎、双写丢更新），请重新 `shared()` 获取。
- 直接 `SylanneEngine(...)` 构造不受影响，且不进入共享注册表；但若目标 data_dir 已有活跃共享实例，会记一条 warning 提示重复创建（软提醒，不阻断）。
- 多个 vendored 副本（不同模块名）共存会汇合到同一引擎并去重；若某副本版本与建引擎的副本不一致，会记一条版本串味 warning，建议各副本独立 namespace，或整进程装一份共享依赖（见 §2.0 shared-venv-first）。

#### 2.1.1 submit() — 幂等前门（取代开发期的 driver/observer 角色层设计，2.4.0）

2.4.0 发布前的开发分支上曾短暂存在一层 driver/observer 角色设计（`acquire`/`AcquireResult`/
`ObserverView`/`role`/`as_observer`），发布前整层撤回——正式版本里这些名字**不存在**，无弃用垫片。
撤回原因：那一层把"谁真跑计算"锚定在 SDK **物理拷贝目录**上
（`my_id == builder_id`），而共享 venv 部署下所有插件共用同一份拷贝，这个判断对每个插件恒真——
N 个插件全拿到 `role="driver"`，N 路 `process()` 全接上，N 倍 LLM 账单，机制在它唯一要解决的默认
部署下彻底 no-op。

新模型不再问"谁是谁"，只问"这条消息算过没有"：

```python
engine = await SylanneEngine.shared(data_dir, llm=my_llm)
surface = await engine.submit(
    session_id,
    text,                          # 传平台原始、未经改写的文本……
    msg_id=event.message_obj.message_id,  # ……或者（更稳）传平台自己的消息 id
)
```

**签名：**

```python
async def submit(
    self, session_id: str, text: str, *,
    msg_id: str | None = None,
    confidence: float | None = None,
    flags: list[str] | None = None,
    now: float | None = None,
    values: dict[str, float] | None = None,
    dedup: bool = True,      # False == 直接 process()，不进去重表
    plugin: str | None = None,  # 诊断专用身份，见 §2.1.3
) -> Surface
```

**保证的精确措辞**：对**所有走 `submit()`、且传一致键**（同一份平台原始文本，或稳定的 `msg_id`）
的调用方 1x——这是契约，不是牢房：直连 `process()` 的调用方不在覆盖范围内（明确的逃生口，不是漏洞）；
保证不要求任何插件知道、信任或分类其他插件，这正是它和 2.4.0 式"合作式角色标签"的本质区别。

**双索引去重表**（挂在引擎实例上，不在 rendezvous cell 里；引擎单 loop 亲和、无锁）：

每次首见提交同时登记两个键：文本哈希键 `(session_id, "h:" + blake2b(text)[:32])` 恒登记；
`msg_id` 键 `(session_id, msg_id)` 在给了 `msg_id` 时额外登记。Join 规则：

| 本次调用 | 命中情况 | 结果 |
|---|---|---|
| 无 `msg_id` | 命中哈希键 | join |
| 带 `msg_id` | 直接命中 `msg_id` 键 | 恒 join（若记录文本不同，WARNING 一次——消息 id 复用是危险模式，仍信任平台、以首提交者为准） |
| 带 `msg_id` | 未命中 `msg_id` 键，但命中哈希键，且哈希条目**未记录** `msg_id` | join（顺便把哈希条目升级为也可走 `msg_id` 直接命中） |
| 带 `msg_id` | 未命中 `msg_id` 键，命中哈希键，但哈希条目记录了**不同** `msg_id` | 真重复（同文本不同消息）→ 重新计算 |

真计算跑在**detached task**（`asyncio.ensure_future`，非直接 await）里；所有 awaiter（含首提交者）
一律 `await asyncio.shield(task)`——任一 awaiter 自己那侧的取消，永远杀不掉共享计算。

**窗口与容量**：每次 `submit()` 调用开头惰性 prune——已完成条目超过 `config.submit_window_seconds`
（默认 10.0s）即驱逐；超出 `config.submit_max_entries`（默认 1024）按最老完成条目优先驱逐。**in-flight
条目不受两条规则约束**，只有真正完成的计算才会老化。失败任务立即驱逐自己的键——毒条目不会在窗口内
"赖着"拖累后续同键提交。

**上下文分歧**：join 到的调用如果 `confidence`/`flags`/`values` 与首提交者不同，debug 级打一次日志，
首提交者的上下文胜出（不是错误，只是提醒）。

**诚实限度**：无 `msg_id` 时，窗口期内的真·重复消息（同一用户真的两次说了一模一样的话）会被合并为
一次计算，状态不推进——这是启发式键（文本哈希）的代价；`msg_id` 能根除这个问题，`submit_window_seconds`
可调小以压缩伤害面，`dedup=False` 可完全逃生。

#### 2.1.2 tick() 收敛语义

```python
async def tick(self, session_id: str, flags: list[str] | None = None, *, force: bool = False) -> Surface
```

对每个 `session_id` 强制**绝对最小间隔** `config.tick_min_interval_seconds`（默认 45.0s）：距该
session 上次真实 tick 不满这个间隔的调用，直接返回缓存的 `Surface`，**不推进状态、不触碰 host**。
这不是心跳调度器，引擎自己不持有任何计时器——它存在的唯一目的是让若干共存插件各自跑自己独立的
~60s 心跳循环打到同一个共享引擎上时，收敛到约每 45s 一次真实 tick，而不是 N 次。

`force=True` 绕过收敛器、总是推进状态——这是测试/运维逃生口，**不是"心跳所有权"的暗号**：没有任何
调用方因为传了 `force` 而获得特殊地位，故意抢间隔本身就违背了调 `tick()` 的意义。

调用次数为什么重要：`compute/body.py` 的事件处理把每次调用的 `elapsed`（距上次事件秒数）钳制到
`[1, 12]`（见 `body.py:402`）——衰减/推进量以此为准，而非墙钟时间差本身，所以"调了几次"直接决定
状态推进了多少步，收敛调用次数就是收敛推进速度。

#### 2.1.3 participants() — 诊断专用身份登记（2.4.0 新增）

```python
def participants(self) -> list[dict]     # [{"plugin","copy_id","sdk_version","first_seen","submits","joins"}, ...]
def submit_stats(self) -> dict           # {"computed","joined","recomputed_after_window",["by_plugin"]}
```

`shared(..., plugin=...)` / `submit(..., plugin=...)` 给的身份字符串，只写入这两个诊断入口。**硬规则：
`submit()` 的去重/join 决策不读取、不分支任何来自这份登记表的信息**——身份负责观测，幂等负责保证。
这是"每 SDK 拷贝专属 id"这类方案的红队通过版：识别调用方是谁，纯粹是为了让运维能看清"哪个插件提交了
多少次、join 了多少次"，绝不允许它像 2.4.0 的 `role` 那样悄悄变成行为判断的输入。

#### 2.1.4 set_llm() — 建者死亡后的运维逃生口

```python
def set_llm(self, llm: LLMFn, *, assessor_llm: LLMFn | None = None) -> None
```

建共享引擎的那个插件被热禁用/卸载/重载后，引擎手里握的 `llm` 闭包可能指向已拆除的状态（见下方
"建者死亡"一节）。`set_llm()` 让运维脚本/健康检查在不重启进程的前提下把它换掉——纯手动，无自动
魔法，没有任何代码会替你调用它。替换时打一条 INFO。

#### 2.1.5 peek_shared() / wait_shared() — 纯监听插件

```python
@classmethod
def peek_shared(cls, data_dir) -> SylanneEngine | None            # 只读探活，永不建引擎
@classmethod
async def wait_shared(cls, data_dir, *, timeout=None, interval=0.5) -> SylanneEngine | None  # 轮询等
```

给没有自己 `llm`、绝不该成为建引擎那份拷贝的纯监听插件。`wait_shared` 是普通轮询循环（默认 0.5s
间隔），不是跨拷贝唤醒协议——parked-future 式唤醒方案在不同模块名的 vendored 拷贝间会丢唤醒/泄漏，
评估后放弃；0.5s 轮询对聊天场景的附着延迟无感知，也不需要引入任何新的跨拷贝同步原语。超时（`timeout`
非 `None` 且到期）打一条 INFO 后返回 `None`——这是正确行为：还没人为这个 data_dir 声明过算力。

#### 2.1.6 建者死亡 / 混布加载顺序抽签

单点身份消失是**结构性非事件**：建引擎的插件被热禁用后，其余幸存插件的 `submit()` 照常计算——没有
driver 就没有孤儿。唯一残留是建者的 `llm` 闭包：引擎的 `_llm` 引用还指向它，若该闭包捕获的状态已被
拆除，评估会走 `assess` 的异常兜底降级（`health()` 可见 `status="degraded"`，confidence-0 兜底继续
跑），文档建议传宿主级、比插件生命周期更长的 provider 回调；需要热替换见 §2.1.4 `set_llm()`。

多拷贝混布（部分已升级 3.0、部分还在 2.x）不是机制性收敛问题，是一次性的**加载顺序抽签**：谁先建
引擎，那份拷贝的能力就是全场能力。附着到一个没有 `submit()` 的旧引擎会打响亮 WARNING 点名建者版本
（`_sharing.py` 附着路径），从 2.4.0 的静默 no-op 变成响亮告警——但机械层面无法收敛，唯一出路是统一
升级所有拷贝（回到 §2.0 的 shared-venv-first 建议）。

#### release_shared() 的定位

`release_shared()` 是**进程级运维拆除**——flush、释放槽位，之后同 data_dir 的下一次 `shared()` 会建
一个全新引擎。它不是插件生命周期钩子：**插件的 `terminate()` 里禁止调用它**，那会替所有还在用这个
引擎的共存插件把引擎一起关掉。应用整体关闭时在进程级关闭路径调用一次即可，平时谁都不用调。

### 2.2 Core Methods / 核心方法

| Method / 方法 | Signature / 签名 | Description / 说明 |
|--------|-----------|-------------|
| **Lifecycle / 生命周期** |||
| `start` | `async () -> None` | 启动引擎（init -> running） |
| `shutdown` | `async () -> None` | 关闭引擎（刷写所有状态 -> closed） |
| **Shared Instance / 共享实例** |||
| `shared` | `classmethod async (data_dir, llm, embedding=None, config=None, *, assessor_llm=None, plugin=None) -> SylanneEngine` | 取进程内共享实例（按 data_dir 去重，返回已 start 的引擎）；不传 config 时自读 `sylanne.config.json`；`plugin` 见 §2.1.3 |
| `release_shared` | `classmethod async (data_dir) -> None` | 进程级运维拆除，见 §2.1"release_shared 的定位"——不要在插件 `terminate()` 里调 |
| `is_shared` | `classmethod (data_dir) -> bool` | 该 data_dir 是否已有活跃共享实例 |
| `list_shared` | `classmethod () -> list[dict]` | 列出当前进程所有共享实例及状态 |
| `clear_shared_registry` | `classmethod () -> None` | 清空共享注册表（不 shutdown；**仅测试隔离用**） |
| `shared_data_dir` | `classmethod (explicit=None) -> Path` | 解析 host 级共享目录（`explicit` > `$SYLANNE_DATA_DIR` > `~/.sylanne/shared`），让独立插件汇合到同一引擎；不创建目录 |
| `peek_shared` | `classmethod (data_dir) -> SylanneEngine \| None` | 只读探活，永不建引擎（见 §2.1.5） |
| `wait_shared` | `classmethod async (data_dir, *, timeout=None, interval=0.5) -> SylanneEngine \| None` | 轮询等待某个插件先建好共享引擎（见 §2.1.5） |
| `set_llm` | `(llm, *, assessor_llm=None) -> None` | 运维逃生口：热替换 llm/assessor_llm 回调（见 §2.1.4） |
| **Idempotent Front Door / 幂等前门（2.4.0）** |||
| `submit` | `async (session_id, text, *, msg_id=None, confidence=None, flags=None, now=None, values=None, dedup=True, plugin=None) -> Surface` | 共享引擎的幂等前门：同一消息被多个插件提交只算一次（见 §2.1.1） |
| `submit_stats` | `() -> dict` | `{"computed","joined","recomputed_after_window",["by_plugin"]}` 计数快照 |
| `participants` | `() -> list[dict]` | 诊断专用身份登记表（见 §2.1.3），从不参与去重判断 |
| **Session / 会话操作** |||
| `process` | `async (session_id: str, text: str, *, confidence=None, flags=None, now=None, values=None) -> Surface` | **Advanced / raw access.** 直接处理文本，始终重新计算，不参与 `submit()` 的去重表——共享引擎上直连它会绕过跨插件去重（一次性 nudge log 提醒）。单实例场景或明确要求"总是全新计算"的调用方使用；多插件共享场景请用 `submit()`（上下文参数见 §2.3） |
| `tick` | `async (session_id: str, flags: list[str] \| None = None, *, force: bool = False) -> Surface` | 无文本的状态推进，带每 session 绝对最小间隔收敛（默认 45s，见 §2.1.2）；flags 默认 `["idle"]` |
| `state` | `async (session_id: str) -> Surface` | 查询当前状态（不触发计算） |
| `reset` | `async (session_id: str) -> None` | 重置会话状态 |
| `destroy` | `async (session_id: str) -> None` | 销毁会话及持久化数据 |
| `exists` | `(session_id: str) -> bool` | 检查会话是否存在 |
| `inject` | `async (session_id: str, source: str, influence_type: str, intensity: float, target_dimension: str = "", payload: dict \| None = None) -> None` | 向会话热池注入外部影响（见 §2.4） |
| **Events & Health / 事件与健康** |||
| `on` | `(listener: Callable[[str, Surface], Any]) -> None` | 注册推送监听器；每次 `process()`（含 `submit()` 内部调用）完成后回调 `listener(session_id, surface)` |
| `off` | `(listener: Callable[[str, Surface], Any]) -> None` | 移除推送监听器 |
| `health` | `() -> HealthStatus` | 引擎级健康检查（不需要 session；见 §4.8） |

### 2.3 Context Parameters / 上下文参数 (`**ctx`)

| Parameter / 参数 | Type / 类型 | Default / 默认值 | Description / 说明 |
|-----------|------|---------|-------------|
| `confidence` | `float \| None` | `None` | 语义置信度 [0, 1]，None 表示由内部 assessor 计算 |
| `flags` | `list[str]` | `[]` | 事件标签（见 3.3 节） |
| `now` | `float` | `time.time()` | 事件时间戳（Unix epoch） |
| `values` | `dict[str, float]` | `{}` | 附加数值信号 |

### 2.4 External Influence Injection / 外部影响注入 (`inject`)

Other plugins or subsystems call `inject()` to affect the emotional state of a session
without going through the full `process()` pipeline. For example, a memory plugin
detecting contradiction with a previously reflected topic can re-ignite that material
in the hot pool.
其他插件或子系统调用 `inject()` 向会话情感状态注入外部影响，无需走完整 `process()` 管线。
例如，记忆插件检测到与此前反思主题的矛盾时，可在热池中重新点燃该素材。

```python
await engine.inject(
    session_id="user_123",
    source="memory_plugin",         # 来源插件标识
    influence_type="contradiction", # 影响类型
    intensity=0.7,                  # 影响强度 [0, 1]
    target_dimension="",            # 热池中的目标维度/材料类型（默认空）
    payload=None,                   # 可选元数据
)
```

**influence_type enum / 影响类型枚举：**

| Value / 值 | Meaning / 含义 |
|-------|---------|
| `contradiction` | 矛盾——与既有情感记忆冲突 |
| `reinforcement` | 强化——增强现有情感模式 |
| `revelation` | 揭示——引入新的情感维度 |
| `betrayal` | 背叛——破坏信任/安全感 |
| `validation` | 确认——肯定现有情感状态 |

---

## 3. Event & Callback Protocol / 事件与回调协议

### 3.1 LLM Callback Signature / LLM 回调签名

```python
async def llm_callback(system_prompt: str, user_prompt: str) -> str:
    """
    Args:
        system_prompt: 系统指令（如 "评估以下文本的情感倾向"）
        user_prompt: 待评估的文本
    Returns:
        LLM 文本响应
    Raises:
        任何异常会被引擎捕获，该次调用退化为本地计算
    """
```

Internal LLM call scenarios / 引擎内部调用 LLM 的场景：
- **Assessor / 语义评估器**：分类标签（positive/negative/boundary/recovery）

### 3.2 Embedding Callback Signature / Embedding 回调签名

```python
async def embedding_callback(text: str) -> list[float]:
    """
    Args:
        text: 待向量化的文本
    Returns:
        浮点向量（维度不限，引擎内部使用余弦相似度）
    Raises:
        失败时退化为关键词匹配召回
    """
```

### 3.3 Event Tag Enum / 事件标签枚举 (flags)

分为 **semantic tags / 语义标签**（描述文本性质）和 **phase tags / 阶段标签**（描述调用时机）。

#### Semantic Tags / 语义标签

| Tag / 标签 | Meaning / 含义 |
|-----|---------|
| `positive` | 正向/安全交互 |
| `negative` | 负向/伤害性内容 |
| `boundary` | 边界触碰 |
| `recovery` | 修复/恢复行为 |
| `idle` | 空闲/无实质内容 |
| `intimate` | 亲密内容 |
| `conflict` | 冲突内容 |
| `farewell` | 告别 |
| `greeting` | 问候 |

#### Phase Tags / 阶段标签

| Tag / 标签 | Meaning / 含义 |
|-----|---------|
| `request` | 用户发来消息 |
| `response` | AI 回复完成 |
| `proactive` | 主动检查 |

Unrecognized tags are silently ignored. / 未识别的标签会被静默忽略。

---

## 4. Output Schema (Surface) / 输出数据格式

### 4.1 Top-Level Structure / 顶层结构

```jsonc
{
    "schema_version": "sylanne.engine.v1",   // 协议版本
    "session_id": "string",                // 会话标识
    "turns": 0,                            // 累计交互轮次
    "timestamp": 1716960000.0,             // 计算时间戳

    "state": { ... },          // 情感状态（8 子系统）
    "personality": { ... },    // 人格状态（双层）
    "decision": { ... },       // 决策输出
    "guard": { ... },          // 边界守卫
    "pad": { ... },            // PAD 情感空间输出（§4.2）
    "pipeline": { ... },       // 7 层管线中间态（diagnostics=True 时返回）
    "dynamics": { ... },       // 动力学指标
    "debug": { ... }           // 调试信息（diagnostics=True 时返回，见 4.9）
}
```

### 4.2 pad — PAD Emotion Space / PAD 情感空间

Pleasure-Arousal-Dominance dimensional output, always present.
三维情感空间输出（愉悦-唤醒-支配），始终返回。

```jsonc
{
    "valence": 0.0,        // [-1, 1] — 愉悦轴（Pleasure axis）
    "arousal": 0.0,        // [0, 1]  — 生理激活度（physiological activation）
    "dominance": 0.0,      // [0, 1]  — 感知控制力（perceived control）
    "label": "neutral",    // 分类情绪标签（categorical emotion label）
    "confidence": 0.0      // [0, 1]  — 分类置信度（classification confidence）
}
```

### 4.3 state — Affective State / 情感状态（8 子系统）

All values in `[0.0, 1.0]` unless noted otherwise. / 所有数值范围 [0.0, 1.0]，除非特别标注。

```jsonc
{
    "rhythm": {                            // 交互节律
        "beat": 0.0,                       // 累计交互计数（单调递增，无上限）
        "stability": 0.5,                  // 节律稳定性
        "strain": 0.0                      // 应激负荷
    },
    "connection": {                        // 连接状态
        "warmth": 0.4,                     // 关系温暖度
        "circulation": 0.0,                // 互动活跃度
        "memory_flow": 0.0                 // 记忆激活强度
    },
    "adaptation": {                        // 适应性
        "plasticity": 0.0,                 // 学习能力
        "sensitivity": 0.0,                // 输入敏感度
        "repetition": 0,                   // 重复次数（整数）
        "threshold_drift": 0.0             // 脱敏漂移
    },
    "responsiveness": {                    // 响应性
        "readiness": 0.2,                  // 行动准备度
        "fatigue": 0.0,                    // 疲劳度
        "trained_reach": 0.0               // 训练容量
    },
    "valence": {                           // 情感效价
        "warmth": 0.45,                    // 情感温暖度
        "volatility": 0.0,                 // 波动性
        "recovery_heat": 0.0               // 恢复能量
    },
    "damage": {                            // 损伤状态
        "open": 0.0,                       // 当前活跃损伤
        "accumulated": 0.0,                // 累积影响
        "sensitivity": 0.0,                // 损伤敏感度
        "recovery": 0.0                    // 恢复进度
    },
    "boundary": {                          // 边界防护
        "pressure": 0.0,                   // 边界压力
        "autonomy": 1.0,                   // 自主权水平
        "interruption_budget": 1.0,        // 主动中断预算
        "cooldown": 0.0,                   // 冷却计时器
        "paused": false                    // 暂停标志（布尔）
    },
    "capacity": {                          // 系统容量
        "load": 0.0,                       // 系统负荷
        "exhaustion": 0.0,                 // 耗竭程度
        "recovery_debt": 0.0              // 恢复欠债
    },
    "needs": {                             // 需求指标
        "expression": 0.0,                 // 表达需求
        "quiet": 0.0,                      // 安静需求
        "recovery": 0.0,                   // 恢复需求
        "contact": 0.0                     // 接触需求
    }
}
```

### 4.4 personality — Personality State / 人格状态

```jsonc
{
    "schema_version": "sylanne.core.personality.v1",

    // Deep structure / 深层结构 — 缓慢漂移，计算驱动
    "deep": {
        "expression_drive": 0.5,           // 表达驱力
        "perception_acuity": 0.5,          // 感知敏锐度
        "boundary_permeability": 0.5,      // 边界渗透性（对新事物的开放度）
        "inner_coherence": 0.5,            // 内在一致性
        "relational_gravity": 0.5          // 关系引力（向他人靠近的倾向）
    },

    // Surface expression / 表层表达 — 快速漂移，文本事件驱动
    "surface": {
        "warmth_bias": 0.5,                // 温暖偏向
        "directness": 0.5,                 // 直接度
        "curiosity": 0.5,                  // 好奇心
        "patience": 0.5,                   // 耐心
        "intimacy_pull": 0.5,              // 亲密倾向
        "autonomy_guard": 0.5             // 自主权保护强度
    }
}
```

### 4.5 decision — Decision Output / 决策输出

```jsonc
{
    "action": "express",                   // 行动类型（枚举）
    "reason": "string",                    // 人类可读的决策原因
    "reason_code": "string",               // 机器可读的原因分类
    "confidence": 0.75,                    // 决策置信度 [0, 1]
    "urgency": 0.3                         // 紧迫度 [0, 1]
}
```

**action enum / 行动枚举：**

| Value / 值 | Meaning / 含义 | Typical Scenario / 典型场景 |
|-------|---------|------------------|
| `express` | 主动表达 | 表达驱力高 |
| `withdraw` | 退缩/沉默 | 负向信号，边界压力高 |
| `recover` | 尝试恢复 | 检测到伤害后 |
| `reach_out` | 主动接触 | 关系引力高 |
| `explore` | 探索/试探 | 好奇心驱动 |
| `hold` | 保持/等待 | 无明确驱力 |
| `guard` | 防御 | 自主权受威胁 |

### 4.6 guard — Boundary Guard / 边界守卫

```jsonc
{
    "allowed": true,                       // 是否允许当前行动
    "reason": "string",                    // 阻止原因（allowed=false 时有值）
    "risk_score": 0.1,                     // 风险评分 [0, 1]
    "constraints": []                      // 当前生效的约束列表
}
```

### 4.7 pipeline — 7-Layer Pipeline State / 7 层管线中间态（可选）

Disabled by default. Enable via `config.diagnostics = True`.
默认关闭，通过 `config.diagnostics = True` 开启。

```jsonc
{
    "L1_encoding": {                       // 第 1 层：超维编码
        "hamming_distance": 0.42,          // 与上次输入的汉明距离
        "novelty": 0.6                     // 新颖度
    },
    "L2_gate": {                           // 第 2 层：预测编码门控
        "path": "normal",                  // 路径：fast / normal / full
        "surprise": 0.35                   // 预测误差
    },
    "L3_absence_impact": {                 // 第 3 层：缺失-影响引擎
        "absence_pressure": 0.2,           // 缺失压力
        "impact_count": 3,                 // 活跃影响数
        "coupling_strength": 0.4           // 耦合强度
    },
    "L4_relational": {                     // 第 4 层：关系动力学
        "coherence": 0.7,                  // 关系一致性
        "active_relations": 2              // 活跃关系数
    },
    "L5_fusion": {                         // 第 5 层：多专家决策融合
        "expert_weights": {},              // 各专家权重
        "consensus": 0.6                   // 共识度
    },
    "L6_boundary": {                       // 第 6 层：自维持边界
        "integrity": 0.9,                  // 边界完整性
        "phase": "stable"                  // 状态：stable / transitioning / breached
    },
    "L7_expression": {                     // 第 7 层：表达触发
        "pressure": 0.4,                   // 表达压力
        "threshold": 0.6,                  // 触发阈值
        "fired": false                     // 本次是否触发
    }
}
```

### 4.8 dynamics — Dynamic Indicators / 动力学指标

```jsonc
{
    "affect": {                            // 情感驱力
        "recovery_drive": 0.0,             // 恢复驱力
        "expression_drive": 0.0,           // 表达驱力
        "quiet_drive": 0.0                 // 安静驱力
    },
    "moral_state": {                       // 道德状态
        "state": "stable",                 // 状态：stable / recovering
        "events": 0                        // 累计事件数
    },
    "uncertainty": {                       // 不确定性
        "claim_caution": 0.0,              // 断言谨慎度 [0, 1]
        "events": 0                        // 累计事件数
    },
    "relational_time": {                   // 关系时间
        "interval_seconds": 0.0,           // 距上次交互的秒数
        "total_duration": 0.0,             // 关系总时长（秒）
        "phase": "active"                  // 阶段：active / cooling / dormant
    },
    "hot_pool": {                          // 热池诊断
        "temperature": 0.0,                // 热池温度
        "volume": 0.0,                     // 热池体积
        "pressure": 0.0,                   // 热池压力
        "material_count": 0,               // 活跃素材数（整数）
        "cascade_active": false,           // 级联是否激活（布尔）
        "cascade_intensity": 0.0,          // 级联强度
        "sensitivity_multiplier": 1.0,     // 敏感度乘数
        "in_recovery": false,              // 是否处于恢复期（布尔）
        "collapse_count": 0                // 崩溃计数（整数）
    }
}
```

### 4.9 debug — Debug Info / 调试信息（diagnostics=True 时返回）

开发者用于判断计算模块是否正常工作。

```jsonc
{
    "healthy": true,                       // 计算引擎是否健康（所有断路器关闭）
    "circuit_breakers": {                  // 各层断路器状态
        "L3_absence_impact": {
            "open": false,                 // 是否断开（true=该层已熔断，使用缓存结果）
            "failures": 0                  // 连续失败次数
        }
    },
    "layer_avg_ms": {                      // 各层平均耗时（毫秒）
        "L1_encoding": 0.12,
        "L3_absence_impact": 1.45
    },
    "computation_cache_size": 5,           // 计算结果缓存条数
    "kernel_schema_version": "sylanne.alpha.body.v1"  // 内核 schema 版本
}
```

**引擎级健康检查**（不需要 session）：

```python
engine.health()
# 返回：
{
    "status": "running",               // 引擎状态：running / degraded / closed
    "active_sessions": 3,              // 当前活跃会话数
    "data_dir_exists": true,           // 持久化目录是否存在
    "llm_configured": true,            // LLM 回调是否已配置
    "embedding_configured": false      // Embedding 回调是否已配置
}
```

---

## 5. Error Handling / 错误处理

### 5.1 Error Codes / 错误码

| Code / 错误码 | Meaning / 含义 | Recoverable / 可恢复 |
|------|---------|-------------|
| `E_SESSION_NOT_FOUND` | 会话不存在 | 是（自动创建） |
| `E_LLM_UNAVAILABLE` | LLM 回调失败 | 是（退化为本地计算） |
| `E_EMBEDDING_UNAVAILABLE` | Embedding 回调失败 | 是（退化为关键词匹配） |
| `E_PERSISTENCE_FAILED` | 持久化写入失败 | 否（状态可能丢失） |
| `E_INVALID_INPUT` | 输入参数不合法 | 是（修正后重试） |
| `E_ENGINE_NOT_INITIALIZED` | 引擎未初始化 | 是（调用 start()） |

### 5.2 Error Response Format / 错误响应格式

```jsonc
{
    "ok": false,
    "error": {
        "code": "E_LLM_UNAVAILABLE",      // 错误码
        "message": "LLM callback raised TimeoutError",  // 错误描述
        "degraded": true                   // true 表示已退化运行，结果仍可用
    },
    // degraded=true 时仍返回计算结果（基于本地计算）
    "state": { ... },
    "decision": { ... }
}
```

### 5.3 Degradation Strategy / 退化策略

The engine is designed to **degrade gracefully** under failure conditions. / 引擎在故障条件下优雅降级。

| Failure / 失败点 | Degradation / 退化行为 |
|---------|-------------|
| LLM assessor unavailable / LLM 评估器不可用 | 使用本地规则引擎评估标签 |
| Persistence failed / 持久化失败 | 内存中继续运行，下次成功时补写 |

---

## 6. Versioning / 版本管理

### 6.1 Semantic Versioning / 语义化版本

SDK follows SemVer: `MAJOR.MINOR.PATCH` / SDK 遵循语义化版本规范。

- **MAJOR**：Surface schema 不兼容变更（字段删除/重命名/类型变更）
- **MINOR**：新增字段、新增方法（向后兼容）
- **PATCH**：Bug 修复、性能优化（行为不变）

### 6.2 Schema Version / Schema 版本

Each output block carries `schema_version`. / 每个输出块携带 schema_version 字段。

Format / 格式：`sylanne.<domain>.<version>`

```python
if surface["schema_version"].startswith("sylanne.engine.v1"):
    # compatible / 兼容
    pass
```

### 6.3 Deprecation Policy / 废弃策略

- 废弃字段至少保留 2 个 MINOR 版本
- 废弃字段标记为 `"_deprecated": true`
- CHANGELOG 中列出迁移路径

---

## 7. Configuration / 配置 (SylanneConfig)

```python
@dataclass
class SylanneConfig:
    mode: Literal["lite", "pro", "max"] = "lite"  # 计算档位
    diagnostics: bool = False          # 是否返回管线中间态
    assessor_enabled: bool = True      # 是否启用 LLM 评估器
    persistence_fsync: bool = True     # 持久化是否 fsync
    tick_drift_cap: float = 0.05       # 单次人格漂移上限
    locale: str = "zh"                 # 语言（影响评估器 prompt）
    force_backend: str | None = None   # 覆盖后端探测（None/"torch"/"cupy"/"numpy"/"python"）；被接受并校验、写入 DimensionProfile.backend，但该字段在当前接线下无任何读取者（HGT 的 numpy 加速开关硬编码读本地 _HAS_NUMPY，不读 profile.backend），故对计算无可观测影响；保留此参数位是因为下游插件在构造时会显式传 force_backend="python"
    training_data_sink: bool = False   # 启用后写本地蒸馏语料（离线 student 训练用）
    training_data_path: str | None = None  # 语料文件名（默认 "distill_corpus.jsonl"）
    training_data_salt: str = ""       # 会话哈希的本地盐（空 = 进程随机盐）
    pel_core_enabled: bool = False     # 启用 PEL-Core 预测编码情感核（v2.5 实验性）
    submit_window_seconds: float = 10.0    # submit() 完成条目的去重窗口（见 §2.1.1）
    submit_max_entries: int = 1024         # submit() 完成条目上限，超出驱逐最老（in-flight 不受限）
    tick_min_interval_seconds: float = 45.0  # tick() 每 session 绝对最小间隔（见 §2.1.2）
```

### 7.1 Config File / 配置文件

不显式传 `config` 时，引擎自读 `<data_dir>/sylanne.config.json`——所有下游 `shared(data_dir)` 共享同一份用户可改配置（首启写入默认模板，显式传入的 `config=` 优先于文件）。顶层认识的键映射到 `SylanneConfig`，不认识的键忽略；缺失/损坏/取值非法均回退默认、引擎照常启动。配置在建引擎时读取，改动需重启生效。

```jsonc
{
    "mode": "lite",
    "assessor_enabled": true,
    // 可选：把语义评估交给一个小而便宜的模型；不填则用主 llm
    "assessor_model": {
        "api_base": "https://api.deepseek.com/v1",
        "api_key": "${SYLANNE_ASSESSOR_KEY}",   // 建议用环境变量，勿提交密钥
        "model": "deepseek-chat"
    }
}
```

`assessor_model` 块走任意 OpenAI 兼容 `/chat/completions` 接口（纯标准库实现，lite 档零依赖）。也可绕过文件、直接给 `SylanneEngine(...)` / `shared(...)` 传 `assessor_llm`（`async (system, user) -> str`）；二者皆无则评估回落主 `llm`。

---

## 8. Lifecycle / 生命周期

```mermaid
stateDiagram-v2
    init: init / 初始化
    running: running / 运行中
    degraded: degraded / 退化运行
    closed: closed / 已关闭

    init --> running : start()
    running --> closed : shutdown()
    running --> degraded : LLM/Embedding 失败
    degraded --> running : 恢复正常
    degraded --> closed : shutdown()
```

- **init / 初始化**：构造 SylanneEngine，验证参数
- **running / 运行中**：`start()` 后正常运行，LLM/Embedding 可用
- **degraded / 退化运行**：LLM 或 Embedding 不可用，本地回退运行
- **closed / 已关闭**：`shutdown()` 后引擎关闭，所有状态已写入磁盘

```python
await engine.start()       # init → running / 启动引擎
await engine.shutdown()    # → closed / 关闭引擎（刷写所有状态）
engine.status              # "init" | "running" | "degraded" | "closed"
```

---

## 9. Concurrency & Thread Safety / 并发与线程安全

- 同一 `session_id` 的调用自动串行化（内部锁）
- 不同 `session_id` 可并发处理
- `state()` 返回只读快照，不加锁
- 引擎实例线程安全，可在多个 asyncio task 中共享
