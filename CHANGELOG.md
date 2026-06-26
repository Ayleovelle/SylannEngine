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

- **PEL-Core（v2.5 预测编码情绪核，default-off）**：新增两层预测编码微电路
  `sylanne_core/compute/pel_core.py`——演化 8 维潜信念 `μ` 与情绪读出 `z`（下游写入
  `scar_state.base`），纯 Python（`math` + list-of-lists，无 numpy，lite 可用）、全 mypy-strict。
  K=2 自由能下降 + 三因子 surprise 门控的 `W_gen` 在线 Hebbian 可塑 + 在线精度 + 谱钳 ≤0.9；
  有界性与收缩为结构性保证（`μ,z∈[−1,1]^8` 前向不变，`‖J_μ‖₂≤1−αδ`）。
  - 新增 `SylanneConfig.pel_core_enabled` 开关，**默认 `False`**——关时引擎走遗留 `_evolve_base`，
    行为与此前逐字节一致（既有套件全绿、未改）；开时才跑 PEL，由其自有测试置位
  - **加性 `free_energy` 键（D-1）**：PEL 开启时 `result["resonance"]` 多一个有限的 `free_energy`
    诊断键；关闭时结果形状完全不变（无契约改动）
  - **非语义 `assessor_advisable` 门信号（D-10）**：经 `diagnostics()["pel"]` 暴露
    （低 surprise 且无创伤 => False，否则 True），连同 surprise/精度一并提供。SDK 只产出信号，
    不接任何下游 call-skip
  - 快照两条路径（`ResonanceSpine` / `ComputationSpine`）均往返 PEL 子键；旧档缺键时从人格重初始化
  - P3 消融扫测试（`tests/test_pel_ablation.py`）：`Pi_top→0` / `eta_W→0` / `ρ_p→0` 各产生可测变化，
    证明无机制是 no-op
  - **更脑 v2（在真流量上让脑机件活起来，仍 default-off）**：三个在线可塑机制，全在 `pel_core_enabled`
    之后、v2 默认 on-path、各自独立可消融，schema v1→v2（加 `pi0`/`theta`/`s_bar`，带 v1 回退）：
    - **M1 除法归一化精度**（Heeger 1992）：固定预算的竞争再分配（均值 1.0），解掉真 spine 上精度
      钉死 `[5.0]×8`（跨维 std≈0）的注意力死饱和——实测跨维 spread 0→~0.46。`PRECISION_DIVISIVE=False`
      与 committed 精度更新**逐位一致**；eta_w ×5 复原设计均值
    - **M2 BCM 式滑动阈元可塑增益**（Bienenstock+1982）：`m_i∈[0,2]` 按各维误差超阈与否调 Hebbian
      速率（不改方向），`θ_i=EMA(e0²)` ~100 拍自调；门见证用 m-spread + path-length
    - **M3 锚定 allostatic π**（Sterling 2012）：朝 ⟨z⟩ 漂的同时拉回冻结 trait 先验 `π0`，止住身份侵蚀
      （渐近保留 ~80% π0），凸更新前向不变
    - **生产见证**：`pel_diagnostics()` 暴露跨维精度 spread / 乘积 spread / `precision_live` / `pi_anchor_drift`，
      真流量上可窗口化告警——把"语料上活"变成"生产上死了能被发现"
    - 收缩/有界性闭式可证且红队实测复核（最坏 `‖J_μ‖₂=0.977<0.985`）；新增 merge-blocking 门 #13–#19
      （T-DIV / T-DIV-OFF / T-BCM / T-PROD / T-ANCHOR / T-SCHEMA / proof 守卫）+ surprise-gate 覆盖；
      `pel_core_enabled=False` 仍逐字节一致；快照恢复按 host flag gate（关时不偷开 PEL）
- `SylanneEngine.shared(data_dir, llm, ...)`：进程内按解析后的 data_dir 去重的共享实例机制，替代已删除的插件版 `get_engine()`。同一目录只由一个引擎拥有，避免状态分裂与 flush 丢更新；返回已 start 的引擎
- `SylanneEngine.release_shared(data_dir)`：关闭并释放共享实例（应用关闭时调用，会 flush 落盘）
- `SylanneEngine.is_shared(data_dir)` / `SylanneEngine.list_shared()`：内省接口，查当前进程里有哪些共享引擎在跑
- 冗余软护栏：直接 `SylanneEngine(...)` 构造时若目标 data_dir 已有活跃共享实例，记 warning 提示重复创建（不阻断）
- `SharedEngineConflictError`：同一 data_dir 以不同 config 获取共享实例时抛出
- **ResonanceSpine 接入 embodiment 人格漂移（canonical）**：`ResonanceSpine.process()` 现在
  在 return 前调用 `_drift_embodiment(result)`，与 `ComputationSpine` 同位语义。此前 ResonanceSpine
  （运行时默认 spine）虽已具备全部漂移基建字段，却从不触发漂移——基建就绪、接线缺失。补齐后
  AGENT_GUIDE「每次 process() 自动漂移」对默认 spine 成立。
