# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [v1.0.0rc3] - 2026-05-31

### 💥 Breaking Changes

- 移除三层记忆系统（L1/L2/L3），Surface 输出不再包含 `memory` 字段
- 移除 `SylanneConfig.memory_capacity` 配置项
- 记忆功能将由独立适配插件提供

### 🐛 Bug Fixes

- 修复 `adapter._map_guard()` 读取 `constraints` 但 kernel 返回 `flags`，导致 guard constraints 永远为空
- 修复 `metadata.yaml` license 标识与 pyproject.toml 不一致（`or-later` → `only`）
- 修复 `metadata.yaml` personality_impact 三项全部标错为 false

### 🔒 Robustness

- 添加 `terminate()` 方法：插件卸载/热重载时正确关闭引擎并清理共享实例
- `initialize()` 添加防御性检查：热重载时先关闭旧引擎再创建新实例

### 📝 Documentation

- README/SPEC/AGENT_GUIDE：`state`/`reset`/`destroy` 标注为 async
- README/SPEC/AGENT_GUIDE：添加 `exists()` 方法文档
- AGENT_GUIDE：补充缺失的 `reach_out` action
- SPEC 版本从 `0.1.0-draft` 更新为 `1.0.0rc3`
- `confidence` 默认值文档从 `0.0` 修正为 `None`
- 移除所有记忆系统相关文档

## [v1.0.0rc2] - 2026-05-31

### ⚡ Performance

- HDC similarity 从 O(n) 字节循环改为 O(1) `int.bit_count()` 单次操作
- 记忆召回预分词：query 只 tokenize 一次，避免 L1+L2 循环内重复计算
- LLM assess 移出 session lock，锁持有时间从"网络延迟+计算"降为"仅计算"

### 🐛 Bug Fixes

- 修复 `confidence=0.0` 被 falsy 逻辑覆盖导致 assessor 结果永远不生效
- 修复 `adapter._map_debug()` 引用错误属性名导致诊断输出永远为空
- 修复 NaN/Inf 可穿透 kernel 事件解析污染状态向量
- 修复 `save_buffer()` 静默吞掉 OSError

### 🔒 Robustness

- `state()`/`reset()`/`destroy()` 改为 async 并加 session lock 防止并发 torn read
- 添加生命周期守卫：shutdown 后调用 process/tick 自动重启引擎
- Session 文件名改用 percent-encoding 防止碰撞（如 `a/b` vs `a_b`）
- `SylanneConfig.__post_init__` 校验参数边界值

### ✨ API Improvements

- 添加 `async with engine:` 上下文管理器支持
- 添加 `engine.exists(session_id)` 方法
- `_notify()` listener 异常改为 `logger.warning` 并附带堆栈
- `Surface.dynamics` 从 `dict[str, Any]` 细化为 `Dynamics` TypedDict
- `ComputationSpine.embodiment_bounds()` 公开方法替代私有属性访问

### 🔧 Maintenance

- 提取共享 `safe_filename()` 到 `compute/utils.py` 消除重复
- 新增 filesystem safe session name 和 save_buffer 错误传播测试

## [v1.0.0rc1] - 2026-05-31

### 🔒 Type Safety

- 全模块 mypy 零错误（--check-untyped-defs）
- 修复 190 处类型标注缺失和 None 安全问题
- CI mypy 检查从 continue-on-error 升级为强制通过

### 🐛 Bug Fixes

- 修复 `ScarredState._mlp_weights` None 解引用风险
- 修复 `VoidSpace._split_pass` cluster_b 未做 None 检查
- 修复 `AlphaBodyState.from_dict` 类型推断不精确
- 修复 `importer` 模块 records 变量类型窄化失败

### 🔧 Maintenance

- 锁定 ruff==0.14.2 与 CI 版本一致
- Release 打包改为 AstrBot 插件格式（184KB vs 6MB）
- 引入 `_as_dict()` 辅助函数简化 kernel 反序列化

## [v1.0.0a1] - 2026-05-31

### ✨ New Features

- 完整的 7 层情感计算管线（body → personality → moral → fallibility → relational → decision → guard）
- 29 维身体状态向量，8 个子系统协同演化
- 双 EMA 人格漂移系统，支持 dt_scale 时间感知
- Void-Scar Engine / HDC / HGT 底层计算引擎
- 异步 `SylanneEngine` 高层 API（start/process/tick/shutdown）
- `SylanneAlphaHost` 中间层，支持持久化、快照、诊断
- `AlphaKernel` 核心调度器，带 circuit breaker 容错
- 会话运行时（Runtime）：原子写入、JSON 恢复、路径安全
- PEP 561 类型标记（py.typed）
- 事件监听器系统（sync/async listeners）

### 🧪 Testing

- 140 个单元测试覆盖全部核心模块
- pytest-asyncio 异步引擎测试
- GitHub Actions CI：Python 3.10-3.13 矩阵测试
- 性能回归检测（500 ticks < 10ms/tick）

### 🐛 Bug Fixes

- 修复 `_L1_PAYLOAD_FALLBACK` 共享可变字典污染 bug
- tick 异常时添加 fallback 日志记录

### 🔧 Maintenance

- ruff 0.14.2 格式化全部源码
- pyproject.toml 完整打包配置（hatchling）
- mypy non-strict 类型检查（CI continue-on-error）

## [v0.1.0-preview] - 2026-05-29

### Initial Preview Release

- 7 层情感计算管线（HDC → Gate → Absence-Impact → Relational → Fusion → Boundary → Expression）
- 8 子系统情感状态模型（rhythm/connection/adaptation/responsiveness/valence/damage/boundary/capacity）
- 双层人格系统（deep 5 维 + surface 6 维）
- 决策输出（7 种 action 类型）
- 边界守卫系统
- 三层记忆系统（L1 hot / L2 warm / L3 cold）
- LLM 语义评估器（带本地 fallback）
- 调试模式（断路器状态、各层耗时、健康检查）
- 完整标准规范文档（SPEC.md）
- 会话持久化（原子写入 + fsync）
- 退化运行策略（LLM 不可用时自动降级）
