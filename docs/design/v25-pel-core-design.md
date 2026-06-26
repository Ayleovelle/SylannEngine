# v2.5 PEL-Core — 技术设计文档 (Design)

> 配套 [PRD](v25-pel-core-prd.md) 与 [技术规格](v25-pel-core-techspec.md)。本文给架构、方程、嫁接几何、契约保全、消融/可观测、回滚、相位、开放项全论证。
> 源出处行号全部经直接 Read 核实（workflow `wu5xap48p` 综合 + 首席对抗复核 2026-06-26）。

---

## 1. 架构总览

```
                       ┌─────────────────────────── 每会话隔离 (SylanneEngine._hosts) ───────────────────────────┐
   user msg ──▶ assessor(LLM) ──(v,a,r,c)──┐                                                                      │
                  [唯一语义器官]            │  1拍延迟折入                                                          │
                                            ▼                                                                      │
   每拍:  PredictiveCodingGate ──surprise s──▶  ┌──────────── PEL-Core (在 ENGINE 内, 不碰 _field) ───────────┐    │
          ssm_input h_t (HDC, 语义盲) ─────────▶│  x_t = c·a_vec + (1−c)·s·h_t      (无 z_{t-1}, 无 μ_{t-1})  │    │
                                                │  K=2 自由能下降:  μ ← (1−α)μ + α·tanh(μ + κ·∂(−F)/∂μ)        │    │
   personality (Big Five) ──π=tanh(B·traits)──▶│  读出:  z_t ← (1−β)z_{t-1} + β·tanh(W_gen·μ + W_in·x_t)       │    │
                                                │  在线可塑:  ΔW_gen=η_W·s·outer(Π_obs⊙e0, μ) (谱钳0.9); Π 在线 │    │
                                                └──────────────┬──────────────────────────────────────────────┘    │
                                                               ▼ 写入                                               │
                                                       scar_state.base ∈ [-1,1]^8  ◀── engine.observe() 读 (无 split-brain)
                                                               │                                                   │
                                  ┌────────────────────────────┴───────────────┐                                  │
                                  ▼                                            ▼                                   │
                         result["emotion"] (line 913)              LLM prompt 情绪叠加 (kernel.py:612)             │
                       └──────────────────────────────────────────────────────────────────────────────────────────┘
   _field (DeterministicFusion):  inject/resonate/observe/active_channels==42  ── 完全不碰，作冻结 reference+兜底
```

**一句话**：PEL 是一个坐在 `VoidScarEngine` 里、写 `scar_state.base` 的两层预测编码微电路；`_field` 那条 7 模块融合器一字不碰；语义全由 assessor 喂入；身份由人格先验 `π` 当吸引子；在线三因子可塑让它真会塑。

---

## 2. 嫁接几何（先把现实钉死，三处 recon 框架都修正过）

经直接 Read 核实：

1. **`scar_state.base ∈ [-1,1]^8`（`scar_algebra.py:144`）是唯一真源。** `VoidScarEngine.observe()` 读它（`void_scar_engine.py:220-223`）；LLM prompt 与场的 Module-2 注入都读同一对象（`resonance_integration.py:423,436,895`）。**PEL 写 `base` ⇒ 天然无 split-brain。** 维序冻死（`void_scar_engine.py:200-209`）：`0 warmth, 1 arousal, 2 valence, 3 tension, 4 curiosity, 5 repair_pressure, 6 expression_drive, 7 boundary_firmness`。

2. **`DeterministicFusion`（`self._field`）是另一个 7 模块融合器**，其 `active_channels==42`（`deterministic_fusion.py:216`，`7×6`）与 8 个情绪维无关。**PEL 不碰 `_field`。** 这一条直接杀掉三份 recon 里的 "free_energy → field.resonate()" 混淆——PEL 活在 engine，场不动，surface `F` 需要独立新管线（见 D-1）。

