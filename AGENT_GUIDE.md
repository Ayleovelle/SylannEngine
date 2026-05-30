# Agent Integration Guide / Agent 集成指南

面向开发者的完整说明书。介绍 SylannEngine 的所有功能模块、输出字段含义、调用方式和集成方法。

---

## 目录

- [1. 调用方式](#1-调用方式)
- [2. 决策系统 (decision)](#2-决策系统-decision)
- [3. 情感状态 — 8 子系统 (state)](#3-情感状态--8-子系统-state)
- [4. 双层人格系统 (personality)](#4-双层人格系统-personality)
- [5. 边界守卫 (guard)](#5-边界守卫-guard)
- [6. 记忆系统 (memory)](#6-记忆系统-memory)
- [7. 动力学指标 (dynamics)](#7-动力学指标-dynamics)
- [8. 上下文参数与事件标签](#8-上下文参数与事件标签)
- [9. 完整集成示例](#9-完整集成示例)
- [10. Vibe Coding 速查](#10-vibe-coding-速查)
- [11. 注意事项](#11-注意事项)

---

## 1. 调用方式

### 1.0 安装与初始化

SylannEngine 有两种使用方式，选择适合你的：

#### 插件版（推荐）— 通过 AstrBot 插件系统安装

在 AstrBot WebUI 安装 SylannEngine 前置插件后，你的插件里直接 import。

由于 AstrBot 不支持插件依赖声明，建议在你的插件启动时加一段检测：

```python
try:
    from sylanne_core import SylanneEngine, SylanneConfig
except ImportError:
    raise RuntimeError(
        "缺少前置插件 SylannEngine，请先安装：\n"
        "AstrBot WebUI → 插件 → 从 Git 仓库安装 → "
        "https://github.com/Ayleovelle/SylannEngine.git"
    )
```

完整示例：

```python
from astrbot.api.star import Context, Star, register
from sylanne_core import SylanneEngine, SylanneConfig


@register("my_plugin", "Author", "desc", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._engine = SylanneEngine(
            data_dir="./data/sylannengine",
            llm=self._llm_call,
            config=SylanneConfig(),
        )

    async def initialize(self):
        await self._engine.start()

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.context.provider_manager.text_chat(
            prompt=user_prompt, system_prompt=system_prompt,
        )
        return response.completion_text
```

前置插件安装地址：`https://github.com/Ayleovelle/SylannEngine.git`

#### SDK 版 — 直接嵌入你的项目

用 `sdk` 分支作为 submodule 或直接复制 `sylanne_core/` 目录：

```bash
git submodule add -b sdk https://github.com/Ayleovelle/SylannEngine.git deps/sylannengine
```

```python
import sys
sys.path.insert(0, "./deps/sylannengine")

from sylanne_core import SylanneEngine, SylanneConfig

engine = SylanneEngine(
    data_dir="./data/sylannengine",
    llm=your_llm_callback,  # async (system_prompt, user_prompt) -> str
    config=SylanneConfig(),
)
await engine.start()
```

SDK 版需要你自己提供 LLM 回调函数，不依赖 AstrBot。

---

### 1.1 拉模式与推模式

SylannEngine 支持两种集成模式：

#### 拉模式（Pull）— 你主动问引擎要结果

```python
surface = await engine.process(session_id="user_123", text="你好")
action = surface["decision"]["action"]
```

### 推模式（Push）— 引擎主动把结果推给你

注册 listener，每次 `process()` 完成后引擎自动推送结果。适合多模块协作——情感模块算完后，语气模块、记忆模块各自拿到结果做自己的事。

```python
async def on_surface(session_id: str, surface: dict):
    if surface["decision"]["action"] == "withdraw":
        await tone_module.set_gentle(session_id)

engine.on(on_surface)    # 注册
engine.off(on_surface)   # 取消
```

listener 支持同步和异步函数。异常不会影响引擎运行。

### 方法一览

| 方法 | 签名 | 说明 |
|------|------|------|
| `process` | `await (session_id, text, **ctx) -> dict` | 主入口，处理文本并返回完整计算结果 |
| `on` | `(listener) -> None` | 注册推送监听器 |
| `off` | `(listener) -> None` | 移除推送监听器 |
| `state` | `(session_id) -> dict` | 查询当前状态（只读，不触发计算） |
| `health` | `() -> dict` | 引擎健康检查 |
| `reset` | `(session_id) -> None` | 重置会话，清除所有状态 |
| `destroy` | `(session_id) -> None` | 销毁会话及持久化数据 |

---

## 2. 决策系统 (decision)

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

## 3. 情感状态 — 8 子系统 (state)

`surface["state"]` 包含 8 个子系统，每个子系统描述情感状态的一个维度。所有数值范围 `[0.0, 1.0]`，除非特别标注。

### 3.1 rhythm — 交互节律

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

### 3.2 connection — 连接状态

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

### 3.3 adaptation — 适应性

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

### 3.4 responsiveness — 响应性

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

### 3.5 valence — 情感效价

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

### 3.6 damage — 损伤状态

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

### 3.7 boundary — 边界防护

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

### 3.8 capacity — 系统容量

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

### 3.9 needs — 需求指标

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

## 4. 双层人格系统 (personality)

SylannEngine 的人格不是固定参数——它会随交互缓慢演化。双层架构确保人格既有稳定的"本性"，又有灵活的"当前表现"。

```python
personality = surface["personality"]
```

### 4.1 深层结构 — Embodiment Five

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

### 4.2 表层表达 — Sylanne Six

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

### 4.3 人格漂移机制

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

### 4.4 关系年龄调制

人格参数会根据关系阶段自动调整：

| 阶段 | 时间 | 调整 |
|------|------|------|
| `infant` | 0-3 天 | 保守：降低边界渗透性和表达驱力 |
| `young` | 3-14 天 | 逐渐开放：轻微降低边界渗透性 |
| `mature` | 14-90 天 | 正常：不调整 |
| `deep` | 90 天+ | 更直接：提升表达驱力和边界渗透性 |

### 4.5 季节性微调

引擎会根据月份对深层特质施加极微弱的调制（±0.01 级别）：

- 冬天（12-2月）：inner_order 微升
- 春天（3-5月）：expression_drive 微升
- 夏天（6-8月）：boundary_permeability 微升
- 秋天（9-11月）：perception_acuity 微升

---

## 5. 边界守卫 (guard)

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

## 6. 记忆系统 (memory)

三层记忆架构：L1（热）→ L2（温）→ L3（冷）。

```python
memory = surface["memory"]
memory["recalled"]       # list：本次召回的相关记忆
memory["total_stored"]   # int：当前会话总记忆条数
```

### 召回的记忆结构

```python
for mem in surface["memory"]["recalled"]:
    mem["text"]        # str：记忆内容
    mem["relevance"]   # float [0, 1]：与当前输入的相关度
    mem["created_at"]  # float：创建时间戳（Unix epoch）
    mem["layer"]       # str："L1" / "L2" / "L3"
```

### 三层含义

| 层 | 名称 | 特点 |
|----|------|------|
| L1 | 热记忆 | 最近的、高相关的，快速召回 |
| L2 | 温记忆 | 经过整合的中期记忆 |
| L3 | 冷记忆 | 长期存储，召回需要更强的触发 |

### 使用方式

```python
recalled = surface["memory"]["recalled"]
if recalled:
    # 有相关记忆被激活，可以在回复中引用
    top_memory = recalled[0]
    if top_memory["relevance"] > 0.8:
        # 高度相关，值得在回复中提及
        pass
```

记忆的写入是自动的——每次 `process()` 都会自动存储。你不需要手动管理。

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
    confidence=0.8,          # 你对语义理解的置信度，0 = 让引擎自己评估
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

- `0.0`（默认）：让引擎内部的 LLM 评估器自己判断
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
            recalled_memories=surface["memory"]["recalled"],
        )
        return reply

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        # 替换为你自己的 LLM 调用
        ...

    async def _generate_reply(self, text, tone, length, recalled_memories):
        # 你的回复生成逻辑
        ...

    def _gentle_decline(self, reason):
        return "..."
```

### 推模式示例：多模块协作

```python
class EmotionAwareSystem:
    def __init__(self):
        self.engine = SylanneEngine(data_dir="./data", llm=self._llm)
        self.tone_module = ToneModule()
        self.memory_module = MemoryModule()

        # 注册多个 listener，各模块独立处理
        self.engine.on(self._update_tone)
        self.engine.on(self._update_memory_context)

    async def _update_tone(self, session_id: str, surface: dict):
        """语气模块：根据情感状态调整语气参数"""
        warmth = surface["state"]["valence"]["warmth"]
        action = surface["decision"]["action"]
        self.tone_module.set(session_id, warmth=warmth, action=action)

    async def _update_memory_context(self, session_id: str, surface: dict):
        """记忆模块：把召回的记忆注入上下文"""
        recalled = surface["memory"]["recalled"]
        if recalled:
            self.memory_module.inject(session_id, recalled)
```

---

## 10. Vibe Coding 速查

给用 AI 辅助写代码的开发者（Cursor、Claude Code、Copilot 等）。

### 一句话告诉 AI 你要干什么

> "帮我接入 SylannEngine 情感计算引擎。如果我用 AstrBot，先安装前置插件 `https://github.com/Ayleovelle/SylannEngine.git`，然后 `from sylanne_core import SylanneEngine`。如果不用 AstrBot，用 sdk 分支做 submodule。每条用户消息调一次 `process(session_id, text)`，返回一个 dict。"

### 最小可用代码

**插件版**（已通过 AstrBot 安装前置插件）：

```python
from sylanne_core import SylanneEngine, SylanneConfig

engine = SylanneEngine(
    data_dir="./data/sylannengine",
    llm=self._llm_call,          # 通过 AstrBot provider_manager
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

**SDK 版**（submodule 或复制 sylanne_core/）：

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

surface = await engine.process(session_id="user_123", text="你好")
```
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

---

## 11. 注意事项

- **每条消息只调一次 `process()`**，不要重复调用
- **session_id 必须唯一**，不同用户用不同 ID，状态完全隔离
- **不要忽略 guard**，`allowed=False` 时 agent 必须克制
- **引擎退化时仍可用**，`health()` 返回 `degraded` 表示 LLM 评估器不可用，但计算仍在运行（精度下降）
- **人格漂移是自动的**，你不需要手动触发，每次 `process()` 都会推进
- **记忆写入是自动的**，你不需要手动存储
- **listener 异常不影响引擎**，推模式下某个 listener 报错不会中断其他 listener 或主流程
- **开源免费，禁止商用**，本引擎以 AGPL-3.0 开源，任何商业用途未获授权
