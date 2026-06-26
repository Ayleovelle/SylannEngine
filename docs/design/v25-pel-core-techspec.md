# v2.5 PEL-Core — 技术规格 (Tech Spec)

> 配套 [PRD](v25-pel-core-prd.md) 与 [技术设计](v25-pel-core-design.md)。本文给完整数学推导与证明、数据结构、参数表、测试矩阵、逐文件改动、成本预算、G:\rules 合规映射。
> 这是可据以实现的层。所有源行号经直接 Read 核实。

---

## 1. 符号与常量

| 符号 | 含义 | 维 | 类型 |
|---|---|---|---|
| `μ` | 潜信念 (latent belief) | 8 | 可塑态 |
| `z` | 观测情绪 = `scar_state.base` | 8 | 可塑态 |
| `π` | 人格先验均值 (attractor center) | 8 | 固定/会话 (D-8 可慢漂) |
| `W_gen` | 生成矩阵 (generative) | 8×8 | 可塑 |
| `W_in` | 输入直通 = `diag(0.6)` | 8 | 固定 |
| `Π_obs,Π_top` | 精度 (precisions) | 8 | 可塑 |
| `x_t` | 输入 = assessor affect + 上下文 | 8 | 每拍 |
| `s` | surprise ∈ [0,1] (PredictiveCodingGate) | 标量 | 每拍 |
| `c` | confidence ∈ [0,1] (assessor) | 标量 | 评估拍 |

常量（D-4/D-5 工作点）：`α=0.3, β=0.4, K=2, κ=0.1, Π_max=5, δ=0.05, ρ_p=0.05, ε=1e-3`。
速率：`η_W=0.002·(0.5+openness)`，`ρ_π`（D-8，极小，建议 ≤1e-3）。
不变式：`κ·Π_max = 0.5`（收缩约束，见 §3）。

---

## 2. 算法（伪码，纯 Python 语义）

```python
def pel_step(state, x_t, s, pi):
    mu = list(state.mu)                          # 起 μ ← μ_{t-1}
    for _k in range(K):                          # K=2
        e0 = [x_t[i] - dot(state.W_gen[i], mu) for i in range(8)]      # 自下而上
        e1 = [mu[i] - pi[i] for i in range(8)]                         # 自上而下
        # g = W_genᵀ (Π_obs ⊙ e0) − Π_top ⊙ e1
        Pe0 = [state.Pi_obs[i]*e0[i] for i in range(8)]
        g = [sum(state.W_gen[j][i]*Pe0[j] for j in range(8)) - state.Pi_top[i]*e1[i]
             for i in range(8)]
        mu = [(1-ALPHA)*mu[i] + ALPHA*tanh(mu[i] + KAPPA*g[i]) for i in range(8)]
    # 读出
    z_hat = [dot(state.W_gen[i], mu) for i in range(8)]
    z = [(1-BETA)*state.z[i] + BETA*tanh(z_hat[i] + 0.6*x_t[i]) for i in range(8)]
    # —— 在线可塑（仅主 step）——
    e0f = [x_t[i] - dot(state.W_gen[i], mu) for i in range(8)]         # 末次 e0
    for i in range(8):
        for j in range(8):
            state.W_gen[i][j] += ETA_W * s * (state.Pi_obs[i]*e0f[i]) * mu[j]   # 三因子 Hebbian
    spectral_normalize_inplace(state.W_gen, rho=0.9)                   # 现有 10 迭代幂法
    for i in range(8):
        state.Pi_obs[i] = clip((1-RHO_P)*state.Pi_obs[i] + RHO_P/(e0f[i]**2+EPS), 0.1, PI_MAX)
        state.Pi_top[i] = clip((1-RHO_P)*state.Pi_top[i] + RHO_P/(e1[i]**2+EPS),  0.1, PI_MAX)
    # F（诊断 / D-1 可 surface）
    F = (0.5*sum(state.Pi_obs[i]*e0f[i]**2 for i in range(8))
         + 0.5*sum(state.Pi_top[i]*e1[i]**2 for i in range(8))
         - 0.5*sum(math.log(state.Pi_obs[i]) + math.log(state.Pi_top[i]) for i in range(8)))
    state.mu, state.z, state.F = mu, z, F
    return z, F
```