3. **`step()` 每拍跑多次**：wound（`heal=False`，`void_scar_engine.py:182`，按 `coupling_events` 跑 0..N 次，**非固定 2-4**）、main（`heal=True`，`:186`）、feedback（`:295`，`heal=True`）。三份设计的"换掉 :402 那行循环"一句话都不安全。**PEL 的潜变量演化只在 `pel_ctx` 在场（主 step）时触发**；wound/feedback 走廉价非潜变量路（D-3/D-7）。

4. **assessor 标量在主 `step()` 时不可得。** `engine.process()`（`resonance_integration.py:415`，内含主 `step()`）先跑，`_apply_assessment_to_engine`（`:422`）后跑；`process()` 签名（`void_scar_engine.py:129`）**无 `assessment` 形参**。⇒ 1 拍延迟折入（§4.1）。

5. **`_evolve_base` 的双计 bug 是真的**：`:402` 调 `_evolve_base(self.base, modulated)`，`:290` `inp = list(x) + list(e_tilde)` = `[z_{t-1}; event]` 一起喂 MLP。PEL 的 `x_t`（无 prior state）真修掉它。

---

## 3. 核方程

### 3.1 输入装配（assessor affect + 上下文，**永不含 prior state**）

```
a_vec = [ 0.67·v,  a,  v,  0.8·r,  0,  0.5·r,  0,  0 ]      # 镜像现有 assessor→base 映射
                                                            #   (resonance_integration.py:627/629/631 + wound_vec 613/615)
x_t   = c · a_vec  +  (1 − c) · s · h_t                      # c=confidence(未评估拍为0); s=surprise∈[0,1]
                                                            #   h_t = ssm_input (8维语义盲 HDC); affect 取自上一评估拍(1拍延迟)
```

`x_t` 不含 `μ_{t-1}/z_{t-1}` ⇒ 雅可比干净，避开 §2.5 的双计 bug。

### 3.2 K=2 潜变量推断（自由能下降——目标函数在动作中）

两层 PC 微电路。潜信念 `μ ∈ [-1,1]^8`，观测情绪 `z ∈ [-1,1]^8`。起 `μ ← μ_{t-1}`；内步 `k=1,2`：

```
e0 = x_t − W_gen · μ                          # 自下而上预测误差
e1 = μ   − π                                  # 自上而下：对人格先验 π 的误差
g  = W_genᵀ · (Π_obs ⊙ e0) − Π_top ⊙ e1       # = +∂(−F)/∂μ  (梯度本身)
μ  = (1 − α) · μ  +  α · tanh( μ + κ · g )     # 有界凸下降步; α=0.3, κ见techspec
```

**关键纠正（对 Design A 的可证性 must-fix #1）**：Design A 把 `W_rec @ m̃` 塞进 tanh 又在雅可比里丢了 `κ·H` 项，红队证其 0.97 界是错的。**本设计彻底删掉 `W_rec`**，把下降梯度 `μ + κ·g` 直接放进 tanh 参数——雅可比闭式精确（techspec §证明），少一个矩阵、少一次谱归一、界更紧。**PEL 里没有 `W_rec`。** K=2 后 `μ_t = μ`。

### 3.3 读出（写进 `scar_state.base`）

```
ẑ   = W_gen · μ_t
z_t = (1 − β) · z_{t-1} + β · tanh( ẑ + W_in · x_t )       # β=0.4, W_in = diag(0.6)
```

`z_t` 直写 `scar_state.base`。`W_in` 对角 ⇒ 满秩、逐维直接输入敏感。`z_t` 对 `z_{t-1}` 的递归是**纯泄漏**（`ẑ` 依赖 `μ_t` 非 `z_{t-1}`），收缩平凡 `(1−β)=0.6`。

### 3.4 矩阵清单（lite 全是纯 Python list-of-lists）

`W_gen`(8×8 可塑)、`W_in`(8 对角 固定)、`π`(8 人格先验 固定/会话)、`Π_obs,Π_top`(8 精度 可塑)、`μ`(8 潜态)。**无 `W_rec`。** 活态 < 1 KB。

