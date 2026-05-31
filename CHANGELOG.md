# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
