# v2.5 PEL-Core — 产品需求文档 (PRD)

> Predictive-Embodied Limbic Core。一个有目标函数、在线可塑、人格即吸引子、闭式可证有界的预测编码情绪核，
> 取代固定 `seed=42` 收缩 MLP（`scar_algebra.py:_evolve_base`）作为每拍情绪状态 `scar_state.base ∈ [-1,1]^8` 的演化机制。
>
> 状态：设计定稿（来自 workflow `wu5xap48p`：6 顶刊范式 → 3 对立设计 → 各红队 → 综合 → 完整性批判 → 首席对抗复核）。等用户拍 D-1…D-9 后进 P0。
> 配套：[v25-pel-core-design.md](v25-pel-core-design.md)（技术设计）、[v25-pel-core-techspec.md](v25-pel-core-techspec.md)（技术规格/推导/测试矩阵）。

---

## 1. 背景与问题陈述 (Why)

### 1.1 现状

v2 的核心机制"共振场"（ResonanceField）已被判失败并在运行期换成一个确定性兜底（`DeterministicFusion`）。
但情绪状态 `base ∈ [-1,1]^8` 的**逐拍演化**至今仍由 `scar_algebra.py:_evolve_base`（定义 :276，调用 :402）承担：
一个 `seed=42` 的、谱归一（`‖W1‖·‖W2‖ < 0.49`）的**随机固定收缩 MLP**，有界性仅来自末层 `tanh`（:304）。权重随机、不学习、无目标。

### 1.2 共振场的三宗罪（本设计必须正面修掉，benchmark 实测）

| # | 罪 | 证据 | 后果 |
|---|---|---|---|
| 1 | **对输入零敏感 / 锁死** | 默认 lite 档稳态 Kuramoto `sync = 0.9991±0.0001`、收敛率 0% | 把任何输入冲洗成与内容无关的定相点 |
| 2 | **没有目标函数** | 整套动力学不下降任何标量 | "会动"从不等于"产出顺序管线给不了的价值" |
| 3 | **不可消融 / 不可归因** | 六机制（Kuramoto/Hopfield/自由能/harmonic/reservoir/simplicial）堆一锅，单一 `max_delta` 出口 | 无法定位是哪一层失配，无法做消融 CI |

`_evolve_base` 继承了罪 2、罪 3，且引入一个**双计 bug**：它把 `[base; modulated]`（即 `[z_{t-1}; event]`）一起喂进 MLP（`scar_algebra.py:290` `inp = list(x) + list(e_tilde)`），把上一拍状态从输入路二次注入。

### 1.3 用户北极星

把这个核重设计为**真正的类脑计算（neuromorphic）**，而不是又一个状态机或确定性平滑。
约束（用户明确）：语义不归这个核（那是 v3 的活，靠外部 LLM assessor 当感官）；**不训练模型、不做离线蒸馏**；只用在线局部可塑。

---

## 2. 目标与非目标 (Scope)

### 2.1 目标 (Goals)

- G1 用一个**单机制**（两层预测编码）替掉 `_evolve_base`，作为 `base` 的每拍演化。
- G2 给它一个**被结构性消费的目标函数**（变分自由能 `F`）：删掉 `F`，动力学就消失（修罪 2）。
- G3 **在线局部可塑**（三因子 Hebbian + 在线精度），无 BPTT、无离线阶段，会话内自适应（"会塑"=脑，不是状态机）。
- G4 **人格即吸引子**：Big Five → 先验均值 `π`，自由运行不动点 `z* = tanh(W_gen·π)`，身份是 `F` 最小值的位置，不是全局魔数。
- G5 **输入敏感**：不动点显式含 `x_t`，结构上不可能塌回与内容无关的定相点（修罪 1）。
- G6 **每维可归因**：每维独立 `e0[i]/e1[i]/Π_obs[i]/Π_top[i]`，三个独立消融旋钮（`Π_top→0`/`η_W→0`/`ρ_p→0`）（修罪 3）。
- G7 **闭式可证有界 + 收缩**：静态可机检的前向不变 + 收缩，不靠 val-MAE 门。
- G8 **每拍便宜、非阻塞**：纯 Python、固定步数（K=2 + 一次谱钳），跑在 AstrBot 单事件循环里 `< 10ms/tick` CI 硬门（部署目标 `< 5ms`）。
- G9 **冻死的公共 API 一字不动**：`process` 签名/结果键/snapshot-restore/`route`/`assessment_source`/`observe` 键集/`active_channels==42` 全保。

### 2.2 非目标 (Non-Goals)