---

## 4. 目标函数与可塑（详见 techspec 推导）

### 4.1 被消费的自由能 `F`

```
F_t = ½ Σ Π_obs[i]·e0[i]²  +  ½ Σ Π_top[i]·e1[i]²  −  ½ Σ ( log Π_obs[i] + log Π_top[i] )
```

三个消费者、一个目标（删 `F` ⇒ 无动力学）：(1) 潜推断 `g=∂(−F)/∂μ`；(2) 精度更新 = `F` 的 `−½logΠ` 可靠性项在线化；(3) 权重更新 `∂F/∂W_gen`。人格 `π` 作为 `F` 的**自上而下先验均值**进入（不是带自己耦合矩阵的独立 Hopfield 能量——那是 Design B 的致命过度工程）；自由运行不动点 `μ*→π`、`z*→tanh(W_gen·π)`，身份即 `F` 最小值的位置。

### 4.2 在线局部可塑（仅主 step，全局部、无 BPTT、无离线）

```
# 生成权重: 局部 Hebbian PC 规则, 三因子门控, 仅 surprise
ΔW_gen = η_W · s · outer( Π_obs ⊙ e0_t , μ_t ) ;   W_gen += ΔW_gen ;   W_gen = spectral_clamp(W_gen, 0.9)
# 精度: 在线逆方差
Π_obs[i] ← clip( (1−ρ_p)·Π_obs[i] + ρ_p / (e0[i]²+ε),  0.1, Π_max )
Π_top[i] ← clip( (1−ρ_p)·Π_top[i] + ρ_p / (e1[i]²+ε),  0.1, Π_max )
```

三处 must-fix（已折入）：
- **谱钳用现有 10 迭代 `_spectral_normalize`（`scar_algebra.py:234-274`），非"一次幂迭代"**：1 次估计是 `σ` 下界、可能放 `‖W_gen‖>0.9` 静默破收缩；8×8 上 10 迭代 ~1.3k flops、纯 Python 也可忽略。**拒绝"1-sweep"优化**（不健全、省得可忽略）。
- **只用 `surprise` 门、不用 `surprise·confidence`**：surprise 每拍可得（`PredictiveCodingGate`，`resonance_integration.py:407-409`），confidence 在稀疏未评估拍为 0；乘积会在主流量上冻死 `W_gen`。`η_W = 0.002·(0.5+openness)`。
- **诚实经验风险**：若 surprise 实测被压平，`W_gen` 慢漂——这是唯一载重经验风险，由 test 8 在**真 surprise 信号**上守、压平就红、强制 retune，而非断言。

### 4.3 人格先验 `π`（吸引子中心，会话内固定；D-8 可加慢漂移）

从 Big Five（`self._personality`，`process()` 前已设）映射，苏思澜 = 傲娇（神经质偏高、表达不亲和）：

```
π[0] warmth   =  0.30·agreeableness − 0.20·neuroticism
π[1] arousal  =  0.10 + 0.20·extraversion + 0.20·neuroticism
π[2] valence  =  0.40·(extraversion − neuroticism)
π[3] tension  =  0.40·neuroticism
π[4] curiosity=  0.40·openness
π[5] repair   =  0.20·neuroticism
π[6] express  =  0.30·extraversion − 0.20·(1−agreeableness)
π[7] boundary =  0.50·(1−agreeableness) + 0.30·sovereignty_guard
π ← tanh(π)
```

初值：`W_gen ← 0.5·I + 小结构化非对角`（谱钳≤0.9）；`Π_obs=Π_top=ones(8)`；`μ_0=π`；`z_0=当前 base`。
速率随特质：`η_W←openness`，`Π_top` 基精度`←neuroticism`（高 N 黏 setpoint 更紧）。
**人格必须经新显式 setter 接到 engine**：`apply_personality` → `engine.scar_state.set_pel_priors(...)`（must-fix）；旧的 `_field._coupling.*` reach-in 落在不动的场上、保留但失活。

