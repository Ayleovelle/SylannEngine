# Agent Integration Guide / Agent 集成指南

本文档面向 AI agent 开发者，说明如何调用 SylannEngine 并根据计算结果调整 agent 行为。

---

## 1. 何时调用

| 场景 | 调用方法 | 说明 |
|------|----------|------|
| 收到用户消息 | `await engine.process(session_id, text)` | 主入口，每条消息调一次 |
| 查询当前状态（不触发计算） | `engine.state(session_id)` | 只读，不改变内部状态 |
| 检查引擎健康 | `engine.health()` | 返回 status / degraded 信息 |
| 重置会话 | `engine.reset(session_id)` | 清除该用户的所有状态 |

---

## 2. 读懂 Surface 输出

`process()` 返回一个 dict，结构如下：

```python
surface = await engine.process(session_id, text)

# 核心字段
surface["decision"]["action"]      # 当前行动倾向
surface["decision"]["confidence"]  # 置信度 0-1
surface["decision"]["urgency"]     # 紧迫度 0-1
surface["state"]                   # 8 子系统状态
surface["guard"]["allowed"]        # 边界是否允许行动
surface["guard"]["risk_score"]     # 风险评分 0-1
```

### 2.1 action 含义与建议响应

| action | 含义 | agent 应该怎么做 |
|--------|------|-----------------|
| `express` | 有话想说，表达驱动力高 | 主动输出，语气可以更热情 |
| `withdraw` | 想退缩，可能受到了伤害 | 减少输出，给空间，不追问 |
| `recover` | 正在自我修复 | 温和回应，不施加压力 |
| `explore` | 好奇心驱动，想探索新话题 | 可以引入新内容，保持轻松 |
| `hold` | 保持现状，观望 | 维持当前节奏，不主动改变 |
| `guard` | 边界收紧，防御状态 | 尊重边界，不越线，简短回应 |

### 2.2 用 guard 做安全检查

```python
if not surface["guard"]["allowed"]:
    # 边界不允许当前行动，应该克制
    # 查看 surface["guard"]["constraints"] 了解具体限制
    pass

if surface["guard"]["risk_score"] > 0.7:
    # 高风险，谨慎行事
    pass
```

### 2.3 用 state 调整语气

```python
warmth = surface["state"]["valence"]["warmth"]       # 情感温度
damage = surface["state"]["damage"]["accumulated"]   # 累积伤害
boundary = surface["state"]["boundary"]["autonomy"]  # 自主权

if warmth > 0.7:
    # 状态好，可以更活泼
    pass
elif damage > 0.3:
    # 受过伤，语气温柔些
    pass
elif boundary < 0.3:
    # 自主权低，可能被过度干预了，给更多空间
    pass
```

---

## 3. 传入上下文参数

```python
surface = await engine.process(
    session_id="user_123",
    text="你好啊",
    confidence=0.8,          # 你对语义理解的置信度，0 = 让引擎自己评估
    flags=["greeting"],      # 事件标签
    values={"tone": 0.7},   # 附加数值信号
)
```

### flags 可用标签

| 标签 | 含义 |
|------|------|
| `positive` | 正面情感事件 |
| `negative` | 负面情感事件 |
| `boundary` | 涉及边界的事件 |
| `recovery` | 修复/道歉类事件 |
| `idle` | 闲聊/无实质内容 |
| `intimate` | 亲密/深度交流 |
| `conflict` | 冲突/对抗 |
| `farewell` | 告别 |
| `greeting` | 问候 |

---