- ✗ **语义**。核永远不解语义；assessor（外部 LLM）是系统唯一语义器官。语义建模 = v3 track，不在本轮。
- ✗ **训练模型 / 离线蒸馏**。无 teacher、无 student 蒸馏、无离线拟合。只有在线局部可塑。
- ✗ **主动时机门控**。`affect_debt` 主动开口时机已在 v2.5 Step 2 实现并全绿，不在本轮范围。
- ✗ **删除共振场源码**。`DeterministicFusion` / `resonance_field*.py` 作为冻结 reference + 最后兜底**保留不删**。
- ✗ **离线情绪指标胜过 DeterministicFusion 的承诺**。见 §5（诚实声明）：这**证不了**，也**不是**成功判据。

---

## 3. 成功判据 (Definition of Done)

成功**不是**"在留出集情绪指标上赢确定性核"——那离线根本证不了（场既是数据发生器又是 baseline），追它正是上一轮被红队判定的 **theater**。

成功**是**以下结构性 + 消融性质，全部由 CI 守（详见 techspec §测试矩阵）：

1. **F 下降**：重复同输入 20 拍，`F_t` 严格下降后平台。
2. **可塑非常量**：50 拍变化会话，`var(Π_obs)>tol` 且 `‖W_gen(T)−W_gen(0)‖_F>tol`。
3. **人格可分**：两组 Big Five、同输入 ⇒ `z*` 在 ≥2 维上可分。
4. **输入敏感**：逐维扰动 `x_t` ⇒ 写进 `base` 的 `z` 逐维 `Δz*≠0`。
5. **会话内误差降**：重复 affect 模式，`mean|e0|` 下降。
6. **有界 fuzz**：1000 次随机（容许集权重 + 任意输入）⇒ `μ,z ∈ [-1,1]^8` 恒成立。
7. **收缩 fuzz**：数值断言 `‖J_μ‖₂ ≤ 1−αδ`（含被 Design A 漏掉的 `κ·H` 项）、`‖J_z‖₂=0.6`。
8. **部署真实可塑门（最关键）**：在真实 cadence（assessor 稀疏 + 真 `PredictiveCodingGate` surprise + 非重复语料）上 replay，断言 `‖W_gen(T)−W_gen(0)‖` 与预测误差降**非平凡**；若 surprise 实测被压平 ⇒ **红**，强制 retune `η_W`/门控，而不是声称在学。

任一条 1–5 或 8 失败 = 核塌回 EMA+查表，构建中断。

---

## 4. 顶刊理论锚 (Citations)

逐条按 workflow 的已验真集核对，页码无法独立核实者标注 `[pages: verify]`。**不许编造、不许拉大旗**。

- Rao & Ballard (1999) *Nat Neurosci* 2(1):79–87 — 预测误差单元 `e0/e1`。
- Friston (2010) *Nat Rev Neurosci* 11(2):127–138 — 自由能 `F`、精度 log-partition。
- Millidge, Tschantz & Buckley (2021) *Neural Comput* 33(5):1290–1322 — 单步潜变量更新即 `F`-梯度。
- Whittington & Bogacz (2017) *Neural Comput* 29(5):1229–1262 — 局部 `ΔW ∝ error·activity`（载重：`W_gen` 即 PC 生成矩阵，正是其设定）。
- Frémaux & Gerstner (2016) *Front Neural Circuits* 9:85 — surprise 作神经调质第三因子。
- Friston (2008) *PLoS Comput Biol* 4(11):e1000211 `[pages: verify]` — 在线精度/逆方差（背景；钳位递归是我们的构造，不过度归因）。
- Russell (2003) *Psychol Rev* 110(1):145–172 — valence×arousal circumplex → `a_vec` 的 2/1 维。
- Khona & Fiete (2022) *Nat Rev Neurosci* 23(12):744–766 — 吸引子框架（**cf./背景**：单一固定先验均值是点吸引子，非该文连续吸引子流形，避免拉大旗）。
- Barrett & Simmons (2015) *Nat Rev Neurosci* 16(7):419–429 — affect-as-prediction（背景，无独立内感回路，降为非载重）。
- Sterling (2012) *Physiol Behav* 106(1):5–15 — 预测性稳态（motivate `π` 作 allostatic setpoint；背景）。
- Hopfield (1982) *PNAS* 79(8):2554–2558 — **仅作能量下降的祖源引用**；PEL 无联想记忆耦合矩阵。

**故意不引** Lukoševičius & Jaeger 2009 / Maass et al. 2002 —— PEL 不是储备池/LSM，引了就是拉大旗（这也是储备池 Design C 未被选为主干的原因）。

---

## 5. 诚实声明：反 theater 边界与不承诺项