**注**：wound/feedback step（`pel_ctx is None`）不调 `pel_step`，走遗留 `base` 上小 affine bias（D-3/D-7）。`_mlp_passes` 不影响 K（D-3 of design §10/G3）。

---

## 3. 有界性与收缩证明（闭式、可机检）

### 3.1 `[-1,1]^8` 前向不变（结构性）

两条活态都是 `g(u) = (1−γ)·u_prev + γ·tanh(·)`，`γ∈(0,1]`：
- `μ_t = (1−α)·μ_{t-1} + α·tanh(μ_{t-1} + κ·g)`，`α=0.3`
- `z_t = (1−β)·z_{t-1} + β·tanh(ẑ + W_in·x_t)`，`β=0.4`

`tanh(·)∈(−1,1)^8`；若 `u_prev∈[−1,1]^8`，每坐标是 `[−1,1]` 中一点与 `(−1,1)` 中一点的凸组合 ⇒ 仍在 `[−1,1]`。起 `μ_0=π∈(−1,1)^8`、`z_0=base∈[−1,1]^8` ⇒ **`[−1,1]^8` 对所有权重、所有精度、所有输入前向不变。** 静态结构不变式（与场末层 tanh、`_evolve_base` 的 tanh `scar_algebra.py:304` 同招），运行期无需 clamp。

### 3.2 潜映射收缩（删 `W_rec` 后的精确证明）

潜递归 `μ_t = (1−α)μ_{t-1} + α·tanh(μ_{t-1} + κ·g(μ_{t-1}))`，`g(μ)=W_genᵀ(Π_obs⊙(x_t−W_gen μ)) − Π_top⊙(μ−π)`。雅可比精确：

```
∂g/∂μ = −( W_genᵀ diag(Π_obs) W_gen + diag(Π_top) )  ≜ −H      (H ⪰ 0, 对称 PSD)
J_μ   = (1−α)·I + α·diag(tanh'(·))·( I − κ·H )
```

`0 ≤ tanh' ≤ 1`，`I−κH` 特征值 ∈ `[1 − κ·λ_max(H), 1]`：

```
‖J_μ‖₂ ≤ (1−α) + α·max( 1, |1 − κ·λ_max(H)| )
```

界 `λ_max(H) ≤ ‖W_gen‖₂²·Π_max + Π_max ≤ 0.81·Π_max + Π_max = 1.81·Π_max`（用 `‖W_gen‖₂≤0.9`）。取 **`κ·Π_max ≤ 0.5`** ⇒ `κ·λ_max(H) ≤ 0.905 < 1` ⇒ `I−κH ⪰ 0.095·I ≻ 0` 且 `‖I−κH‖₂ ≤ 1`，故 `‖J_μ‖₂ ≤ (1−α)+α·1 = 1`（非扩张），且在 `tanh'<1` 处严格 `<1`。（**诚实注**：`spectral_clamp` 是下界估计、不严格保 `‖W‖₂≤0.9`，对抗 fuzz 下 ‖W‖₂ 可达 ~1.31，故 0.905 是乐观值；实测最坏 `‖J_μ‖₂=0.977<0.985`、`κ·λ<2`，收缩仍成立，余量见 §3.6。）
**严格一致界**：给梯度支加泄漏 `(1−δ)` ⇒ `‖J_μ‖₂ ≤ (1−α)+α(1−δ) = 1−αδ`。
**容许集（非空、显式）**：`Π_max=5, κ=0.1`（`κ·Π_max=0.5`），`δ=0.05` ⇒ **`‖J_μ‖₂ ≤ 0.985 < 1`，每拍、对一切 `‖W_gen‖₂≤0.9` 成立。**

