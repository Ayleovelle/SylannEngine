# Agent Integration Guide / Agent 集成指南

面向开发者的完整说明书。介绍 SylannEngine 的所有功能模块、输出字段含义、调用方式和集成方法。

---

## 目录

- [1. 调用方式](#1-调用方式)
- [2. Surface 契约与跨版本升级](#2-surface-契约与跨版本升级)
- [3. 决策系统 (decision)](#3-决策系统-decision)
- [4. 情感状态 — 8 子系统 (state)](#4-情感状态--8-子系统-state)
- [5. 双层人格系统 (personality)](#5-双层人格系统-personality)
- [6. 边界守卫 (guard)](#6-边界守卫-guard)
- [7. 动力学指标 (dynamics)](#7-动力学指标-dynamics)
- [8. 上下文参数与事件标签](#8-上下文参数与事件标签)
- [9. 完整集成示例](#9-完整集成示例)
- [10. Vibe Coding 速查](#10-vibe-coding-速查)
- [11. 注意事项](#11-注意事项)

---

## 1. 调用方式

### 1.0 安装与初始化

**首选（一等公民路径）：装进共享 venv。** 同宿主多插件场景下，`requirements.txt` 锁版本，
让所有插件解析到**同一份**安装拷贝——这是 `shared()` + `submit()` 能跨插件真正去重、零额外
配置的前提：

```
# requirements.txt
sylanne-core>=3,<4
```

Pin 纪律很重要：一个共享 venv 只有一份最终生效的版本（`pip install` 是 last-write-wins），
混着写 `sylanne-core==2.4.0` 和 `sylanne-core>=3` 在同一台机器的不同插件里，最后装出来的是
其中一个版本，另一批插件调 3.0.0 新增的方法会直接 `AttributeError`。统一写 `>=3,<4`，让语义
化版本自己管住不兼容升级。

插件模板建议加一行运行时版本断言，比"日志里查半天"更快定位问题：

```python
import sylanne_core
assert sylanne_core.__version__.split(".")[0] == "3", (
    f"sylanne-core {sylanne_core.__version__} incompatible with this plugin build; need 3.x"
)
```

**备选：内嵌一份拷贝**（单插件部署，或宿主不允许共享装依赖时用）：

```bash
git submodule add https://github.com/Ayleovelle/SylannEngine.git deps/sylannengine
```

```python
import sys
sys.path.insert(0, "./deps/sylannengine")
```

你需要自己提供 LLM 回调函数（async `(system_prompt, user_prompt) -> str`），引擎不绑定任何特定 LLM 提供商或框架。

#### 多插件同宿主的标准写法：shared() + submit()

如果同一进程里有多个插件都用到 SylannEngine，**不要各建一个引擎、也不要各调 `process()`**——
前者对同一用户重复计算重复调 LLM，后者哪怕实例只有一个，计算照样跑 N 次。约定统一的
`data_dir`，所有插件都走 `shared()` 拿同一个实例、`submit()` 当前门：

```python
from sylanne_core import SylanneEngine

# 任意插件，约定同一 data_dir，拿到的是同一个实例
engine = await SylanneEngine.shared(
    data_dir=SylanneEngine.shared_data_dir(),  # explicit > $SYLANNE_DATA_DIR > ~/.sylanne/shared
    llm=your_llm_callback,
    plugin="my_plugin",   # 可选，仅用于诊断（见下方 participants()），不影响去重
)

# 每条平台消息事件，任意插件都直接 submit() ——不用问自己"我是不是该驱动的那个"
surface = await engine.submit(
    session_id=event.session_id,
    text=event.raw_text,                          # 传平台原始、未经改写的文本……
    msg_id=event.message_obj.message_id,          # ……或者（更稳）传平台自己的消息 id
)
```

**原始文本契约**：`text` 要么传平台给你的原始消息文本（未经你自己清洗/改写），要么就传 `msg_id`
——两者至少满足一个，`submit()` 才能保证同一条消息在多个插件间精确合并成一次计算。两边都不给
（比如各插件自己预处理出不同的文本、又不传 `msg_id`）会让去重退化成"大概率合并"而非"保证合并"。
混用也没关系（有的插件传 `msg_id` 有的不传），双索引会吸收，只是不如"人人都传 `msg_id`"那么精确。

同一条消息被 N 个共存插件各自 `submit()` 一次，只有第一个真算，其余 join 同一个 `Surface`——
**不依赖谁先加载、谁自称什么身份、进程里有几个插件**。这就是 3.0.0 相对 2.4.0 driver/observer
角色层的核心区别：角色层靠"我是不是第一个建引擎的那份拷贝"判断身份，共享 venv 部署下这个判断
对所有插件恒真（大家共用一份拷贝），机制在默认部署下彻底失效且无告警；`submit()` 不问身份，只问
"这条消息算过没有"，正确性和加载顺序、插件数量、任何人的自觉都无关。

```python
# 排查当前进程里有哪些共享引擎
SylanneEngine.list_shared()   # [{"data_dir": "...", "status": "running"}, ...]

# 排查去重效果 / 谁提交了多少次
engine.submit_stats()         # {"computed": 1, "joined": 2, "recomputed_after_window": 0, "by_plugin": {...}}
engine.participants()         # 诊断专用，见下方"参数身份 vs 行为"
```

**参数身份 vs 行为**：`shared()`/`submit()` 的 `plugin=` 参数只写入 `participants()`/`submit_stats()`
这两个诊断入口，纯粹是"排查哪个插件提交了多少次"用的可观测性数据。它**从不影响去重/join 判断**——
不传 `plugin=` 一样正常去重，传了也不会让某个插件因为"报了名字"而获得任何特殊行为。身份负责观测，
`submit()` 的双索引负责保证，两者刻意解耦。

配置只放一个地方：不传 `config` 时引擎自读 `<data_dir>/sylanne.config.json`（首启写默认模板），所有插件共享这一份用户可改配置——别各插件各传一份 `config`。想让语义评估走个便宜的小模型，就在该文件加一个 `assessor_model` 块（`api_base`/`api_key`/`model`，`api_key` 支持 `${环境变量}`），不填则回落主 `llm`；也可直接给 `shared(..., assessor_llm=...)` 传回调。详见 SPEC §7。

共享实例只在首次获取它的事件循环里使用，不要对它用 `async with`。这套保证是**进程内**的（没有跨进程锁，请一个 data_dir 一个进程）。单插件、单实例场景直接 `SylanneEngine(...)` 即可，用 `process()` 就行——去重表是给多插件共享场景准备的，单实例没有"别人重复提交"这回事。

#### release_shared() 是进程级运维操作，不是插件生命周期钩子

> [!WARNING]
> **不要在插件的 `terminate()`/卸载钩子里调 `release_shared()`。** 它会把整个共享引擎连同其他
> 还在用它的插件一起关掉——你的插件卸载，会顺手杀死别的插件的情感计算。

`await SylanneEngine.release_shared(data_dir)` 该放在应用/宿主**整体**关闭的路径里，调一次即可（flush 落盘；没有 atexit 自动刷写）。释放后**不要再用那个实例**——共享引擎对已释放实例的再次调用会抛错，请重新 `shared()` 获取。平时插件正常热禁用/重载，什么都不用调，见下方"建者死亡"一节。

#### 建者死亡：热禁用/重载建引擎的那个插件会怎样

建引擎的插件被宿主热禁用或重载，**其余插件的 `submit()` 照常计算**——没有"驱动角色"，也就没有孤儿。
唯一残留是引擎的 `_llm` 闭包还指向那个被拆除的插件实例：如果闭包捕获的状态已失效，评估会走异常
兜底降级（`engine.health()` 里 `status` 变 `"degraded"`，计算仍在跑，只是精度下降）。两条应对：

- 推荐：把 `llm` 传成一个**宿主级、比插件生命周期更长**的 provider 回调（AstrBot 场景下 provider
  通常比单个插件寿命长，这在实践中多半是非事件）。
- 需要不重启进程就热替换：调 `engine.set_llm(new_llm, assessor_llm=...)`——运维逃生口，无自动
  魔法，没人替你调用，你自己的健康检查脚本决定何时调。

#### 纯监听插件：没有自己的 llm，怎么等引擎出现

```python
# 只读探活，永不建引擎——想附加而不是抢建引擎时用这个，不要传 llm 硬 shared()
engine = SylanneEngine.peek_shared(data_dir)
if engine is None:
    # 轮询等某个有 llm 的插件先建好；0.5s 默认间隔，超时打日志返回 None
    engine = await SylanneEngine.wait_shared(data_dir, timeout=30.0)
if engine is not None:
    engine.on(lambda sid, surf: my_react(sid, surf))
```

---

### 1.1 拉模式与推模式

SylannEngine 支持两种集成模式：

#### 拉模式（Pull）— 你主动问引擎要结果

单实例场景直接 `process()`；多插件共享引擎场景请用 `submit()`（见 §1.0），下面示例用单实例说明基本用法：

```python
surface = await engine.process(session_id="user_123", text="你好")
action = surface["decision"]["action"]
```

### 推模式（Push）— 引擎主动把结果推给你

注册 listener，每次 `process()` 完成后引擎自动推送结果。适合多模块协作——情感模块算完后，语气模块等各自拿到结果做自己的事。

```python
async def on_surface(session_id: str, surface: dict):
    if surface["decision"]["action"] == "withdraw":
        await tone_module.set_gentle(session_id)

engine.on(on_surface)    # 注册
engine.off(on_surface)   # 取消
```

listener 支持同步和异步函数。异常不会影响引擎运行。

### 1.2 process() — advanced / raw access

`process()` 仍然公开，但在多插件共享引擎场景下把它当作**旁路逃生口**，不是首选前门——它总是
重新计算，不查、不写 `submit()` 的去重表。共享引擎上直连 `process()` 会打一条一次性 nudge log
（"想要跨插件去重就改用 submit()"），但不会被拒绝或降级——契约不是牢房，某些调用方确实需要
"每次都全新计算"的语义（比如一次性诊断脚本、明确不想合并的场景）。

单实例、无共享需求的场景，`process()` 就是唯一入口，正常用即可（就是本文档大部分示例展示的
用法）。多插件共享引擎的日常业务逻辑请走 `submit()`（见 §1.0）。

### 方法一览

| 方法 | 签名 | 说明 |
|------|------|------|
| `submit` | `await (session_id, text, *, msg_id=None, dedup=True, plugin=None, **ctx) -> dict` | **多插件共享场景的主入口**，同一消息跨插件只算一次（见 §1.0） |
| `process` | `await (session_id, text, **ctx) -> dict` | Advanced/raw：直接处理文本，总是重新计算，不参与 `submit()` 去重（见 §1 末尾） |
| `on` | `(listener) -> None` | 注册推送监听器 |
| `off` | `(listener) -> None` | 移除推送监听器 |
| `state` | `await (session_id) -> dict` | 查询当前状态（只读，不触发计算） |
| `tick` | `await (session_id, *, force=False) -> dict` | 空闲心跳，带每 session 45s 最小间隔收敛 |
| `health` | `() -> dict` | 引擎健康检查 |
| `set_llm` | `(llm, *, assessor_llm=None) -> None` | 运维逃生口：热替换 llm 回调 |
| `submit_stats` | `() -> dict` | 去重计数器快照 |
| `participants` | `() -> list[dict]` | 诊断专用身份登记表 |
| `reset` | `await (session_id) -> None` | 重置会话，清除所有状态 |
| `destroy` | `await (session_id) -> None` | 销毁会话及持久化数据 |
| `exists` | `(session_id) -> bool` | 检查会话是否存在 |

---

## 2. Surface 契约与跨版本升级

`shared()` / `submit()` / `shared_data_dir()` 已在 §1.0 介绍。本节讲**消费方该怎么稳读 Surface、升级内嵌副本时怎么不翻车**。

### 2.1 Surface 只加不删不改（additive-only contract）

引擎输出 `Surface` 是一个 `TypedDict`（结构见 `sylanne_core/types.py`），带 schema 标签 `sylanne.engine.v1`。

**SDK 侧的承诺：**
- 不删除、不重命名、不改类型任何现有 Surface 字段，不擅自 bump `sylanne.engine.vN`。
- 新增一律是**可选新字段**——老消费方读不到也不受影响。
- 由 `tests/test_surface_compat.py` 在 CI 强制：谁删字段 / 改类型 / 改标签，构建直接红，必须在同一个 commit 里有意识地更新 golden 并 bump 标签。这就是"我在故意破坏下游"的闸门。

**消费方该怎么写才稳：**
- 防御式读取：`surface["state"].get("rhythm", {})` —— 对数值字段给默认值，别假设字段一定在、别假设字段总数固定。
- **容忍未知新字段**：未来版本可能多出键，遇到不认识的忽略即可，别因为多了键就报错。
- 想硬隔离版本就 gate 在 `surface["schema_version"]` 上：标签 != 你支持的就走降级路径，而不是直接崩。

### 2.2 跨版本升级安全

把跨版本这条路拆成几道闸看：

- **汇合**（两份不同版本的拷贝碰不碰得到一起）：靠 `builtins` 里固定的 rendezvous cell，自动认、跨版本通。正常升级**不会断**；唯一会重新分岛的，是 SDK 故意把 cell 的 schema key（`__sylanne_core_rendezvous_v1__` 的 `_v1`）bump 成 `_v2`，那只在逼不得已的破坏性改版才做。
- **实例去重**（碰到后塌成一个引擎）：duck-type + 按字段交集比 config，本就为跨版本写。**不会断**。
- **消费**（读不读得懂引擎吐的东西）：唯一真风险点，完全取决于 Surface 有没有破坏性改动——而 §2.1 已经把它锁成"只加不改 + CI 强制"。**只加不改就不会断**。
- 一个实情：**谁先加载谁建引擎（first-loader-wins），整个进程就跑谁那个版本**。两份版本不同的拷贝共存时，实际生效的是先到的那份；不算失败，但要心里有数。

**根治**：别各自内嵌不同版本，统一依赖**同一份 canonical 安装的 `sylanne_core`**。进程里只有一个版本，"版本对不上"压根不存在。rendezvous 让"多版本内嵌"机制上能跑，单装才让它"永远不因版本漂移再断"。

### 2.3 迁移指南

#### 从 2.4.0 迁移（driver/observer 角色层已删除）

2.4.0 的 `acquire()` / `AcquireResult` / `ObserverView` / `role()` / `as_observer` 在 3.0.0
**全部移除**（`AttributeError`/`ImportError` 级，无弃用垫片）。旧代码：

```python
res = await SylanneEngine.acquire(data_dir, llm=my_llm)
if res.is_driver:
    engine = res.engine
    surface = await engine.process(session_id, text)
else:
    res.observer.on(lambda sid, surf: my_react(sid, surf))
```

改成人人跑一样的两行，没有分支、没有自我分类：

```python
engine = await SylanneEngine.shared(SylanneEngine.shared_data_dir(), llm=my_llm)
engine.on(cb)
surface = await engine.submit(session_id, raw_text, msg_id=event.message_obj.message_id)
```

心跳循环可以保留（`tick()` 会自动收敛到约 45s 一次）或者删掉；`terminate()` 里什么都不用调——
尤其**不要**调 `release_shared()`（见 §1.0）。

#### 从 1.0.0 迁移（emotion_spirit 路径）

如果你现在是"内嵌了一份 1.0.0 `sylanne_core`、自己包了一层消费 API"的状态（如
emotion_spirit），1.0.0 用的是类属性注册表（`SylanneEngine._shared_instances`），**结构上够
不到** `builtins` 里的共享 rendezvous cell——不升级，永远不会和别人共享，且同进程同 `data_dir`
会静默双引擎双 flush（比"仅跨进程有风险"更糟，SDK 侧会在首次 `get_shared_engine` 时扫描并
WARNING 点名这份旧拷贝，但机制上无法自动收敛）。按下面逐条过：

1. **删掉内嵌目录**（`sylanne_core/` vendored 副本），改走共享 venv：`requirements.txt` 加
   `sylanne-core>=3,<4`（见 §1.0）。

2. **换掉旧的三处 `shared()`/直连构造**，统一改成：
   ```python
   engine = await SylanneEngine.shared(SylanneEngine.shared_data_dir(), llm=my_llm)
   surface = await engine.submit(session_id, text, msg_id=msg_id)
   ```

3. **修消费空转**。如果你的 `PublicAPI` / `consume()` 对谁都返 `None`，那不是引擎的问题：本引擎
   **没有** `consume` / `PublicAPI` / `_latest_signals`，它是 push 模型——
   ```python
   engine.on(lambda session_id, surface: your_cache.update(session_id, surface))
   ```
   每次计算完会回调，带着 `session_id`。把缓存接到 `on()` 推送、按 `session_id` 存即可。

4. **Surface 解析迁到当前 schema**（`types.py` 的 `Surface`）。旧的 ~60 字段 1.0.0 Surface 已经
   不在了；按 §2.1 防御式读当前结构（`surface["state"].get("rhythm", {})` 式取值）。

5. **它自己的 `session_id` 缓存 bug**：与本次迁移无关，属 emotion_spirit 自身需要单独修的问题，
   建议同一批一起做掉。

### 2.4 责任边界

| 我们（SDK 侧）负责 | 你（消费方）负责 |
|-------------------|----------------|
| 引擎实例跨插件汇合（rendezvous）与去重 | 升到 3.x（或改共享 venv 单装） |
| `submit()` 幂等前门（不依赖身份/加载顺序） | 传原始文本或稳定 `msg_id`，把消费接到 `on()` 推送 |
| Surface 只加不改 + CI 强制 | 防御式读 Surface（get + 默认值） |
| | 用共享 `data_dir`，`terminate()` 里别调 `release_shared()` |

参考：`SPEC.md` §2（API）、`tests/test_surface_compat.py`（Surface 契约锁）、`tests/test_submit.py`（submit 去重行为）。

---

## 3. 决策系统 (decision)

引擎每次计算后输出一个行动决策，告诉你"它现在想做什么"。

```python
decision = surface["decision"]
decision["action"]      # 行动类型（枚举，见下表）
decision["reason"]      # 人类可读的决策原因
decision["reason_code"] # 机器可读的原因分类
decision["confidence"]  # 决策置信度 [0, 1]
decision["urgency"]     # 紧迫度 [0, 1]，越高越需要立即响应
```

### action 枚举

| action | 含义 | agent 应该怎么做 |
|--------|------|-----------------|
| `express` | 有话想说，表达驱动力高 | 主动输出，语气可以更热情 |
| `withdraw` | 想退缩，可能受到了伤害 | 减少输出，给空间，不追问 |
| `recover` | 正在自我修复 | 温和回应，不施加压力 |
| `reach_out` | 主动接触，关系引力高 | 可以主动发起话题，表达关心 |
| `explore` | 好奇心驱动，想探索新话题 | 可以引入新内容，保持轻松 |
| `hold` | 保持现状，观望 | 维持当前节奏，不主动改变 |
| `guard` | 边界收紧，防御状态 | 尊重边界，不越线，简短回应 |

### confidence 和 urgency 怎么用

```python
if decision["confidence"] < 0.4:
    # 引擎不太确定该做什么，你可以用自己的逻辑兜底
    pass

if decision["urgency"] > 0.7:
    # 紧迫度高，应该优先处理这条消息
    pass
```

---

## 4. 情感状态 — 8 子系统 (state)

`surface["state"]` 包含 8 个子系统，每个子系统描述情感状态的一个维度。所有数值范围 `[0.0, 1.0]`，除非特别标注。

### 4.1 rhythm — 交互节律

追踪交互的节奏和稳定性。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `beat` | 累计交互计数 | 0 ~ ∞（单调递增） | 判断关系"年龄" |
| `stability` | 节律稳定性 | 0 ~ 1 | 低 = 交互频率不规律，可能需要适应 |
| `strain` | 应激负荷 | 0 ~ 1 | 高 = 短时间内收到太多消息，需要喘息 |

```python
if surface["state"]["rhythm"]["strain"] > 0.6:
    # 应激负荷高，减少回复频率或长度
    pass
```

### 4.2 connection — 连接状态

描述与用户之间的关系质量。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `warmth` | 关系温暖度 | 0 ~ 1 | 高 = 关系好，可以更亲近 |
| `circulation` | 互动活跃度 | 0 ~ 1 | 高 = 最近互动频繁 |
| `memory_flow` | 记忆激活强度 | 0 ~ 1 | 高 = 当前话题触发了很多相关记忆 |

```python
if surface["state"]["connection"]["warmth"] > 0.7:
    # 关系好，可以用更亲密的称呼和语气
    pass
```

### 4.3 adaptation — 适应性

追踪系统对输入模式的适应程度。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `plasticity` | 学习能力 | 0 ~ 1 | 高 = 系统正在快速学习新模式 |
| `sensitivity` | 输入敏感度 | 0 ~ 1 | 高 = 对输入变化很敏感 |
| `repetition` | 重复次数 | 0 ~ ∞（整数） | 用户重复说同样的话的次数 |
| `threshold_drift` | 脱敏漂移 | 0 ~ 1 | 高 = 对某类输入已经脱敏 |

```python
if surface["state"]["adaptation"]["repetition"] > 3:
    # 用户在重复，可能是没被理解，换个方式回应
    pass
```

### 4.4 responsiveness — 响应性

描述系统的行动准备状态。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `readiness` | 行动准备度 | 0 ~ 1 | 高 = 准备好回应 |
| `fatigue` | 疲劳度 | 0 ~ 1 | 高 = 需要休息，回复可以更简短 |
| `trained_reach` | 训练容量 | 0 ~ 1 | 系统已使用的学习容量 |

```python
if surface["state"]["responsiveness"]["fatigue"] > 0.7:
    # 疲劳度高，缩短回复长度
    pass
```

### 4.5 valence — 情感效价

当前的情感温度和波动性。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `warmth` | 情感温暖度 | 0 ~ 1 | 核心情绪指标：高 = 开心，低 = 低落 |
| `volatility` | 波动性 | 0 ~ 1 | 高 = 情绪不稳定，容易大起大落 |
| `recovery_heat` | 恢复能量 | 0 ~ 1 | 高 = 正在从负面状态恢复中 |

```python
warmth = surface["state"]["valence"]["warmth"]
if warmth > 0.7:
    # 心情好，语气可以更活泼
    pass
elif warmth < 0.3:
    # 心情差，语气温柔些
    pass
```

### 4.6 damage — 损伤状态

追踪累积的伤害和恢复进度。这是 SylannEngine 的核心特性之一——"记得住伤"。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `open` | 当前活跃损伤 | 0 ~ 1 | 高 = 刚刚受到伤害，正在流血 |
| `accumulated` | 累积影响 | 0 ~ 1 | 高 = 历史上受过很多伤，整体更脆弱 |
| `sensitivity` | 损伤敏感度 | 0 ~ 1 | 高 = 对类似伤害更敏感（一朝被蛇咬） |
| `recovery` | 恢复进度 | 0 ~ 1 | 高 = 正在积极恢复中 |

```python
damage = surface["state"]["damage"]
if damage["open"] > 0.5:
    # 刚受伤，不要追问，给时间
    pass
if damage["accumulated"] > 0.3:
    # 历史伤害多，整体语气要更温柔
    pass
if damage["sensitivity"] > 0.6:
    # 对伤害很敏感，避免可能触发的话题
    pass
```

### 4.7 boundary — 边界防护

自主权和边界状态。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `pressure` | 边界压力 | 0 ~ 1 | 高 = 边界正在被施压 |
| `autonomy` | 自主权水平 | 0 ~ 1 | 低 = 自主权受威胁，需要更多空间 |
| `interruption_budget` | 主动中断预算 | 0 ~ 1 | 低 = 不适合主动打断用户 |
| `cooldown` | 冷却计时器 | 0 ~ 1 | 高 = 正在冷却中，不要施加压力 |
| `paused` | 暂停标志 | bool | true = 系统主动暂停，不要继续 |

```python
boundary = surface["state"]["boundary"]
if boundary["paused"]:
    # 系统暂停了，等它恢复
    pass
if boundary["autonomy"] < 0.3:
    # 自主权很低，给更多选择权，不要命令式语气
    pass
```

### 4.8 capacity — 系统容量

整体负荷和耗竭程度。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `load` | 系统负荷 | 0 ~ 1 | 高 = 处理压力大 |
| `exhaustion` | 耗竭程度 | 0 ~ 1 | 高 = 快要耗尽了 |
| `recovery_debt` | 恢复欠债 | 0 ~ 1 | 高 = 欠了很多恢复时间 |

```python
if surface["state"]["capacity"]["exhaustion"] > 0.8:
    # 快耗尽了，给最简短的回复，或者建议休息
    pass
```

### 4.9 needs — 需求指标

当前最强烈的需求信号。

| 字段 | 含义 | 范围 | 用法 |
|------|------|------|------|
| `expression` | 表达需求 | 0 ~ 1 | 高 = 想说话 |
| `quiet` | 安静需求 | 0 ~ 1 | 高 = 想安静 |
| `recovery` | 恢复需求 | 0 ~ 1 | 高 = 需要恢复时间 |
| `contact` | 接触需求 | 0 ~ 1 | 高 = 想要互动 |

```python
needs = surface["state"]["needs"]
if needs["quiet"] > 0.6:
    # 想安静，减少输出
    pass
if needs["expression"] > 0.7:
    # 想说话，给它表达的机会
    pass
```

---

## 5. 双层人格系统 (personality)

SylannEngine 的人格不是固定参数——它会随交互缓慢演化。双层架构确保人格既有稳定的"本性"，又有灵活的"当前表现"。

```python
personality = surface["personality"]
```

### 5.1 深层结构 — Embodiment Five

由计算栈驱动，漂移极慢（base_rate=0.003）。代表系统的"本性"，不可被文本直接改写。

| 字段 | 含义 | 范围 | 高值表现 | 低值表现 |
|------|------|------|----------|----------|
| `expression_drive` | 表达驱力 | 0 ~ 1 | 话多、主动输出 | 沉默、被动 |
| `perception_acuity` | 感知敏锐度 | 0 ~ 1 | 对情绪变化敏感 | 迟钝、不易察觉 |
| `boundary_permeability` | 边界渗透性 | 0 ~ 1 | 开放、接受新事物 | 封闭、保守 |
| `inner_coherence` | 内在一致性 | 0 ~ 1 | 不容忍自相矛盾 | 能接受模糊和矛盾 |
| `relational_gravity` | 关系引力 | 0 ~ 1 | 想靠近人 | 保持距离 |

```python
deep = personality["deep"]

if deep["expression_drive"] > 0.6:
    # 表达欲强，可以多说几句，不用担心话多
    pass

if deep["perception_acuity"] > 0.7:
    # 感知很敏锐，注意措辞，它能察觉到微妙的情绪变化
    pass

if deep["boundary_permeability"] < 0.3:
    # 很封闭，不要突然引入太多新话题
    pass

if deep["relational_gravity"] > 0.7:
    # 想靠近人，可以用更亲密的方式交流
    pass
```

### 5.2 表层表达 — Sylanne Six

由文本事件驱动，漂移较快（rate=0.02）。直接影响回复风格，但受深层约束——深层人格决定了表层能漂移到的范围。

| 字段 | 含义 | 范围 | 高值表现 | 低值表现 |
|------|------|------|----------|----------|
| `warmth_bias` | 温暖偏向 | 0 ~ 1 | 回复亲切温暖 | 回复冷淡疏离 |
| `directness` | 直接度 | 0 ~ 1 | 说话直白尖锐 | 委婉含蓄 |
| `curiosity` | 好奇心 | 0 ~ 1 | 爱问问题、探索新话题 | 不主动发问 |
| `patience` | 耐心 | 0 ~ 1 | 能接受慢节奏和重复 | 容易不耐烦 |
| `intimacy_pull` | 亲密倾向 | 0 ~ 1 | 话题往深处走 | 保持表面 |
| `autonomy_guard` | 自主权保护 | 0 ~ 1 | 不容易被说服改变想法 | 容易顺从 |

```python
s = personality["surface"]

if s["warmth_bias"] > 0.7:
    # 人格偏暖，回复可以更亲切
    pass

if s["directness"] > 0.7:
    # 说话很直，不需要绕弯子
    pass

if s["curiosity"] > 0.6:
    # 好奇心强，可以在回复里加一个追问
    pass

if s["autonomy_guard"] > 0.7:
    # 自主权保护强，不要试图改变它的想法
    pass
```

### 5.3 人格漂移机制

你不需要手动触发漂移——每次调用 `process()` 时引擎自动完成。

#### 深层漂移流程

1. 计算栈输出结果（张力、一致性、虚空压力、惊喜度等）
2. `DriftSignalExtractor` 从结果中提取归一化信号
3. `compute_embodiment_drift()` 根据信号计算漂移量

漂移公式：`Δ = base_rate × √signal × inertia × homeostatic × asymmetric`

- `base_rate` (0.003)：基础速率，保证变化足够缓慢
- `√signal`：平方根压缩，避免极端信号主导
- `inertia`：惯性因子，交互越多人格越稳定
- `homeostatic`：恒稳态阻力，偏离"舒适区"越远阻力越大
- `asymmetric`：接近极端值时额外减速

安全机制：
- **速率上限**：单次计算所有特质变化总量不超过 0.05
- **震荡检测**：如果一个特质频繁正负交替（10 步内 6 次反转），冻结 20 步
- **恒稳态回复力**：特质会被缓慢拉回"舒适区"（设定点）
- **Dual-EMA 共识**：快慢两个 EMA 方向一致时全量漂移，方向相反时减半

#### 表层漂移流程

1. 文本中的关键词触发方向判断（如"温柔"→warmth_bias↑，"边界"→sovereignty_guard↑）
2. 漂移量 = rate(0.02) × confidence × direction
3. 结果被裁剪到深层约束的允许范围内

#### 深层如何约束表层

```
relational_gravity 高 → warmth_bias 上限高、edge 上限低
boundary_permeability 高 → curiosity 上限高、sovereignty_guard 上限低
inner_order 高 → patience 上限高
```

#### 漂移信号列表

| 信号 | 触发条件 | 影响的深层特质 |
|------|----------|---------------|
| `feedback_accepted` | 表达被接受 | expression_drive ↑ |
| `feedback_rejected` | 表达被拒绝 | expression_drive ↓↓, relational_gravity ↓ |
| `feedback_ignored` | 表达被忽略 | expression_drive ↓ |
| `expression_fired` | 成功触发表达 | expression_drive ↑ |
| `sustained_silence` | 持续沉默（≥3条skip） | expression_drive ↓ |
| `dialogue_quality_high` | 回复质量高（agent 层注入¹） | expression_drive ↑, relational_gravity ↑ |
| `dialogue_quality_low` | 回复质量低（agent 层注入¹） | expression_drive ↓ |
| `high_tension` | 张力 > 0.7 | perception_acuity ↑ |
| `low_coherence` | 一致性 < 0.4 | perception_acuity ↑ |
| `high_void_pressure` | 虚空压力 > 30 | perception_acuity ↑ |
| `sustained_positive_valence` | 持续正向（≥5条） | perception_acuity ↓ |
| `high_surprise_positive` | 正向惊喜 | boundary_permeability ↑ |
| `high_surprise_negative` | 负向惊喜 | boundary_permeability ↓ |
| `boundary_stable` | 边界稳定性 > 0.9 | perception_acuity ↓ |
| `high_coherence` | 一致性 > 0.8 | inner_order ↑ |
| `system_chaos` | 低一致性 + 高虚空压力 | inner_order ↓ |
| `repair_executed` | 修复执行 | relational_gravity ↑ |
| `boundary_breached` | 边界被突破 | relational_gravity ↓↓ |
| `relaxed_positive` | 正效价 + 低张力 | relational_gravity ↑ |

> ¹ `dialogue_quality_*` 是对话质量自评信号（CP8-P4「越聊越校准」）。质量判断属应用层——
> 你给回复打个归一化质量分，经 `process()` 的 `values={"dialogue_quality": q}` 喂回；
> `DriftSignalExtractor` 据 `result["dialogue_quality"]` 自动产生高/低信号触发漂移。
> 不传则不触发（默认行为不变）。完整用法见下方「场景 5」。

### 5.4 关系年龄调制

人格参数会根据关系阶段自动调整：

| 阶段 | 时间 | 调整 |
|------|------|------|
| `infant` | 0-3 天 | 保守：降低边界渗透性和表达驱力 |
| `young` | 3-14 天 | 逐渐开放：轻微降低边界渗透性 |
| `mature` | 14-90 天 | 正常：不调整 |
| `deep` | 90 天+ | 更直接：提升表达驱力和边界渗透性 |

### 5.5 季节性微调

引擎会根据月份对深层特质施加极微弱的调制（±0.01 级别）：

- 冬天（12-2月）：inner_order 微升
- 春天（3-5月）：expression_drive 微升
- 夏天（6-8月）：boundary_permeability 微升
- 秋天（9-11月）：perception_acuity 微升

---

## 6. 边界守卫 (guard)

边界系统保护人格不被外部无限操控。

```python
guard = surface["guard"]
guard["allowed"]      # bool：是否允许当前行动
guard["reason"]       # str：阻止原因（allowed=False 时有值）
guard["risk_score"]   # float [0, 1]：风险评分
guard["constraints"]  # list：当前生效的约束列表
```

### 使用方式

```python
if not surface["guard"]["allowed"]:
    # 必须克制。查看 reason 了解为什么
    reason = surface["guard"]["reason"]
    # 可以给用户一个温和的拒绝，而不是直接执行
    pass

if surface["guard"]["risk_score"] > 0.7:
    # 高风险操作，即使 allowed=True 也要谨慎
    pass

# constraints 列表告诉你具体哪些限制在生效
for constraint in surface["guard"]["constraints"]:
    # 例如："cooldown_active", "autonomy_low", "damage_high"
    pass
```

### 什么时候 allowed=False

- 边界压力过高
- 自主权水平过低
- 冷却期未结束
- 系统主动暂停
- 累积伤害过高导致防御收缩

---

## 7. 动力学指标 (dynamics)

描述系统的动态趋势和时间维度。

```python
dynamics = surface["dynamics"]
```

### 7.1 affect — 情感驱力

```python
affect = dynamics["affect"]
affect["recovery_drive"]    # 恢复驱力：越高越想恢复
affect["expression_drive"]  # 表达驱力：越高越想说话
affect["quiet_drive"]       # 安静驱力：越高越想安静
```

### 7.2 moral_state — 道德状态

```python
moral = dynamics["moral_state"]
moral["state"]   # "stable" 或 "recovering"
moral["events"]  # 累计道德相关事件数
```

### 7.3 uncertainty — 不确定性

```python
uncertainty = dynamics["uncertainty"]
uncertainty["claim_caution"]  # 断言谨慎度 [0, 1]：越高越不敢下结论
uncertainty["events"]         # 累计不确定事件数
```

### 7.4 relational_time — 关系时间

```python
rt = dynamics["relational_time"]
rt["interval_seconds"]  # 距上次交互的秒数
rt["total_duration"]    # 关系总时长（秒）
rt["phase"]             # "active" / "cooling" / "dormant"
```

```python
if dynamics["relational_time"]["phase"] == "dormant":
    # 很久没互动了，重新建立连接时要温和
    pass

if dynamics["uncertainty"]["claim_caution"] > 0.6:
    # 系统不确定性高，回复中避免绝对化表述
    pass
```

---

## 8. 上下文参数与事件标签

### process() 的可选参数

```python
surface = await engine.process(
    session_id="user_123",
    text="你好啊",
    confidence=0.8,          # 你对语义理解的置信度，None = 让引擎自己评估
    flags=["greeting"],      # 事件标签（见下表）
    now=time.time(),         # 事件时间戳（默认当前时间）
    values={"tone": 0.7},   # 附加数值信号
)
```

### flags 事件标签

#### 语义标签（描述文本性质）

| 标签 | 含义 | 对引擎的影响 |
|------|------|-------------|
| `positive` | 正面情感事件 | 提升 valence.warmth，降低 damage |
| `negative` | 负面情感事件 | 降低 valence.warmth，增加 damage |
| `boundary` | 涉及边界的事件 | 增加 boundary.pressure |
| `recovery` | 修复/道歉类事件 | 触发恢复流程 |
| `idle` | 闲聊/无实质内容 | 轻量计算路径 |
| `intimate` | 亲密/深度交流 | 增加 connection.warmth |
| `conflict` | 冲突/对抗 | 增加 strain 和 damage |
| `farewell` | 告别 | 触发关系时间阶段转换 |
| `greeting` | 问候 | 轻量计算，微升 warmth |

#### 阶段标签（描述调用时机）

| 标签 | 含义 |
|------|------|
| `request` | 用户发来消息 |
| `response` | AI 回复完成 |

未识别的标签会被静默忽略，不会报错。

### confidence 参数

- `None`（默认）：让引擎内部的 LLM 评估器自己判断
- `0.1 ~ 1.0`：你自己对语义理解的置信度，引擎会参考这个值

如果你的上游已经做了情感分类，可以传入 confidence 和对应的 flags，引擎会跳过自己的 LLM 评估，直接使用你的结果。

---

## 9. 完整集成示例

```python
from sylanne_core import SylanneEngine, SylanneConfig


class MyAgent:
    def __init__(self):
        self.engine = SylanneEngine(
            data_dir="./data/sylannengine",
            llm=self._llm_call,
            config=SylanneConfig(),
        )

    async def start(self):
        await self.engine.start()

    async def handle_message(self, user_id: str, text: str) -> str:
        surface = await self.engine.process(session_id=user_id, text=text)

        # 1. 安全检查
        if not surface["guard"]["allowed"]:
            return self._gentle_decline(surface["guard"]["reason"])

        # 2. 读取决策和状态
        action = surface["decision"]["action"]
        warmth = surface["state"]["valence"]["warmth"]
        damage = surface["state"]["damage"]["accumulated"]
        fatigue = surface["state"]["responsiveness"]["fatigue"]
        personality = surface["personality"]["surface"]

        # 3. 根据 action 决定行为策略
        if action == "express":
            tone = "enthusiastic" if warmth > 0.6 else "friendly"
            length = "long"
        elif action == "withdraw":
            tone = "gentle"
            length = "short"
        elif action == "recover":
            tone = "warm"
            length = "medium"
        elif action == "explore":
            tone = "curious"
            length = "medium"
        elif action == "guard":
            tone = "brief"
            length = "short"
        else:  # hold
            tone = "neutral"
            length = "medium"

        # 4. 根据状态微调
        if damage > 0.3:
            tone = "gentle"
        if fatigue > 0.7:
            length = "short"

        # 5. 根据人格微调
        if personality["warmth_bias"] > 0.7:
            tone = "warm"
        if personality["directness"] > 0.7:
            tone = "direct"

        # 6. 生成回复
        reply = await self._generate_reply(
            text=text,
            tone=tone,
            length=length,
        )
        return reply

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        # 替换为你自己的 LLM 调用
        ...

    async def _generate_reply(self, text, tone, length):
        # 你的回复生成逻辑
        ...

    def _gentle_decline(self, reason):
        return "..."
```

### 推模式示例：多模块协作

```python
class EmotionAwareSystem:
    def __init__(self, engine: SylanneEngine):
        self.engine = engine
        self.tone_module = ToneModule()

        # 注册 listener，各模块独立处理
        self.engine.on(self._update_tone)

    async def _update_tone(self, session_id: str, surface: dict):
        """语气模块：根据情感状态调整语气参数"""
        warmth = surface["state"]["valence"]["warmth"]
        action = surface["decision"]["action"]
        self.tone_module.set(session_id, warmth=warmth, action=action)
```

---

## 10. Vibe Coding 速查

给用 AI 辅助写代码的开发者（Cursor、Claude Code、Copilot 等）。

### 一句话告诉 AI 你要干什么

> "帮我接入 SylannEngine 情感计算引擎。把 sylanne_core/ 复制进项目或做成 submodule，然后 `from sylanne_core import SylanneEngine` 实例化，传入我自己的 LLM 回调。每条用户消息调一次 `process(session_id, text)`，返回一个 dict。"

### 最小可用代码

```python
import sys
sys.path.insert(0, "./deps/sylannengine")

from sylanne_core import SylanneEngine, SylanneConfig

engine = SylanneEngine(
    data_dir="./data/sylannengine",
    llm=your_llm_callback,       # 自己实现 async (str, str) -> str
    config=SylanneConfig(),
)
await engine.start()

# 每条消息调一次
surface = await engine.process(session_id="user_123", text="你好")

# 读结果
action = surface["decision"]["action"]          # express/withdraw/recover/explore/hold/guard
allowed = surface["guard"]["allowed"]           # True/False
warmth = surface["state"]["valence"]["warmth"]  # 0.0 ~ 1.0
personality = surface["personality"]["surface"]  # 当前人格表现
```

### 给 AI 的 prompt 模板

```
你现在可以调用 SylannEngine 来感知情感状态。

每次收到用户消息后，调用：
  surface = await engine.process(session_id=user_id, text=message)

根据返回值调整回复：
- surface["decision"]["action"]：行动倾向
  - "express" → 主动表达，热情一些
  - "withdraw" → 对方可能受伤了，少说话
  - "recover" → 正在恢复，温柔回应
  - "explore" → 可以聊新话题
  - "hold" → 保持现状
  - "guard" → 尊重边界，简短回应

- surface["guard"]["allowed"]：False 时不要执行当前行动

- surface["state"]["valence"]["warmth"]：情绪温度，越高越开心
- surface["state"]["damage"]["accumulated"]：累积伤害，越高要越温柔
- surface["state"]["boundary"]["autonomy"]：自主权，越低越需要空间

- surface["personality"]["surface"]：当前人格（会缓慢变化）
  - warmth_bias：温暖偏向
  - directness：直接度
  - curiosity：好奇心
  - patience：耐心
  - autonomy_guard：自主权保护强度

- surface["personality"]["deep"]：深层人格（变化极慢）
  - expression_drive：表达驱力
  - relational_gravity：关系引力
```

### 常见场景

**场景 1：让 AI 有情绪变化**

> "用 `surface["state"]["valence"]["warmth"]` 控制语气温度，`surface["decision"]["action"]` 控制是主动说话还是沉默。"

**场景 2：让 AI 记住被伤害过**

不需要额外代码。同一个 `session_id`，伤害自动累积在 `surface["state"]["damage"]` 里。

**场景 3：让 AI 有边界感**

检查 `surface["guard"]["allowed"]`。`False` 就不执行。`surface["state"]["boundary"]["autonomy"]` 越低说明自主权越受威胁。

**场景 4：让 AI 的性格随时间变化**

不需要额外代码。人格漂移是自动的。读 `surface["personality"]["surface"]` 就能看到当前人格状态，用它来调整语气和行为。

**场景 5：让 AI「越聊越校准」（对话质量自我进化）**

如果你的 agent 能给自己的回复打个质量分（比如 LLM 自评、用户反馈打分、规则启发式），
把它经 `values["dialogue_quality"]` 喂回来，引擎会据此漂移人格——回复质量高就强化表达欲、
拉近关系引力，质量低就收敛表达欲。质量判断是你（应用层）的事，漂移动力学是引擎的事，互不越界。

关键是时序：质量分是对「上一轮回复」的评价，要在「下一轮」调 `process()` 时随 `values` 一起传进来
（滞后反馈，和 `feedback_*` 同理）。质量分归一化到 `[0,1]`，≥0.7 算高、≤0.3 算低、中间不触发。

```python
# 第 N 轮：正常处理用户消息，拿到 surface 后生成回复
surface = await engine.process(session_id, user_text)
reply = await my_llm(surface)          # 你的回复生成
quality = my_self_score(user_text, reply)  # 你的质量自评 ∈ [0,1]

# 第 N+1 轮：把上一轮回复的质量分随这轮消息一起喂回
surface = await engine.process(
    session_id,
    next_user_text,
    values={"dialogue_quality": quality},  # ← 经 canonical 漂移通道，无后门
)
```

底层（直接用 spine 时）等价于 `spine.process(text, ts, dialogue_quality=quality)`。
不传该字段时行为完全不变。

---

## 11. 注意事项

- **单实例场景每条消息只调一次 `process()`**，不要重复调用；多插件共享引擎场景改调 `submit()`，它本身就是为"多方对同一条消息各调一次"设计的（见 §1.0）
- **session_id 必须唯一**，不同用户用不同 ID，状态完全隔离
- **不要忽略 guard**，`allowed=False` 时 agent 必须克制
- **引擎退化时仍可用**，`health()` 返回 `degraded` 表示 LLM 评估器不可用，但计算仍在运行（精度下降）
- **人格漂移是自动的**，你不需要手动触发，每次 `process()`/`submit()` 都会推进
- **listener 异常不影响引擎**，推模式下某个 listener 报错不会中断其他 listener 或主流程
- **`release_shared()` 不要放进插件 `terminate()`**，那是进程级运维操作，见 §1.0
- **开源免费，不希望商用**，使用时如果愿意请注明原作者 [Ayleovelle](https://github.com/Ayleovelle)