> 这一节是本 PRD 的良心。CLAUDE.md 要求交付前自检、红队在场——下面是经首席对抗复核后保留的真话。

**为什么这是脑、不是 DF 换皮 / EMA：**
- 目标函数**结构性载重**：`μ + κ·g` 就是 `F` 的梯度步，删 `F` 则 `g` 无定义、更新消失。EMA 不下降任何东西，DF 压根没目标。
- 输入敏感**结构性**：`z* = tanh(W_gen·μ* + W_in·x)`，非零输入雅可比，无 all-to-all 相位变量可锁。
- 可塑**真 > EMA（运行时）**：精度每拍按逐维误差更新（状态相关、时变增益，EMA 是定增益）；`W_gen` 在 surprise 下被改写（会话末的生成图 ≠ 会话初）。
- 归因**真**：逐维误差 + 三个独立消融旋钮，对比场的六处纠缠写入藏在一个 `max_delta` 后。
- 身份**是吸引子**：`π` 是 `F` 的先验均值，自由运行不动点维度特异。

**诚实的塌缩条件（点名，不藏）：** 若 `η_W=0` 且 `ρ_p=0`，PEL 退化为定精度 PC 推断 = `W_gen·π` 与 `x_t` 之间的闭式精度加权仿射平均 = DF + 一个人格查表先验 + 一段慢爬。
**PEL 只在在线更新真的跑、真的移动时才非 theater。** 这由 §3 的部署真实可塑门（test 8）强制：真流量上漂移压平就红、强制 retune，而非断言。

**不承诺：**
(a) 不承诺离线情绪指标胜过 DeterministicFusion（证不了，场是自己的 baseline）；
(b) 在稀疏 assessor 读之间**且**低 surprise 时，PEL 大体是朝 `π` 的收缩精度加权平均——可辩护为"事件间的情绪沉降"，但这是可塑性主张里最薄的一环，**如实标注而非粉饰**。
(c) `π` 在会话内若冻死（见 D-8），且未来若走单 spine 多租户（见 D-9），则 `π` 退化成手设向量 `tanh(B·traits)`，会拉近 theater——D-8 的慢 allostatic `π`-漂移正是为收窄这条缝而设。

---

## 6. 部署与并发约束 (Deployment)

- 上线档 lite = **纯 Python / 无 numpy / 无 torch**（`scar_algebra.py` 实测纯 `math`+list-of-lists）。2c2g（2 vCPU / 2GB）、无 GPU、`< 5ms/tick` 目标。
- **int8 在 lite 无意义并丢弃**（纯 Python 浮点核）；仅在未来 numpy max-tier 才重入，且届时**必须重验量化后收缩**（int8 舍入可能把 `σ` 顶过 0.9）。
- **每会话隔离（G1 已验证）**：`SylanneEngine`（`engine.py:37`）持 `_hosts: dict[session_id → SylanneHost]`（:83），`_get_or_create_host`（:371）每会话独立 host→kernel→spine→`ScarredState`。`shared(path)`（:283）只缓存同一 facade、内部按会话路由。故 PEL 可塑态进 snapshot 即随会话隔离，与今日 `base` 同等，**不新增串味**。
  - 残留约束（D-9）：若未来某部署让**单个 spine 跨多个 session_key**（`computation_spine.py:293` 的 `_relationship_deltas` per-relationship 模式），则单个 `ScarredState` 被多会话共享，PEL 可塑态需按 `session_key` 分桶（mirror `_relationship_deltas`）。当前架构不需要，列为约束而非现 bug。

---

## 7. 里程碑 (Milestones)

| 阶段 | 内容 | 是否需真数据 | 出口门 |
|---|---|---|---|
| **M0** | 本三件套定稿，拍 D-1…D-9 | 否 | 用户签字 |
| **P0** | `pel_core.py` 纯数学核（numpy-free）+ test 6/7（有界/收缩 fuzz）+ 1/3/4（F降/人格可分/输入敏感） | 否 | ruff+mypy strict + 5 测试绿 |
| **P1** | 引擎嫁接（`ScarredState.__slots__`/`to_dict`/`from_dict`/`set_pel_priors`，`pel_ctx` 入主 step，D-3 路由 wound/feedback）+ 双快照路径迁移测试（`ResonanceSpine` **与** `ComputationSpine`） | 否 | snapshot round-trip + 既有 tests 全绿 + `_field` 未碰断言 |
| **P2** | spine 集成 + 真实性：`x_t` 装配、可选 `free_energy` 键（D-1）、test 2/5/8 + **真跑** 500-tick benchmark 断言 `<10ms/tick` | 否（synthetic + 既有 benchmark 语料） | 全 CI 绿；test 8 红则 retune 再前进 |
| **P3** | 硬化 + 文档：消融扫、更新 ADR、changelog（D-1 加键则记 additive）、commit `feat/pel-core`、SemVer **2.1.0** minor | — | 合并 |
| 延后 | D-2 同拍重排、numpy max-tier int8、移除遗留 in-place clamp（PEL 现网验平价后） | — | — |