这直接折入 Design A 最硬的 must-fix：收缩对**真实** K=2 递归（含 Design A 丢掉的 `κ·H`）重证，`Π` 上限与 `κ` 联合约束（`Π_max=5/κ=0.1`，非不健全的 `Π=10/κ=0.5`）。证明是闭式静态、**非** val-MAE 门。

### 3.3 读出映射 + 联合系统

`∂z_t/∂z_{t-1} = (1−β)·I = 0.6·I`（`ẑ` 依赖 `μ_t` 非 `z_{t-1}`）⇒ `‖·‖₂=0.6<1`。
联合 `(μ,z)` 块下三角（μ 收缩 ≤0.985，z 收缩 0.6，非对角 `∂z_t/∂μ_t` 有界）⇒ 联合谱半径 `= max(0.985,0.6) < 1`。

### 3.4 输入敏感（无饱和）

不动点 `z* = tanh(W_gen·μ* + W_in·x_t)`，显式含 `x_t`，`∂z*/∂x = β·diag(1−tanh²)·W_in`，对角严格正（`W_in=diag(0.6)`）。无 all-to-all 相位变量可锁 ⇒ 结构上不可能塌成与内容无关点（修罪 1）。异 `x` ⇒ 异 `z*`，可扰动测试。

---

## 3.5 更脑 v2 三机制（真流量上让脑机件活起来）

> 权威全文：`v25-pel-core-v2-upgrade-spec.md`（逐行替换 + E-1..E-7）；上线前硬修：`v25-pel-core-v2-critic.md`；实测病理：`v25-pel-core-v2-recon.md`。全部在 master flag `pel_core_enabled` 之后；flag 关时 `_field` 字节一致，PEL 模块不实例化。v2 默认 on-path（E-4），每机制独立可消融。

病理（recon 钉死）：真 spine 上精度 Π 全钉 `[5.0]×8`（跨维 std≈0，注意力死）、W_gen 漂移弱、π 往 ⟨z⟩≈0.08 漂蚀身份、无元可塑。

- M1 除法归一化精度（Heeger 1992）：`target_i = PI_MIN + _PI_GAIN·r_i/Σr`，`r_i=1/(e_i²+EPS)`，`_PI_GAIN=PI_BUDGET−N·PI_MIN=7.2`。固定预算的竞争再分配（均值 1.0=ones-init），解饱和。RHO_P EMA + `[PI_MIN,PI_MAX]` 钳不变；`PRECISION_DIVISIVE=False` 与原式代数等价（字节一致）。eta_w 乘 `ETA_W_DIVISIVE_GAIN=PI_MAX/(PI_BUDGET/N)=5.0` 复原设计均值。
- M2 BCM 式滑动阈元可塑增益（Bienenstock+1982；Abraham 2008）：`m_i=1+LAMBDA_BCM·tanh(GAMMA_BCM·(e0²−θ_i)/(θ_i+THETA_FLOOR))∈[0,2]`，`θ_i=EMA(e0²)`（RHO_THETA=0.01，~100 拍）。θ 先读后更；只调 Hebbian 速率不改 `+e0·μ` 方向（不复活无目的 Hebb）。
- M3 锚定 allostatic π（Sterling 2012；离散 OU/AR(1)）：`π_i ← clip(π_i + drift·(z_ema_i−π_i) − RHO_ANCHOR·(π_i−π0_i), −1, 1)`，`RHO_ANCHOR=4e-3`，π0=冻结 trait 先验。渐近保留 `a/(d+a)≈80%` π0。surprise-gate 出厂关（E-5；平 surprise 下恒等缩放=theater）。

