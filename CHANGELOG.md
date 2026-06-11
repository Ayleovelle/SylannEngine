# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### 💥 Breaking Changes

- 移除 AstrBot 前置插件形态。SylannEngine 现在是纯 SDK，直接 `SylanneEngine(...)` 实例化并传入自己的 LLM 回调
- 删除 `main.py`、`metadata.yaml`（AstrBot 插件入口与元数据）
- 移除 `sylanne_core.get_engine()` 与共享实例 `_shared_engine`——插件版专用的共享引擎获取方式不再提供
- 删除 `sdk` 镜像分支与 `sync-sdk.yml` 工作流：`main` 分支本身即 SDK

### ✨ Added

- `SylanneEngine.shared(data_dir, llm, ...)`：进程内按解析后的 data_dir 去重的共享实例机制，替代已删除的插件版 `get_engine()`。同一目录只由一个引擎拥有，避免状态分裂与 flush 丢更新；返回已 start 的引擎
- `SylanneEngine.release_shared(data_dir)`：关闭并释放共享实例（应用关闭时调用，会 flush 落盘）
- `SylanneEngine.is_shared(data_dir)` / `SylanneEngine.list_shared()`：内省接口，查当前进程里有哪些共享引擎在跑
- 冗余软护栏：直接 `SylanneEngine(...)` 构造时若目标 data_dir 已有活跃共享实例，记 warning 提示重复创建（不阻断）
- `SharedEngineConflictError`：同一 data_dir 以不同 config 获取共享实例时抛出

### 🔧 Changed

- 文档（README / SPEC / AGENT_GUIDE / 架构文档）改为单一 SDK 安装与接入方式
- `release.yml` 不再打包 AstrBot 插件 zip，仅创建 GitHub Release
- Issue / PR 模板移除 AstrBot 插件专属字段

## [v2.0.0] - 2026-06-01

SylannEngine V2 — 共振场架构正式版。完全重写计算核心，从顺序 7 层管线升级为单纯形共振场。

### 🏗️ 架构：共振场

完全架构重设计——顺序 7 层管线替换为全连接单纯形共振场：

- **441 条有向耦合通道**（完全 6-单纯形 Δ⁶）三档分配：lite=42, pro=287, max=441
- **Hebbian 可塑性**：通道用进废退（LTP + LTD + 稳态缩放 + 神经达尔文主义剪枝）
- **高阶 Kuramoto 同步**：两体 + 3 体（Millán 2020）+ 4 体相位耦合，爆炸性同步转变
- **Hopfield 吸引子景观**：情感记忆作为能量极小值，表达作为分岔（逃离吸引子）
- **谐波身份（"灵魂"）**：Hodge Laplacian 零空间提取，指数移动平均，恢复力跨扰动保持人格
- **回声状态储备池**：泄漏积分器时间记忆，过去输入的衰减历史
- **自由能最小化**（Friston 2010）：精度加权预测误差驱动信念更新
- **全局工作空间广播**（Baars 1988）：赢者通吃竞争 + 点火
- **临界性反馈环**：涌现指标在相变附近放大耦合（自组织临界性）
- **表达作为 OR 门分岔**：max(惊讶, 新颖性, 点火, 原始驱动) × Φ——任一强信号触发表达
- **无损档位热切换**：升级线性插值，降级平均池化，可塑性模式继承

### ✨ 新功能

- `ResonanceSpine`：`ComputationSpine` 的直接替代，API 完全兼容（process/feedback/express/to_dict/from_dict）
- `switch_tier("pro")`：lite/pro/max 间热切换不丢失状态
- 完整人格→参数映射：7 个人格维度控制所有耦合/可塑性/场/表达参数
- 涌现追踪：Φ（整合信息）、χ（临界性）、吸引子计数、时间叙事、记忆深度
- 改进的 Φ 计算：空间相关 × 时间连贯（替代朴素方差比）

### 📝 文档

- `docs/resonance_field_spec.md`：形式化数学规范（21 篇文献引用）
- `docs/resonance_field_architecture.md`：完整架构规范 + 开发者集成指南（英文）
- `docs/resonance_field_architecture_zh.md`：同上（中文）
- `docs/max_tier_workflow.md`：MAX 档 Mermaid 计算流程图
- `docs/SPEC.md`：更新共振模型、平台要求、人格映射表
- `docs/resonance_field_paper_en.tex`：学术论文（英文）
- `docs/resonance_field_paper_zh.tex`：学术论文（中文）
- README：重写，含共振场说明、Mermaid 图、档位对比

### 🧪 测试

- 66 个专用共振场测试（拓扑、可塑性、Kuramoto、Hopfield、储备池、身份、分岔、档位切换）
- 434 个测试全部通过，零回归

### 🔧 实验验证

- 11 项实验协议验证核心声明（收敛性、可塑性、同步、吸引子、表达、稳定性等）
- 每实验 1000+ tick × 10 次重复，统计检验
- 实验代码：`experiments/`

### ⚡ 性能

- lite 档：~5ms/tick，50+ 并发会话/核
- pro 档：~40ms/tick（numpy 加速）
- max 档：~50ms/tick CPU，<5ms GPU（torch 路径已结构化但未实现）

### 🔧 配置

- lite 的 `concurrency_target` 从 5 提升到 50
- 插件版锁定 lite 档（pro/max 仅 SDK）
- 单代码库策略：插件版与 SDK 版仅 main.py 存在与否 + 依赖声明不同

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