---

## 8. 待拍开放项 (Open Forks) — 摘要

完整论证见 design §开放项。下面是给用户的决策清单（每条带我的推荐）：

| Fork | 问题 | 我的推荐 |
|---|---|---|
| **D-1** | 把 `F_t` 加进 `result["resonance"]["free_energy"]`？（纯加性，但触结果形状） | **加**（唯一让目标可经公共契约审计；忽略未知键的消费者不受影响）。零触碰退路：只走 `engine.diagnostics()`。 |
| **D-2** | 本拍 affect 同拍消费（重排 spine）vs 1 拍延迟折入 | **先延迟折入**（零 spine 顺序风险，保留 in-place clamp 平价）；重排作后续 |
| **D-3** | wound/feedback step 的处理 | **走小固定 affine bias（不推进 μ）**，μ 单一来源主 step |
| **D-4** | `Π_max/κ/δ` 工作点 | **5 / 0.1 / 0.05** ⇒ `‖J_μ‖≤0.985`；按 CI test 7 调 |
| **D-5** | 内步 K | **K=2**（最便宜仍显两步下降） |
| **D-6** | SemVer + 分支（**纠正**：base 是 2.0.0，非综合说的 1.x） | **2.1.0 minor**，分支 `feat/pel-core`，Conventional Commits + English |
| **D-7** | `feedback()`（第三 step 点，:295，带 accepted/ignored/rejected 真 affect）是否推进 μ | **不推进 μ**：feedback 走 `W_gen`/奖励侧，不进潜变量路（与 D-3 一致，μ 单源主 step）；如此 feedback 的情绪效应经 `W_gen` 漂移间接体现 |
| **D-8** | `π` 是否引入慢 allostatic 漂移（surprise-**非**门控）让吸引子本身被学到 | **引入**（小、慢、有界）：收窄 §5(c) 的 theater 缝，让"身份涌现"名副其实 |
| **D-9** | 是否现在就把 PEL 态按 `session_key` 分桶 | **否**：现架构 host-per-session 已隔离；仅在未来单 spine 多租户时才分桶 |
| **D-10** | 用 PEL 的 surprise/置信信号渐减 assessor 调用（用户明确想要） | **建信号、不建跳过**：PEL 每拍已产 surprise；低 surprise 且无 wound 迹象 ⇒ 标"本拍可省一次语义读"（走 local fallback / 沿用现 mood），高 surprise 或**任何** wound 提示 ⇒ 永远叫 LLM（不对称安全门，绝不在可能受伤时省）。诚实天花板=**新颖度缓存**，只在熟悉/低新颖轮省，不预测新颖输入的 affect（那是 v3 语义蒸馏）。归属：SDK 产门控信号（P2 附带、非语义、在 PEL 内）；真正"跳过调用"是下游插件动作，受 [[no-premature-downstream]]，**信号先建、接线后做**。这正是 v2.5 当 v3 技术储备的接口。 |

---

## 9. 风险登记 (Risk Register)

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 真流量 surprise 被压平 ⇒ `W_gen` 不漂 ⇒ 退化 EMA | 高（唯一载重经验风险） | 部署真实可塑门 test 8 监测真 surprise，红则强制 retune；不靠断言 |
| `π` 冻死 + 单 spine 多租户 ⇒ `π` 退化查表 | 中 | D-8 慢漂移 + D-9 分桶约束 |
| 第二条快照路径 `ComputationSpine` 漏带 PEL 子键 | 中 | P1 双路径迁移测试（`computation_spine.py:1176/1199`，`from_dict` :1209） |
| `_mlp_passes>1`（pro/max 多跑演化）与 K 语义冲突 | 中 | PEL 的 K 为内部固定，**忽略 `_mlp_passes`**，加 tier-sweep 测试 |
| int8/numpy tier 未来引入破收缩证明 | 低（当前 out-of-scope） | 量化后重验 `σ≤0.9`；现 lite 不量化、不回归 |
| 场的 cosmetic `sync_order` 仍流入 `result["resonance"]`（`_field` 未碰） | 低 | 罪 1 对**情绪状态**已闭；场的 `sync_order` 记为 dead，按需 D 决定是否中和 |