schema v1→v2：`PELState` 加 `pi0`/`theta`/`s_bar`（均带默认，dataclass 排序安全）；`last_m` 诊断不持久化。`to_dict`/`from_dict` 加键带 v1 回退（`pi0:=pi`、`theta:=THETA_INIT`、`s_bar:=0`）。**迁移语义坑（must-fix #2）**：v1 档无 `pi0`，回退 `pi0:=pi` 会把**已漂走的身份**当锚点冻住（不恢复真 trait 先验），无 washout 保证只是"冻结侵蚀"而非"恢复"。长跑 v1 会话迁移后，host 应在首次加载时重调 `set_pel_priors`（它有人格）恢复真 π0；spine 的自动重 prior 只对**缺 "pel" 键**的 legacy 档触发（`not pel_active()` 门控），v1-带-pel 档恢复后已 active、不会自动重 prior。

## 3.6 重导有界性 + 收缩（M1+M2+M3 后逐拍成立）

容许集 `A` 不变。三个逐拍执行器仍保 state∈A：`spectral_clamp`（无条件、最后、不变）、双精度逐元 `_clip`、M3 凸 π 更新。

- 关键不变量：`λ_max(H) ≤ ‖W‖₂²·max_i Π_obs[i] + max_i Π_top[i]`，**只经每维 max 进雅可比，与 budget/Σ 无关**。除法归一化在 `[PI_MIN,PI_MAX]` 内重分配、钳保留。**诚实余量（红队实测修正）**：`spectral_clamp` 的 10 次幂迭代只**下界**估 σ，并不严格把 ‖W‖₂ 压到 0.9——对抗 fuzz 初值（`spectral_clamp(uniform[-1,1],0.9)`，即 #6/#7 用的构造）下 ‖W‖₂ 实测可达 ~1.31。故最坏界不是早稿写的 0.905，而是 `κ·λ_max(H) ≤ κ(1.4²·5+5) ≈ 1.48 ≤ 2`；`‖J_μ‖₂` 20000 次 fuzz 实测最坏 **0.977 < 0.985**（`κ·λ` 最坏 ≈1.36<2）——收缩**成立**但余量比早稿薄。真 init/生产（‖W‖₂≈0.52）`κ·λ_max(H)@Π=5=0.635`，远在安全区。（`spectral_clamp` 的下界性是既有 v1 行为，非 v2 引入；收紧它是独立项。）
- M3 引理：`π_i'=π_i(1−d−a)+d·z_ema_i+a·π0_i`，三系数≥0 且和为 1 当 `d+a≤1`（`d≤RHO_PI=1e-3`、`a=4e-3` ⇒ 5e-3≤1）⇒ π∈[−1,1]^8 前向不变（比 legacy a=0 更强）；π 的值不入 `‖J_μ‖` 界（只经 `tanh'`≤1）⇒ 不影响收缩。无 washout：`|π_eq−π0|=(d/(d+a))·|z_ema−π0|<|z_ema−π0|`。
- M2/eta_w：m_i∈[0,2] 与 eta_w×5 只缩 pre-clamp ΔW，`spectral_clamp` 无条件兜底 ⇒ A 不变。真 max η=0.002·1.5·5=**0.015**，`|ΔW|≤0.015·1·5·3.5·2·1=0.525` 有限。
- 收缩-fuzz #7 采样 Π∈[PI_MIN,PI_MAX] 已覆盖除法运行域，钳保留 ⇒ **无需改 #7**。

---

## 4. 数据结构与持久化

`ScarredState` 新增（`scar_algebra.py`）：

```python
# __slots__ 追加 (现 :113-139):
#   "_pel_mu", "_pel_W_gen", "_pel_Pi_obs", "_pel_Pi_top", "_pel_pi", "_pel_F", "_pel_enabled"
```

`to_dict`（`scar_algebra.py:571-...`）追加加性子键：

```python
out["pel"] = {
    "mu": self._pel_mu, "W_gen": self._pel_W_gen,
    "Pi_obs": self._pel_Pi_obs, "Pi_top": self._pel_Pi_top,
    "pi": self._pel_pi,                 # D-8 慢漂时也需存
    "v": 1,                             # PEL schema 版本, 只增不改
}
```