## 4. 完整集成示例

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

        # 1. 安全检查：边界是否允许行动
        if not surface["guard"]["allowed"]:
            return self._minimal_response(surface["guard"]["reason"])

        # 2. 读取决策
        action = surface["decision"]["action"]
        confidence = surface["decision"]["confidence"]
        urgency = surface["decision"]["urgency"]

        # 3. 读取情感状态
        warmth = surface["state"]["valence"]["warmth"]
        damage = surface["state"]["damage"]["accumulated"]
        fatigue = surface["state"]["responsiveness"]["fatigue"]

        # 4. 根据 action 决定行为策略
        if action == "express":
            tone = "enthusiastic" if warmth > 0.6 else "friendly"
            should_initiate = True
        elif action == "withdraw":
            tone = "gentle"
            should_initiate = False
        elif action == "recover":
            tone = "warm"
            should_initiate = False
        elif action == "explore":
            tone = "curious"
            should_initiate = True
        elif action == "guard":
            tone = "brief"
            should_initiate = False
        else:  # hold
            tone = "neutral"
            should_initiate = False

        # 5. 根据状态微调
        if damage > 0.3:
            tone = "gentle"
        if fatigue > 0.7:
            tone = "brief"

        # 6. 生成回复（你自己的逻辑）
        reply = await self._generate_reply(
            text=text,
            tone=tone,
            should_initiate=should_initiate,
            urgency=urgency,
        )
        return reply

    async def _llm_call(self, system_prompt: str, user_prompt: str) -> str:
        # 替换为你自己的 LLM 调用
        ...

    async def _generate_reply(self, text, tone, should_initiate, urgency):
        # 你的回复生成逻辑
        ...

    def _minimal_response(self, reason):
        return "..."
```

---

## 5. 注意事项

- **每条消息只调一次 `process()`**，不要重复调用
- **session_id 必须唯一**，不同用户用不同 ID，状态完全隔离
- **不要忽略 guard**，如果 `allowed=False`，agent 应该克制行动
- **引擎退化时仍可用**，`health()` 返回 `degraded` 表示 LLM 评估器不可用，但计算仍在运行（精度下降）

---

## 6. Vibe Coding 集成速查 / 给 AI 辅助开发者的快速指南

如果你正在用 AI 辅助写代码（Cursor、Claude Code、Copilot 等），把下面的内容直接丢给你的 AI 助手就行。

### 一句话告诉 AI 你要干什么

> "帮我接入 SylannEngine 情感计算引擎。它是一个纯 SDK，我 `from sylanne_core import SylanneEngine` 然后传入 LLM 回调就行。每条用户消息调一次 `process(session_id, text)`，返回一个 dict，里面有 `decision.action`（行动倾向）和 `guard.allowed`（是否允许行动）。"

### 最小可用代码（复制即用）

```python
from sylanne_core import SylanneEngine, SylanneConfig

engine = SylanneEngine(
    data_dir="./data/sylannengine",
    llm=your_llm_callback,       # async (system_prompt, user_prompt) -> str
    config=SylanneConfig(),
)
await engine.start()

# 每条消息调一次
surface = await engine.process(session_id="user_123", text="你好")

# 读结果
action = surface["decision"]["action"]       # express/withdraw/recover/explore/hold/guard
allowed = surface["guard"]["allowed"]        # True/False
warmth = surface["state"]["valence"]["warmth"]  # 0.0 ~ 1.0
```

### 给 AI 的 prompt 模板

把这段加到你的 system prompt 或 AI 助手的上下文里：

```
你现在可以调用 SylannEngine 来感知用户的情感状态。

每次收到用户消息后，调用：
  surface = await engine.process(session_id=user_id, text=message)

根据返回值调整你的回复：
- surface["decision"]["action"] 告诉你当前应该做什么
  - "express" → 主动表达，可以热情一些
  - "withdraw" → 对方可能受伤了，少说话，给空间
  - "recover" → 正在恢复，温柔回应
  - "explore" → 可以聊新话题
  - "hold" → 保持现状
  - "guard" → 尊重边界，简短回应

- surface["guard"]["allowed"] 如果是 False，不要执行当前行动

- surface["state"]["valence"]["warmth"] 越高越开心，越低越低落
- surface["state"]["damage"]["accumulated"] 越高说明受过越多伤，要更温柔
```

### 常见 vibe coding 场景

**场景 1：我想让 AI 角色有情绪变化**

告诉你的 AI 助手：
> "用 SylannEngine 的 `surface["state"]["valence"]["warmth"]` 控制语气温度，`surface["decision"]["action"]` 控制是主动说话还是沉默。"

**场景 2：我想让 AI 记住被伤害过**

不需要额外代码，SylannEngine 自动追踪。只要你每次都传同一个 `session_id`，伤害会累积在 `surface["state"]["damage"]` 里。

**场景 3：我想让 AI 有边界感，不被用户随意操控**

检查 `surface["guard"]["allowed"]`。如果是 `False`，就不执行用户要求的行动。`surface["state"]["boundary"]["autonomy"]` 越低说明自主权越受威胁。