---

## 5. 公共 API 保全（逐面核实）

| 冻死面 | 如何保（已验证行号） |
|---|---|
| `DeterministicFusion.inject/resonate/observe/switch_tier/reset/to_dict/from_dict` + 全 `_coupling/_complex` reach-in | **完全不碰**——PEL 在 engine，不在 `_field`。字节一致。 |
| `observe()` 8 键 / `resonate()` 11 键 | 场方法不变（`deterministic_fusion.py:196-221`）。 |
| `active_channels == 42` | `_complex.total_directed = 7×6`（`deterministic_fusion.py:216`），不碰。 |
| `route="resonance"` / `assessment_source="resonance_field"` | 字面量 `resonance_integration.py:911,938`，不碰。 |
| `engine.observe()` 键集（`warmth…boundary_firmness`） | 不变——`observe()` 读 `scar_state.base`（`void_scar_engine.py:220-223`），PEL 写同一 `base`。**无 split-brain**（`:423` & `:895` 都读 `self._engine.observe()`）。 |
| `process()` 签名 / 结果键 | `result["resonance"]` 键不变，**除非 D-1 加 `free_energy`**（纯加性）。 |
| snapshot/restore round-trip | `ScarredState.to_dict/from_dict`（`scar_algebra.py:571-610`）加 `"pel"` 子键（`μ,W_gen,Π_obs,Π_top`）；缺该键的旧档从人格重初始化（既有 `data.get(...)` 迁移）。**两条快照路径都要带**：`ResonanceSpine` 与 **`ComputationSpine`（`computation_spine.py:1176/1199`，`from_dict` :1209 经 `ScarredState.from_dict(engine_data["scar"])`）**。 |

assessment 路径：in-place clamp（`resonance_integration.py:626-632`）**保留**（首日平价，D-2 后议移除）；新增"存 `(v,a,r,c)` 供下拍折入"（加性）+ 把 `pel_ctx` 穿进主 `step()`（内部）。wound 路（610-616）与 void 压力路（636-641）不变。

---

## 6. 消融与可观测 (Observability)

每维归因直接：维 `i` 有独立 `e0[i],e1[i],Π_obs[i],Π_top[i]`。三个独立命名旋钮：`Π_top→0`（先验关）、`η_W→0`（生成学习关）、`ρ_p→0`（精度关）。
`F_t`、`per-dim e0/e1`、`‖W_gen−W_gen0‖`、`Π` 轨迹经 `engine.diagnostics()`（已非冻结）导出，反 theater CI 无需触契约即可读。
（D-1 若加 `result["resonance"]["free_energy"]` 则目标亦可经公共契约审计。）

---

## 7. 回滚 (Rollback)

- **代码级**：PEL 只改 `ScarredState.step()` 主调用点 + 一个 setter + 一个延迟 affect 存储。保留遗留 `_evolve_base` 路径不删；用一个 `use_pel` 开关在主 step 选择 PEL vs 遗留 MLP ⇒ 翻 flag 即回滚，零数据迁移。
- **状态级**：旧档无 `"pel"` 子键 ⇒ 自动从人格重初始化；新档被旧 SDK 读 ⇒ 旧 `from_dict` 忽略未知 `"pel"` 键。双向安全。
- **场兜底**：`DeterministicFusion`/`resonance_field*.py` 不删，作最后兜底。

---

## 8. 相位 (Phasing)

见 PRD §7（M0/P0/P1/P2/P3）。要点：**P0 纯数学核先证脑数学（零真数据、最高信噪），再碰 spine**；P2 才上部署真实可塑门 test 8 并**真跑** benchmark（非断言）。

---

## 9. 开放项详论 (Open Forks)

> 摘要见 PRD §8。下面是每条的完整权衡 + 推荐。用户拍完进 P0。