`from_dict` 迁移安全：`pel = data.get("pel")`；缺则 `set_pel_priors(personality)` 从人格重初始化（既有 `data.get` 模式）。
**两条快照路径都过**：`ResonanceSpine`（`resonance_integration.py:968/994`，键 `"field"` 是 `_field` 的，PEL 在 engine 侧的 `scar` 块）与 `ComputationSpine`（`computation_spine.py:1176/1199`，`from_dict` :1209 `ScarredState.from_dict(engine_data["scar"])`）。

新 setter：

```python
def set_pel_priors(self, personality: dict[str, float]) -> None:
    """从 Big Five 设 π 与速率；W_gen=0.5·I+结构化非对角(谱钳≤0.9); Π=ones; μ=π。"""
```

`apply_personality`（`resonance_integration.py:~241` 区）增一行：`self._engine.scar_state.set_pel_priors(effective_personality)`。

---

## 5. 测试矩阵（merge-blocking，`tests/test_pel_core.py`）

工具链（§7）：`ruff check`、`mypy`（full strict）、`pytest tests/ -q`。

| # | 测试 | 断言 | 需真数据 | 阶段 |
|---|---|---|---|---|
| 1 | F-descent | 重复同输入 20 拍，`F_20 < F_1 − tol`（读 `engine.diagnostics()`，无契约依赖） | 否 | P0 |
| 2 | 可塑非常量 | 50 拍变化会话，`var(Π_obs)>tol` 且 `‖W_gen(T)−W_gen(0)‖_F>tol` | 否 | P2 |
| 3 | 人格可分 | 两组 Big Five、同输入 ⇒ `‖z*_A−z*_B‖>tol`（≥2 维） | 否 | P0 |
| 4 | 输入敏感 | 逐维扰动 `x_t` ⇒ 写进 `base` 的 `Δz*≠0`（断言真 `z`，非场 `sync_order` 代理） | 否 | P0 |
| 5 | 会话内误差降 | 重复 affect 模式，`mean|e0|` 降 | 否 | P2 |
| 6 | 有界 fuzz | 1000 次（容许集权重 + 输入∈[−1,1]^8）⇒ `μ,z∈[−1,1]^8` 恒 | 否 | P0 |
| 7 | 收缩 fuzz | 数值断言 `‖J_μ‖₂≤1−αδ`（**含 κ·H**）、`‖J_z‖₂=0.6`，网格 `(μ, W_gen∈容许, Π∈[0.1,Π_max])` | 否 | P0 |
| 8 | **部署真实可塑门** | 真 cadence（assessor 稀疏 + 真 `PredictiveCodingGate` surprise + 非重复语料如 70-input `_tmp_benchmark`）⇒ `‖W_gen(T)−W_gen(0)‖` 与误差降**非平凡**；压平 ⇒ **红**，强制 retune | 否（synthetic + 既有语料） | P2 |
| 9 | snapshot round-trip | 两条路径（`ResonanceSpine`+`ComputationSpine`）带/不带 `"pel"` 子键往返一致；旧档迁移 | 否 | P1 |
| 10 | API 保全 | `_field` 字节未碰断言；`observe`/`resonate` 键集、`active_channels==42`、`route`/`assessment_source` 字面量不变 | 否 | P1 |
| 11 | tier-sweep | lite/pro/max（`_mlp_passes` 1/2/3）PEL 行为一致（K 内部固定、忽略 `_mlp_passes`） | 否 | P1 |
| 12 | 成本 | **真跑** 500-tick benchmark，断言 `<10ms/tick`（非断言式估算） | 否 | P2 |
| 13 | **T-DIV 真路径精度活** | 真 `ResonanceSpine` 跑 CORPUS 160 拍稀疏 assessor，弃 30 warm-up；跨维 `pstd(pi_obs)>0.15`（实测 ~0.46）、`pstd(pi_top)>0.10`（~0.25）；over-time var>1e-3（~0.048）；clip 见证 `pi_obs/pi_top≤PI_MAX` 恒，稳态峰<PI_MAX | 否 | v2 |
| 14 | T-DIV-OFF 消融 | 同真路径 `PRECISION_DIVISIVE=False`：`on.pstd>2×off.pstd`（0.46 vs 0.10），off 有维钉 PI_MAX（饱和签名），on 峰<PI_MAX−0.5 | 否 | v2 |
| 15 | T-BCM 元可塑 | (a) `LAMBDA_BCM=0`⇒`last_m≡1`（代数退化遗留三因子）；(b) `LAMBDA_BCM=1`⇒m-spread 均值>1e-2（实测 1.24）；(c) path-length `Σ‖ΔW‖_F` λ=1 vs λ=0 相对差>0.05。**注 critic must-fix #1：删 θ 方差阈值（1e-4/1e-6 会误杀正常 BCM，实测 6.1e-6/1.8e-6），改用 m-spread+path-length** | 否 | v2 |
| 16 | T-PROD 乘积不抵消 | 真路径有效门 `g_i=pi_obs_i·m_i`：跨维 `pstd>0.05`（~0.27）且 over-time var>1e-3（~0.074）——竞争×时序两正交轴不塌成标量 | 否 | v2 |
| 17 | T-ANCHOR 身份保留 | 1500 拍 z→0 高蚀压：`‖π−π0‖`@4e-3 < 0.5×@0 washout（0.14 vs 0.55，保留 74.5%）；anchor-live `‖π−π0‖>1e-3`（π 真动非钉死） | 否 | v2 |
| 18 | T-SCHEMA v1→v2 | PELCore 往返 pi0/theta/s_bar；v1 档回退（pi0:=pi、theta:=THETA_INIT、s_bar:=0）；**ScarredState 快照按 host flag gate 恢复（must-fix #3：flag 关时 "pel" 键被忽略，不偷开 PEL）** | 否 | v2 |
| 19 | proof 守卫 | #6 有界 fuzz 加 `π∈[−1,1]^8` 断言；#13 含真 spine clip 见证 | 否 | v2 |

