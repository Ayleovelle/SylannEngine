# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [v1.0.0rc1] - 2026-06-01

### 🏗️ Architecture: Resonance Field

Complete architectural redesign — sequential 7-layer pipeline replaced by fully-connected simplicial resonance field:

- **441 directed coupling channels** (complete 6-simplex Δ⁶) with three-tier allocation: lite=42, pro=287, max=441
- **Hebbian plasticity**: channels strengthen with use, atrophy without (LTP + LTD + homeostatic scaling + neural Darwinism pruning)
- **Higher-order Kuramoto synchronization**: pairwise + 3-body (Millán 2020) + 4-body phase coupling with explosive sync transitions
- **Hopfield attractor landscape**: emotional memory as energy minima, expression fires as bifurcation (escaping attractor)
- **Harmonic identity ("soul")**: Hodge Laplacian null-space extraction, exponential moving average, restoring force preserves personality across perturbations
- **Echo state reservoir**: leaky-integrator temporal memory, fading history of past inputs
- **Free energy minimization** (Friston 2010): precision-weighted prediction error drives belief updates
- **Global Workspace broadcast** (Baars 1988): winner-take-all competition + ignition
- **Criticality feedback loop**: emergence metrics amplify coupling near phase transitions (self-organized criticality)
- **Expression as OR-gate bifurcation**: max(surprise, novelty, ignition, raw_drive) × Φ — any single strong signal triggers expression
- **Lossless tier hot-switching**: linear interpolation upgrade, average pooling downgrade, plasticity patterns inherited

### ✨ New Features

- `ResonanceSpine`: drop-in replacement for `ComputationSpine` with identical API (process/feedback/express/to_dict/from_dict)
- `switch_tier("pro")`: hot-switch between lite/pro/max without losing state
- Full personality → parameter mapping: 7 personality dimensions control all coupling/plasticity/field/expression parameters
- Emergence tracking: Φ (integrated information), χ (criticality), attractor count, temporal narrative, memory depth
- Improved Φ calculation: spatial correlation × temporal coherence (replaces naive variance ratio)

### 📝 Documentation

- `docs/resonance_field_spec.md`: formal mathematical specification (21 literature citations)
- `docs/resonance_field_architecture.md`: full architecture spec + developer integration guide (EN)
- `docs/resonance_field_architecture_zh.md`: same in Chinese
- `docs/max_tier_workflow.md`: MAX tier Mermaid computation flow diagram
- `docs/SPEC.md`: updated with resonance model, platform requirements, personality mapping table
- README: rewritten with resonance field explanation, mermaid diagrams, tier comparison

### 🧪 Testing

- 66 dedicated resonance field tests (topology, plasticity, Kuramoto, Hopfield, reservoir, identity, bifurcation, tier switching)
- 434 total tests passing, zero regressions

### ⚡ Performance

- lite tier: ~5ms/tick, 50+ concurrent sessions per core
- pro tier: ~40ms/tick (numpy accelerated)
- max tier: ~50ms/tick CPU, <5ms GPU (torch path structured but not yet implemented)

### 🔧 Configuration

- `concurrency_target` for lite raised from 5 to 50
- Plugin version locks to lite tier (pro/max for SDK only)
- Single codebase strategy: plugin vs SDK differ only in main.py presence + dependency declarations

---

## [v1.0.0a4] - 2026-05-31

(Previously labeled v1.0.0rc3)

### 💥 Breaking Changes

- 移除三层记忆系统（L1/L2/L3），Surface 输出不再包含 `memory` 字段
- 移除 `SylanneConfig.memory_capacity` 配置项

### 🐛 Bug Fixes

- 修复 `adapter._map_guard()` 读取 `constraints` 但 kernel 返回 `flags`
- 修复 `metadata.yaml` license 标识与 pyproject.toml 不一致
- 修复 `metadata.yaml` personality_impact 三项全部标错为 false

### 🔒 Robustness

- 添加 `terminate()` 方法：插件卸载/热重载时正确关闭引擎
- `initialize()` 添加防御性检查

## [v1.0.0a3] - 2026-05-31

(Previously labeled v1.0.0rc2)

### ⚡ Performance

- HDC similarity 从 O(n) 字节循环改为 O(1) `int.bit_count()`
- LLM assess 移出 session lock

### 🐛 Bug Fixes

- 修复 `confidence=0.0` 被 falsy 逻辑覆盖
- 修复 NaN/Inf 可穿透 kernel 事件解析
- 修复 `save_buffer()` 静默吞掉 OSError

### ✨ API Improvements

- 添加 `async with engine:` 上下文管理器
- 添加 `engine.exists(session_id)` 方法

## [v1.0.0a2] - 2026-05-31

(Previously labeled v1.0.0rc1)

### 🔒 Type Safety

- 全模块 mypy 零错误
- 修复 190 处类型标注缺失
- Release 打包改为 AstrBot 插件格式

## [v1.0.0a1] - 2026-05-31

### ✨ Initial Alpha

- 完整的 7 层情感计算管线
- 29 维身体状态向量，8 个子系统
- 双 EMA 人格漂移系统
- Void-Scar Engine / HDC / HGT 底层计算引擎
- 异步 `SylanneEngine` 高层 API
- 140 个单元测试
- GitHub Actions CI

## [v0.1.0-preview] - 2026-05-29

### Initial Preview Release

- 7 层情感计算管线原型
- 8 子系统情感状态模型
- 双层人格系统
- 三层记忆系统（后移除）
- LLM 语义评估器