**D-1 — surface `F_t`？** `result["resonance"]` 现无 `free_energy` 键（`resonance_integration.py:928-936` 已核）。加 `"free_energy": round(F_t,4)` 纯加性但触结果形状。**推荐：加**——唯一让被消费的目标经公共契约可审计；忽略未知键的消费者不受影响；替掉场那个 dead 的硬零。零触碰退路：只经 `engine.diagnostics()`（已非冻结），CI 从那读。*我的选：加。*

**D-2 — 同拍重排 vs 1 拍延迟折入。** PEL 主 step 先于 assessor 读。**推荐：先发延迟折入**（零 spine 顺序风险、保留 in-place clamp 平价）；同拍重排（把 assessment 解析移到 `engine.process()` 前）作 PEL 验稳后的 follow-up。*我的选：延迟现做，1 拍延迟若真显行为再重排。*

**D-3 — wound/feedback step 处理。** PEL 只在主 step 触发（§2.3）；wound（`heal=False`）/feedback 步保留廉价非潜变量路。**推荐：wound/feedback 走 `base` 上小固定 affine bias（不推进 μ）**，scar 副作用存活但 μ 不被无 affect 的 wound 向量污染、μ 演化单源主 step。备选：让它们以 wound_vec 当 `x_t` 推进 μ（语义可辩护——伤痕就是输入）。*我的选：非潜变量 bias。*

**D-4 — `Π_max/κ/δ` 工作点。** 证明容许 `κ·Π_max ≤ 0.5`。**推荐：`Π_max=5, κ=0.1, δ=0.05` ⇒ `‖J_μ‖≤0.985`。** 若精度驱动的注意太弱，抬 `Π_max=8` 降 `κ=0.06`（保乘积≤0.5）。*我的选：5/0.1/0.05，按 test 7 调。*

**D-5 — 内步 K。** **推荐 K=2**（最便宜仍显两步下降）。K=1 塌向单仿射步（弱化"下降 F"叙事），K=3 多花成本换边际残差。*我的选：K=2。*

**D-6 — SemVer + 分支（纠正综合的事实错）。** `pyproject.toml` 版本是 **2.0.0**（综合误写 1.x）。新核在冻死 API 后。**推荐：minor bump → 2.1.0，分支 `feat/pel-core`，Conventional Commits + English。** D-1 加键则在 changelog 记为 additive/向后兼容。*我的选：2.1.0 minor。*

**D-7 — `feedback()` 是否推进 μ？（来自完整性批判 G4）** `VoidScarEngine.feedback()` 在 `:295` 以 `heal=True`(默认) 调 `scar_state.step(feedback_vec,0.0)`，带 accepted/ignored/rejected 真 affect（`:285-291`）。`pel_ctx is None ⇒ 遗留` 规则会把它路由到非潜变量路，等于 feedback 不再经核移动情绪——**这是行为变更，综合默默丢了**。**推荐：feedback 不推进 μ，但折进奖励侧**——它的情绪效应经 `W_gen` 漂移（feedback 的 outcome 调 `η_W`/门）间接体现，保持 μ 单源主 step。*我的选：不推进 μ；显式决策、不沉默丢。*

**D-8 — `π` 慢 allostatic 漂移？（来自完整性批判 G9）** 综合把 `π` 冻死在会话内；叠加 D-9（若无每会话边界）则 `π` 退化成手设 `tanh(B·traits)`，拉近 theater。**推荐：引入小、慢、有界、surprise-非门控的 `π` 漂移**（allostatic 规则：`π ← π + ρ_π·(⟨z⟩_EMA − π)`，`ρ_π` 极小），让吸引子本身被学到，收窄 §5(c) 的缝、让"身份涌现"名副其实。*我的选：引入（保守速率，进 snapshot）。*

**D-9 — 现在就按 `session_key` 分桶 PEL 态？（来自完整性批判 G1，我已对抗复核）** 现架构 `SylanneEngine._hosts`（`engine.py:83`）已 host-per-session、PEL 态进 snapshot 即随会话隔离，**与今日 `base` 同等、不需分桶**。仅当未来某部署让单个 spine 跨多 `session_key`（`_relationship_deltas` 模式，`computation_spine.py:293`）才需 mirror 它按 key 分桶。**推荐：现在不分桶，列为约束**；分桶接口预留但不实现（避免 [[no-premature-downstream]] 式死代码）。*我的选：不分桶，文档化约束。*