任一条 1–5 或 8 失败 = 核塌回 EMA+查表，构建中断。**不断言**"胜过 DeterministicFusion 的离线情绪指标"（证不了）。

**#1 重释（更脑 v2）**：原 #1 断言 full `F=½ΣΠe²−½Σlog Π` 在重复输入上降。v2 除法精度下 full F 不再单调——竞争精度故意给高相对误差维低精度（高熵、大 −½log Π）。更关键：legacy full-F 的"降"本身是精度**饱和**的产物（Π 钉 PI_MAX 使 −½Σlog Π 暴跌，掩盖加权误差实际**上升**）——即测的是 recon 要除掉的死饱和病理，非学习。故 #1 改断言真正幸存且更诚实的属性：**底向误差能量 `‖e0‖²` 在重复输入上降**（legacy 0.93→0.65、v2 0.93→0.63，路径无关单调），并断言 F 有限。这是修正错代理，非弱化。

**生产见证（must-fix #4，头号风险）**：除法精度活性数据依赖；`pel_diagnostics()` 暴露 `pi_obs_pstd`/`pi_top_pstd`/`prod_spread`/`precision_live`，真流量上窗口化、稳态 spread 跌破 T-DIV tol（0.15）即告警——把"语料上活"变成"生产上死了能被发现"。

---

## 6. 逐文件改动 (Change Map)