- **对话质量自我进化（CP8-P4「越聊越校准」）端到端贯通**：agent 把回复质量自评经
  `process(..., values={"dialogue_quality": q})`（或 spine 层 `process(..., dialogue_quality=q)`）
  喂回，引擎据此漂移人格——质量高强化表达欲+拉近关系引力，质量低收敛表达欲。全程走 canonical
  自动漂移通道（`engine → kernel → spine.process → result → DriftSignalExtractor → _drift_embodiment`），
  无「第四写动词」后门。具体三层改动：
  - `DRIFT_SIGNALS` 新增 `dialogue_quality_high` / `dialogue_quality_low` 两条映射
  - `DriftSignalExtractor.extract()` 认 `result["dialogue_quality"]` → 产高/低信号
    （阈值 `_DIALOGUE_QUALITY_HIGH=0.7` / `_LOW=0.3`，中间区不触发）
  - 两个 spine 的 `process()` 加可选 `dialogue_quality` 入参；kernel 从 `values` 通道透传
  - 质量分是滞后反馈：对第 N 轮回复的评分在第 N+1 轮传入。不传时行为完全不变（默认 None）

### 🔧 Changed

- 文档（README / SPEC / AGENT_GUIDE / 架构文档）改为单一 SDK 安装与接入方式
- `release.yml` 不再打包 AstrBot 插件 zip，仅创建 GitHub Release
- Issue / PR 模板移除 AstrBot 插件专属字段

### 🔧 表达策略：硬闸人格显函数化（axiom A7）+ credit assignment 修正

`ExpressionPolicy` 的表达硬闸从死常数升级为人格显函数，并修正 contextual bandit 的
off-policy 信用分配。**默认行为逐 tick 不变、存档无损**——所有新参数均可选，缺省即旧行为。

- **T1 硬闸人格显函数化**：`_DRIVE_FORCE_EXPRESS=0.95`/`_DRIVE_FORCE_HOLD=0.1` 两处死常数
  （`expression_policy.decide()` 与 `resonance_integration` spine 覆盖点）改为实例字段
  `_force_express`/`_force_hold`，由 `set_personality(openness, expression_drive_trait,
  sovereignty_guard)` 派生：
  - `force_express = 1.05 − 0.20·expression_drive_trait`（中性 0.5 → 0.95）
  - `force_hold = 0.02 + 0.16·sovereignty_guard`（中性 0.5 → 0.10）
  - 单调性：表达欲越强越早强制开口；主权越强"懒得说"区越大。`force_express>1.0` 合法
    （该人格永不被强制开口）。spine 覆盖点改读 `force_express_threshold`/
    `force_hold_threshold` 属性，消灭第二份重复常数。
- **T2 credit assignment 接真实 action**：`update_from_feedback(..., actual_action=None)`
  与 `ResonanceSpine.feedback(..., actual_expressed=None)`——当表达决策由上层仲裁器拥有时，
  可告知真实执行的行动，让 bandit 为真正做过的选择领赏受罚（`None` 缺省=旧行为）。
  反馈总线其余五家消费者一律不动（纯透传）。
- **T3 强制决策不训练（可选）**：`update_from_feedback(..., skip_forced=False)`——置 True 时
  硬闸强制的样本只记 diagnostics、跳过梯度步，避免 policy 被自己没选的行动污染。缺省
  False 保留旧行为。新增 `last_decision_forced` 属性暴露上次决策是否走硬闸。
- **持久化**：`to_dict`/`from_dict` 新增 `force_express`/`force_hold` 可选键；旧档缺键回退
  legacy 常数（0.95/0.1），新档被旧版读取时多余键被忽略——三向往返不炸。
- **诊断**：`diagnostics()` 新增 `force_express`/`force_hold` 可观测。
- 测试：`tests/test_expression_policy_saddle.py`（23 例，覆盖中性锚定/单调性/真实 action
  梯度/强制不训练/存档往返/spine 接线）；存量全绿。

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