**D-10 — 用 PEL 的 surprise/置信渐减 assessor 调用（用户明确想要）。** 目标重述（诚实）：不是"取代 assessor"，是"随用随学、在熟模式上渐渐少叫 assessor、新颖输入永远兜回 LLM、wound 永不跳过"。
- **机制（非语义，v2.5 内可建）**：PEL 每拍已算 surprise `s`（`PredictiveCodingGate`）。当 `s` 低（消息低新颖）**且**无 wound 迹象时，产一个建议位 `assessor_advisable=False`（本拍可省一次新语义读，沿用现 mood / 走 `assessor._local_fallback`）；`s` 高 **或任何** wound 提示 ⇒ `assessor_advisable=True`，永远叫 LLM。**不对称安全门**：wound 侧零省（漏接真受伤是最贵的错）。
- **诚实天花板**：这是**新颖度缓存**，不是语义预测。它靠"消息指纹是否新颖"省调用，省不了"对全新说法判 affect"——那要预测 message→affect 映射 = 语义 = v3。低 HDC-surprise ≠ 情感无关（熟话也可能伤人），故门必须保守、且与 wound 检测并联。它换的是"省成本 vs affect 保真"，应只省明显冗余的读、并被测量。
- **归属与时序**：SDK 只**产门控信号**（便宜、在 PEL 内、随 surprise/置信白送）；真正"跳过 LLM 调用"是**下游插件**的动作，受 [[no-premature-downstream]]，**信号先建、接线后做**。这恰是 v2.5 当 v3 技术储备的接口——v3 的 confidence-gate 蒸馏直接长在 PEL 的 surprise/精度/自由能上。
- **推荐**：P2 附带把 `assessor_advisable`（+ surprise + 逐维精度）经 `engine.diagnostics()` / surface 暴露；下游消费押后。*我的选：建信号，下游接线另起。*

---

## 10. 完整性批判的其余 gap（已折入处置）

| gap | 处置 |
|---|---|
| G2 SemVer/类名错 | 版本 2.0.0→**2.1.0**；类是 `ResonanceSpine`（非 "ResonanceIntegration"）；`ComputationSpine` 第二快照路径纳入 P1 迁移测试 |
| G3 `_mlp_passes>1` 多跑 | PEL 的 K 为**内部固定**，**忽略 `_mlp_passes`**；加 tier-sweep 测试断言 lite/pro/max 行为一致 |
| G5 mypy strict | PEL 全量 strict 类型（typed list-of-lists，无裸 `Any` 泄漏，无随手 `# type: ignore`）；三 shim 模块的 `warn_unused_ignores` 豁免不含 PEL |
| G6 int8 部署约束未满足 | 明示：现核压根不量化，PEL 不引入回归也不满足该行；未来 numpy/int8 tier 须**量化后重验收缩** |
| G7 场 `sync_order` 残留 | 罪 1 对**情绪状态**（`result["emotion"]`，line 913/895）已闭；场的 cosmetic `sync_order`（`_field` 未碰）仍流入 `result["resonance"]`，记为 dead、按需中和 |
| G8 wound 步数无界 | wound 走廉价 bias 故成本无忧；"每拍有界"主张按真实 `coupling_events` 计数重立（确认上游是否封顶或显式 bound wound-bias 工作量） |
| G10 Khona&Fiete 拉大旗 | 降为 cf./背景（单一固定先验是点吸引子，非连续吸引子流形） |
| G11 ruff/类型门 | `E501` 已全局 ignore（综合的 `--ignore=E501` 冗余但无害）；类型门 strict 经 `packages=["sylanne_core"]` 自动纳入 `compute/pel_core.py` |