| 文件 | 改动 |
|---|---|
| `sylanne_core/compute/pel_core.py` | **新建**：`PELCore`/`PELState`（numpy-free，§2 方程，§4 可塑，§4.3 人格初始化）。~150 LOC，全 strict typed。 |
| `sylanne_core/compute/scar_algebra.py` | `__slots__` 追加 PEL 槽（:113-139）；主 step 用 `use_pel` 选 PEL vs 遗留 `_evolve_base`（:401-402）；`to_dict`/`from_dict` 加 `"pel"`（:571-610）；新增 `set_pel_priors`。 |
| `sylanne_core/compute/void_scar_engine.py` | `process`（:129-197）穿 `pel_ctx`/延迟 affect 存储；`step` 三调用点（:182/186/295）按 D-3/D-7 路由（仅主 step 带 `pel_ctx`）。 |
| `sylanne_core/compute/resonance_integration.py` | 在 :414 附近装配 `x_t`；`_apply_assessment_to_engine`（:588-646）存 `(v,a,r,c)` 供下拍折入；可选 `free_energy` 键（:928-936，D-1）；`apply_personality` 接 `set_pel_priors`。 |
| `tests/test_pel_core.py` | **新建**：§5 的 12 门反 theater 套件。 |
| **不碰** | `deterministic_fusion.py` 及一切冻死 `_field` 面。 |

---

## 7. 成本预算（诚实——lite 纯 Python）

**事实**：`scar_algebra.py` 纯 `math`+list-of-lists（numpy 只在 `resonance_field_numpy.py`）。"int8 BLAS / 256-LUT / <0.1ms" 在此嫁接点是虚构。真实定价：

每**主拍**（idle/未评估），纯 Python 标量循环，K=2：
- K=2 ×（`W_gen·μ` 64 + `W_genᵀ·(Π⊙e0)` 64）≈ 256 MAC
- `ẑ=W_gen·μ` 64 + `W_in·x`(对角) 8 = 72 MAC
- 误差/精度逐元素 ~80 op；16 `math.tanh` ~16 调
- **≈ 420 标量 MAC + ~100 op + 16 tanh**。CPython ~50–100 ns/float-op ⇒ ~数十 µs。

每**评估拍**加：`ΔW_gen` outer 64 + **10 迭代谱钳 8×8 ~1.3k** + 精度 16 ≈ ~1.4k op ⇒ ~100–150 µs。评估拍稀疏，摊销 = idle 的数十 µs。

**净**：**远低于 10ms CI 硬门**（门是 10ms/tick × 500 拍；5ms 是部署目标）。现 `_evolve_base` ~1 趟 `12×16+8×12≈360 MAC` 纯 Python、套件已过，PEL ~420 MAC + 稀疏 10 迭代钳同量级。**固定步数（K=2 + 一次钳），无迭代到收敛循环** ⇒ 单事件循环内非阻塞。**500-tick benchmark 合并前必须真跑**（test 12，非断言）。

**pro/max（可选，非 lite）**：numpy 后端可向量化 8×8；lite 保纯 Python/无 numpy。int8 在 lite 丢弃（纯 Python 浮点核无意义）；仅未来 numpy max-tier 重入，且届时**重验量化后收缩**（舍入可能把 `σ` 顶过 0.9）。

---

## 8. G:\rules 合规映射

> G:\rules 本体是 AstrBot **插件**规范；只横向条款绑此 SDK 重设计。逐条：

| 条 | 要求 | 本设计 |
|---|---|---|
| §8 单事件循环 | 每拍便宜、非阻塞、无迭代解算器堵 bot | 固定 K=2 + 一次谱钳，~数十 µs，§7 真跑验 `<10ms` |
| §9 提交/SemVer | Conventional Commits、English、`feat/` 前缀、SemVer 对齐 | `feat/pel-core`，commit/PR English，**2.1.0 minor**（D-6） |
| §10 lint/类型 | ruff + 单一类型门 | 用 **SDK 自己** 的：`ruff==0.14.2`（`E,F,W,I,UP,B,SIM`，`E501` ignored，py310，line 100）+ `mypy strict packages=["sylanne_core"]`（**非**插件的 pyright）。PEL 全 strict、无随手 `# type: ignore` |
| §11 测试 | pytest，纯逻辑必测 | `tests/test_pel_core.py` 12 门（§5），`asyncio_mode=auto` |
| §14 模型/effort 分层 | 编排按任务形状分模型 | 本设计的 workflow 已照办（recon=sonnet，理论/设计/红队=opus high/xhigh，综合=opus max） |
| §2-7/§12（插件目录/上架/消息组件） | — | **不绑** SDK 核；但 vendored 同步须保公共 API 稳定（已是硬约束，§5 design） |

