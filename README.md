# SylannEngine

> 情感计算引擎 SDK — 为 AstrBot 插件开发者提供结构化的情感状态计算服务

**Status: v0.1.0-preview**

---

## 这是什么

SylannEngine 是一个纯计算引擎，其他 AstrBot 插件可以调用它来获取情感状态数据。

- 文本输入，结构化数据输出
- 不生成回复，不注入 prompt，不管消息收发
- 7 层计算管线，29 维状态向量，双层人格系统

## 快速开始

### 1. 安装

在 AstrBot 插件市场安装 `SylannEngine`，或从 Release 下载。

### 2. 在你的插件中调用

```python
from astrbot.api.star import Context, Star


class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._engine = None

    async def initialize(self):
        # 获取 SylannEngine 实例
        engine_star = self.context.get_registered_star("astrbot_plugin_sylannengine")
        if engine_star:
            self._engine = engine_star.star_instance

    async def on_message(self, event):
        if self._engine:
            # 调用计算引擎
            surface = await self._engine.process(
                session_id="user_123",
                text=event.message_str,
            )

            # 使用计算结果
            action = surface["decision"]["action"]   # express/withdraw/recover/...
            warmth = surface["state"]["valence"]["warmth"]
            fatigue = surface["state"]["responsiveness"]["fatigue"]
```

### 3. 健康检查

```python
health = self._engine.health()
# {"status": "running", "active_sessions": 3, ...}
```

## API 概览

| 方法 | 说明 |
|------|------|
| `await process(session_id, text, **ctx)` | 处理输入文本，返回完整计算结果 |
| `await tick(session_id, flags)` | 无文本的状态推进（时间衰减等） |
| `state(session_id)` | 查询当前状态（不触发计算） |
| `health()` | 引擎健康检查 |
| `reset(session_id)` | 重置会话 |

## 输出结构 (Surface)

```jsonc
{
    "schema_version": "sylanne.core.v1",
    "session_id": "user_123",
    "turns": 5,
    "state": {          // 8 子系统情感状态
        "rhythm": { "beat": 5.0, "stability": 0.6, "strain": 0.1 },
        "connection": { "warmth": 0.5, ... },
        "adaptation": { "plasticity": 0.3, ... },
        "responsiveness": { "readiness": 0.4, ... },
        "valence": { "warmth": 0.5, ... },
        "damage": { "open": 0.0, ... },
        "boundary": { "pressure": 0.1, "autonomy": 0.9, ... },
        "capacity": { "load": 0.2, ... },
        "needs": { "expression": 0.3, "quiet": 0.1, ... }
    },
    "personality": {    // 双层人格
        "deep": { "expression_drive": 0.5, ... },
        "surface": { "warmth_bias": 0.5, "curiosity": 0.6, ... }
    },
    "decision": {       // 决策输出
        "action": "express",  // express/withdraw/recover/reach_out/explore/hold/guard
        "reason": "...",
        "confidence": 0.75,
        "urgency": 0.3
    },
    "guard": { "allowed": true, "risk_score": 0.1 },
    "memory": { "recalled": [...], "total_stored": 42 }
}
```

完整字段定义见 [SPEC.md](SPEC.md)。

## 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `sylannengine_data_dir` | `./data/sylannengine` | 持久化目录 |
| `sylannengine_diagnostics` | `false` | 是否返回管线中间态和调试信息 |
| `sylannengine_locale` | `zh` | 语言 |

## 设计原则

- **被动接收**：只有插件调用 `process()` 推数据进来才会计算，不主动拉取任何数据
- **永不崩溃**：LLM 不可用时退化为本地规则引擎，Embedding 不可用时退化为关键词匹配
- **会话隔离**：每个 session_id 独立状态，互不干扰
- **零外部依赖**：计算引擎本身只依赖 Python 标准库

## 许可证

AGPL-3.0-or-later