---

## 9. 实现顺序（落到 commit 粒度）

1. **P0** ✅：`pel_core.py` + test 6/7（有界/收缩，零真数据、锁证明）→ test 1/3/4。`ruff+mypy strict+5 测试绿`。单 commit。（commit `371433b`）
2. **P1** ✅：`scar_algebra` 槽/迁移/setter + `void_scar_engine` 穿 `pel_ctx` + D-3/D-7 路由 + `apply_personality` 接线。test 9/10/11。既有 tests 全绿、`_field` 未碰断言。（commit `acc9669`）
3. **P2** ✅：`resonance_integration` 装配 `x_t` + 延迟 affect 存储 +（D-1）`free_energy` 键 +（D-10）`assessor_advisable` 信号。test 2/5/8/12。（commit `3caf1a2` / `d36c574`）
4. **P3** ✅：消融扫（`tests/test_pel_ablation.py`，`Pi_top→0`/`eta_W→0`/`ρ_p→0` 各可测）+ changelog（D-1 additive 键 + default-off flag + D-10 信号）+ SemVer **2.1.0**。合并 `feat/pel-core`。

> 实现状态：P0–P3 全部落地。默认 `pel_core_enabled=False`，既有套件逐字节不变；PEL-on 集成另测。`ruff` + `mypy --strict` + 全量 `pytest` 两路（off=baseline / on）均绿。

---

## 10. 附：被拒红队点（带证）

| 红队主张 | 裁决 |
|---|---|
| A-RT "free_energy → resonate() 同键、无需新键 FALSE" | **采纳**（核实 :928-936 无该键）→ D-1 加性键 + diagnostics 退路 |
| A-RT "1 拍延迟是 hand-wave" | 部分驳：延迟现为显式文档化设计选择（design §9 D-2），非隐藏 |
| B-RT "目标 cosmetic / 三矩阵矛盾" | 适用 B，**对赢家驳回**——PEL 无 `W_rec`、无 Hopfield 耦合矩阵，先验是 `F` 内固定均值 π，矛盾结构性缺席 |
| C-RT "W&B 2017 为 readout 拉大旗" | 采纳其针对 C；**对赢家 W_gen 更新是真 PC 局部规则**（W_gen 是 2 层 PC 生成矩阵，正是 W&B 设定），引用载重、保留 |
| C-RT "idle target=μ_pers=EMA-toward-prior" | 适用 C，**对赢家驳回**——PEL idle 输入是 `(1−c)·s·h_t`（surprise 缩放 HDC），非先验；先验只作 `F` 自上而下项，可塑按真 HDC novelty surprise 门控、非朝常数慢爬 |
| 完整性批判 G1 "进程级共享单例、PEL 串味 CRITICAL" | **对抗复核后降级**——`SylanneEngine._hosts`（`engine.py:83`）host-per-session，`shared()` 只缓存 facade、按会话路由；PEL 进 snapshot 即随会话隔离，与今日 `base` 同等。残留仅未来单 spine 多租户（D-9） |
| 红队 "σ=0.9 不保证收缩、需 slack" | **驳回**（此结论早在 v3 推过）：单矩阵 `(1−α)+0.9α=1−0.1α<1` 对任意 `α>0` 收缩；此处更直接走 `κ·Π_max≤0.5` + 泄漏 δ 的精确界 §3.2 |
