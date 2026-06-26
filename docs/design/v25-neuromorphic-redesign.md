# v2.5 重新设计 — 类脑计算引擎 (Neuromorphic Compute Engine)

> 目标(用户指令,原话):**重新设计 2.5 — 做计算引擎,但是类脑计算,设计哲学与大脑无异,真模型训练放到 v3。**
>
> 即:把 v2.5 从现在的过渡补丁,重设计成一个**连贯的类脑计算引擎**,整套架构的计算哲学按大脑来,
> 全靠**手设计的神经科学结构 + 在线局部可塑**实现,**零离线训练**(真模型训练是 v3 的事)。
> 引擎是"感官(LLM)下游的脑-身体",不冒充它给不了的语义智能。

## §0 状态

设计进行中。架构方案由设计擂台 workflow(`wczx2cmjg` / run `wf_d32eec3f-82f`)产出:4 路侦察 →
4 种组织哲学各出一版架构 → 每版对抗评审猎 theater → 综合。本文件 §1/§2/§8 是基于直读当前代码的
承重地基(确定);§3–§7/§9–§10 待擂台结论填入。

## §1 为什么要重设计 —— 当前 v2.5 的不连贯(直读代码实锤)

v2.5 现状是"杀了共振场 + 临时替身 + PEL 藏 flag 后"的补丁拼接,不是一个连贯的脑:

- **融合核是占位替身**:`resonance_integration.py:138` `self._field = create_deterministic_fusion(...)`——
  共振场已被 `DeterministicFusion`(单次确定性聚合)顶替,但它只是"对已删机制保契约"的兜底,不是
  按脑设计的核(见 [[v25-design]] 记忆轨迹)。
- **类脑核 PEL 被藏在 default-off flag 后**:`pel_core.py` 的 PEL-Core 更脑 v2(预测编码 + 除法精度 +
  BCM 元可塑 + 锚定 allostatic π,有界可证)是目前唯一真按脑设计的件,却 gated 在 `pel_core_enabled=False`,
  且只 lite 8 维专属、藏在 VoidScarEngine 里写 `scar_state.base`,不是引擎主干。
- **API 还在用已死的共振场词汇说话**:`apply_personality`(`resonance_integration.py:251-277`)仍把 Big Five
  映射成 `_coupling.kuramoto._k1/_k2/_k3`、`free_energy._precision`、`broadcast._threshold`、`_hopfield_strength`、
  `_max_attractors`、`_dissipation`、`_residual_decay`、`_identity_inertia`——这些全打进 DeterministicFusion 的
  惰性桩,人格→引擎的映射停留在 Kuramoto/Hopfield 这套与脑无关的振子词汇。
- **stale 范式文档**:`process()` docstring(`:381-386`)还在描述"各模块注入 → 场迭代耦合到收敛 → 表达从
  收敛态涌现"——可 DeterministicFusion 是单次前向,没有迭代收敛。叙述与实现脱节。
- **死代码仍在树里**:`resonance_field.py` / `resonance_field_numpy.py` / `resonance_field_torch.py` 三变体
  spine 已不用(仅自身直测在用);`coupling_dynamics.py`、`emergence.py`、`social_field.py`、`autopoiesis.py`、
  `phase_transition.py` 等是否仍真正输入敏感、还是装饰/常量,待 theater-audit 钉死。
- **模块多源拼接**:活路径 HDC→PredictiveCodingGate(surprise)→VoidScarEngine(情绪源,PEL 在内)→
  assessor_advisable→DeterministicFusion→EmergenceTracker→PhaseTransitionExpression→embodiment drift,
  来自不同设计年代、各说各话,没有一个统一的脑组织原则把它们串成一个身体。

重设计要做的:用**一个**类脑组织原则把这些重新长成一个连贯的脑-身体,该合的合、该删的删、人格映射
改用脑参数语汇,PEL 类脑核从"藏 flag 后的旁路"提升到主干,默认行为就是类脑(仍保 flag/契约/字节兜底)。

## §2 北极星与硬约束(任何方案必须过)

反 theater 北极星(本项目的立身之本,共振场就是因为犯了它被杀):
- 每个机制必须有明确**计算职责/目标函数**,**独立可消融**且有 CI 红线证明它不是 no-op,**真正提升**
  输入敏感性(而非冲洗成与内容无关的定点),并映射到**真实、可引的脑原理**——是脑**机制**不是脑**cosplay**
  (例:为美观模拟脉冲却什么都不买,禁止)。"更脑"永远指更多脑机制,绝不是更多脑外观。
- 诚实优先于表演:不声称语义盲感官(LLM)封顶之外的能力。

硬约束(违一条即出局):
- 部署 2 vCPU / 2 GB 无 GPU VPS。lite 纯 Python;numpy 仅可选加速;**serving 不准 torch/onnx**。
- **<10ms/拍,且按尾巴算预算**:红队实测现有 spine 在快 dev 机上 mean ~3.9ms / p50 3.16ms / **p99 12.6ms** /
  max 22ms;真 2c2g(×2–4)p99 才是绑定数。重设计必须**更轻、尾巴更受控**,不是更重。
- 两个活 footgun 必须修/避:`config.build_profile()→get_backend()` eager `import torch`(+458MB RSS);
  jieba 词典 +67MB。lite 必须 torch-free 且轻。
- 公共 API 冻死;快照/恢复安全;有风险的默认 off flag;**有界 + 闭式收缩可证**(引擎不可发散)。
- **LLM/assessor = 唯一语义器官**(远程 API,不在盒子上);HDC 是语义盲哈希。引擎是感官下游的脑-身体。
- **v3 边界**:真训练/真本地语义学习是 v3,且 ADR-0001 已判"学习版核在真实数据上尚未打过 trivial
  persistence"——重设计**不得偷渡 v3 的训练/学习**,只做手设计结构 + 在线可塑。

## §3 无需训练即可体现的脑原理正典(保留 vs 陷阱)

可在零训练下用手设计结构 + 在线局部可塑落地的脑原理(每条带真引文,引文按红队纪律,未重验标 [verify]):

- 层级预测编码(Rao & Ballard 1999 Nat Neurosci; Friston 2005)——底向/顶向精度加权误差最小化。**PEL 已是。**
- 精度加权=注意力 / 除法归一化(Heeger 1992; Carandini & Heeger 2012)——M1 已是。
- 多时标突触可塑:三因子 Hebbian / BCM 元可塑(Bienenstock+1982)/ 稳态突触缩放(Turrigiano 2008)——
  M2 已有 Hebbian+BCM。
- 神经调质作元参数(Doya 2002;Yu & Dayan 2005 ACh/NE = 预期 vs 意外不确定性;DA = RPE/精度)——
  把感官映成"怎么推断"的旋钮,**是本次最大的新增脑机制**(见 §6)。
- Allostasis / 预测性调节(Sterling 2012)——M3 锚定 π 已是。
- 内感受推断 / 情感作身体状态估计(Barrett 2017; Seth 2013)——8 维 z 读出 = 内感受情感,**这是项目真论点**。
- 典范皮层微环路 = 预测编码(Bastos+2012 на Douglas-Martin)——作**组织原则**,让 PEL 成"非任意的核"。

陷阱(= 被杀的共振场之罪,必须保持死亡或诚实改写,**不得**作卖点):
- 朴素 Kuramoto / 全局相位、Hopfield 自采吸引子、simulated spikes(LIF)纯美观——**全删,见 §8**。
- **临界性 / edge-of-chaos 作目标**——与"可证收缩"自相矛盾(可证收缩系统按定义**不在**临界点):
  ρ(W_gen)=0.9、‖J_μ‖≤0.985<1、唯一稳定不动点,这是**正当的稳定裕度,不是 criticality**。CMC-8 因为
  把 ρ=0.9 包装成"近临界"被红队判残余 theater;本设计**丢掉 criticality 这个词**,只讲收缩裕度。
- **k-WTA 稀疏编码 @ N=8**——Olshausen-Field 是"上万里取几个"的过完备去冗余;8 个命名的非冗余情感维清零
  第 3 强 = 丢信号不是去冗余,引文不转移。**砍**。
- **字面 Tsodyks-Markram STP**——是 ms 级脉冲间突触滤波;这里一"拍"是分钟级对话消息、无脉冲。直接套是
  "novelty 标量贴 STP 标签",4 个量级时标错配。**要么诚实改写**(作用在**输入支**上的历史依赖 novelty 增益,
  不冒充字面突触 STP,且带实质红线)**要么砍**。

## §4 选定架构 —— 综合赢家(单皮层预测编码柱 + 神经调质总线 + 主动推断动作门)

擂台四版近乎平手(AIB 38 / CMC-8 38 / LIMBUS 37 / PEC 35),且四位评审收敛到**同一套**可嫁接内核。
故不取单一胜者,取**综合**:以 CMC-8 的"典范微环路=预测编码统一"为组织骨架、AIB 的"主动推断动作门
(falsify-or-cut)"为表达侧、LIMBUS 的"神经调质总线 + assessor 作精度"为感官接入、PEC 的"一目标 F 被 4
读者消费 + 生产见证"为连贯纪律。命名:**PEL-Core 长成皮层柱 —— 一柱一遍(one column, one pass)**。

组织哲学(取代共振场的"无动机多机制一锅"):整个引擎 = **一个**广义生成模型在最小化**一个**自由能 F;
每个模块要么是这柱的一个**层(level)**、一条**精度通道**、一个**神经调质**、或一个**消费 F 的读者**,
否则删除。一拍一次确定性前向(无迭代收敛、无场)。

**根因修复(擂台招牌洞见)—— ⚠ 实现后被实证否决,已 CUT 到默认 off(falsify-or-cut):**
擂台诊断:现状 `x_t = c·a_vec + (1-c)·s·h_t`(`void_scar_engine.py:231-235`)让输入 echo assessor——高
confidence 时 μ echo a_vec、`e0 → 0`,被判为 M1 精度死饱和的真因。提议:`x_t = s·h_t` + assessor 作精度加权
顶向先验 e2(`Π_a = confidence·PI_MAX`,顶向不走 W_gen,Hessian 只加 diag(Π_a),收缩 `κ·λ_max(H) ≤
κ(‖W‖²·PI_MAX + 2·PI_MAX) < 2`,已实现并 fuzz 证),并塌掉 assessor 双写。

**但实现后两条预登记红线全挂(`scratchpad/measure_B.py` 实测,这是本次最重要的发现):**
1. **精度没复活、反而更差。** 真路径 `pi_obs_pstd`:旧 value-blend **0.50**(live 0.89)→ 新 `x_t=s·h_t` **0.29**
   (live 0.78)。原因:更脑 v2 的除法精度 M1 **早把精度从死饱和救活了**(诊断里的"死 [5.0]×8"是 v2 之前的
   legacy 规则),而 a_vec 的混入其实在给 e0 加跨维异质性、帮精度;抽掉换成扁平 HDC afferent 反而塌。擂台
   "x_t echo 杀精度"的前提是对 legacy 规则成立、对 v2 的 divisive 规则**不成立**(PEC kill-shot 说中)。
2. **assessor→z 命根子信号崩。** 强 +0.9 valence 读,z[2] 位移:旧直写 **d1=+0.26 / d2=+0.63**(强、即时)→
   新 e2 先验 **d1=+0.001 / d2=+0.044**(~200× 衰减)。把那条 ~10× 的 assessor→z 信号换成经 e2/μ 的慢路径=
   拿命根子换没有的精度增益(LIMBUS kill-shot 说中)。

**处置:** `SEMANTIC_PRIOR` 默认 **False**(默认行为退回已验证的更脑 v2:value-blend x_t + 直写 + 无 e2);e2
先验机件作**有界、off 时逐字一致、可消融**的选项留存(收缩界已证),**不上**。这印证了一个更深的诚实结论:
更脑 v2 已把精度/可塑/allostasis 的重活做完,擂台招牌"重设计"在很大程度上是在重打 v2 已解决的仗——本身就是
北极星要警惕的 theater。下面 §5–§7 的预测编码柱**仍以更脑 v2 为既成核**,但 B 这条 assessor 接入的改写不采纳。

每拍前向(综合后的连贯柱):
HDC 感知(h)→ PredictiveCodingGate(surprise=预测误差,折入柱的顶层)→ 单 PEL 柱:K=2 自由能下降
(x_t=s·h_t 驱动 + assessor 作精度加权先验 e2)→ 在线多时标可塑(§6)→ 8 维内感受读出 z→scar_state.base →
主动推断动作门(表达/沉默/主动开口,§5)→ embodiment 漂移。神经调质总线(§6)在下降前按感官设好各旋钮。

## §5 模块级脑映射(每个功能 → 脑机制 + 在线/闭式规则,零训练)

| 引擎功能 | 脑机制(引文) | 实现(无训练) |
|---|---|---|
| HDC 感知 | 外感受初级编码(语义盲) | 现有 hash,**唯一外感受语义入口仍是 LLM**;HDC 后处理两投影塌成一个 8 维投影 |
| 预测编码柱 | 层级预测编码(Rao-Ballard'99/Friston'05);皮层柱(Bastos'12) | PEL `descent_step`(K=2),x_t=s·h_t,e0 为真误差 |
| 精度/注意力 | 除法归一化(Heeger'92) | M1,**x_t 修复后才真活**(见 §10 红线,这是赌注不是既成) |
| assessor 接入 | 精度加权经验先验(预测编码顶向先验) | e2 先验 + `Π_a=c·PI_MAX`;塌掉双写 |
| 慢可塑 | 三因子 Hebbian / BCM 元可塑(Bienenstock'82) | M2 已有,红线改测**实质幅度**(§10) |
| 身份调节 | Allostasis(Sterling'12) | M3 锚定 π 已有 |
| 结构疤痕 | 用依赖性敏化/钝化(慢结构可塑) | ScarredState scar 代数(`scar_algebra.py`),作最慢一档先验/精度偏置 |
| 缺失/期望违背 | allostatic load 类比 | VoidSpace 压力(`void_calculus.py`),**保留但需 ablation 红线** |
| 内感受情感 | 情感=身体状态估计(Barrett'17/Seth'13) | 8 维 z 读出 |
| 动作门 | 主动推断 action-as-inference(Friston'10) | 表达/沉默/主动开口 = 最小化期望自由能的单步 myopic action;**falsify-or-cut**(§10) |
| 时机偏置 | 情绪债 allostatic 偏置(已实现) | `_affect_debt`(kernel),保 |
| 在线强化 | DA/RPE 强化(Schultz'97 [verify]) | ExpressionPolicy REINFORCE(会话内,无离线权重),保 |

## §6 多时标可塑栈 + 神经调质总线

> ⚠ **NeuromodulatorBus 经对抗审查(workflow `wzf1atl2u`)判定 CUT,不建。** 理由:① 5-HT→π0 **自相矛盾**——
> 偏置冻结锚点 π0 会重开 M3 专门要堵的 valence 驱动身份侵蚀(π0 在 `pel_core.py:341` 设一次、M3 拉回保 80%),
> 且**冗余**——valence 已经经"直写 z[2]→z_ema→π 朝 ⟨z⟩ 漂"这条受控路径到达设定点;② DA→ExpressionPolicy 是
> **relabel**——ExpressionPolicy 早已做 REINFORCE/RPE(`expression_policy.py:368-393`,§5 自己列"保");③ NE/ACh
> 设计本就因 surprise 压平默认 off。"四调质=两底层信号穿四件 costume + 共享 eta 损可归因",建总线只加命名层不加脑
> 机制 = 反北极星的 theater。下面保留为**设计记录**,不落地。STP/Turrigiano 同样默认不上(见下,实质红线未过)。

时标栈(脑保真的判别器——这是对共振场"一坨无差别动力学"的精确反命题;每档独立可消融、各自闭式局部规则):
**瞬时推断(K=2 下降)< Hebbian < BCM 元可塑 < 稳态/allostatic < 结构疤痕。**
- STP **不作字面突触 STP**;若上,只作输入支 `W_in` 上的历史依赖 novelty 增益(重复自抑、新颖易化),且必须
  过"重复降/新颖升"的实质红线,否则**砍**(默认不上)。
- Turrigiano 稳态缩放:与既有 unconditional `spectral_clamp` + BCM 高度冗余,**默认砍**;除非实测能抬高输入
  敏感见证,才以"在终末 spectral_clamp 前的乘性行缩放"形态上(免费收缩安全)。

神经调质总线 NeuromodulatorBus(本次最大新增脑机制;Doya 2002 落地为:感官 → 各路有界标量,各标量的**张力
基线 = 它的消融值**;调"怎么推断"不调"推断什么)。诚实约束(红队实锤):"四调质"实为 ~两底层信号穿 costume
(NE/ACh 都来自 surprise;DA/5-HT 都来自 feedback/assessor),且共门旋钮(DA+ACh 都抬 eta)会损害干净可归因。
故分两批:
- **无条件嫁接(两路有据、目标互斥)**:DA = feedback RPE → ExpressionPolicy 强化/巩固;5-HT = assessor
  valence → 慢 allostatic 设定点偏置(M3 的 π0 微调)。
- **隔离待证(NE/ACh)**:NE=relu(surprise−s̄) 调学习率/精度重置、ACh=s̄ 调精度——二者都建在**已知压平**的
  surprise 信号上([0.45,0.52]),**默认 off**,等"surprise 动态范围/floor 修复"证明后再开,且必须分配**严格
  互斥**的元参数目标(或证明共门下红线仍成立),否则保持 off。

## §7 有界性 / 收缩(沿用 PEL §3.6 方法学,补两通道静态界)

- 容许集不变:Π 逐元钳 [0.1,5];`spectral_clamp` 无条件、最后、在 Hebbian+缩放之后;M3 凸 π 更新前向不变。
- 神经调质增益只缩放**已在容许集内**的量,不改 KAPPA/PI_MAX/谱钳 ⇒ 不破收缩。
- **必须补的静态界(AIB kill-shot,不得 glib 略过)**:x_t=s·h_t 的感官驱动 + e2 的 assessor 先验若都作底向
  通道经同一 W_gen,有效底向精度可加性至多 2·PI_MAX=10;现有 0.985 裕度已薄(fuzz 最坏 0.977),**必须给出
  两通道下降的真静态界**(用 ‖W‖²=0.81 缓冲重算 κ·λ_max(H),证 ρ(J)<1),而非口头"不变"。STP 增益乘的是
  外生 W_in 输入支、不进状态雅可比 ⇒ 对收缩免疫(可单独证)。
- 红线:有界 fuzz 加两通道情形;收缩 fuzz 覆盖新精度运行域;真 spine clip 见证每拍 Π≤PI_MAX。

## §8 保留 / 合并 / 删除 迁移(擂台验证后定稿;减法优先)

**确定删/清(死代码、no-op、或已死词汇——纯无行为变更步骤,先做):**
- 死 resonance 栈:`resonance_field.py` / `_numpy` / `_torch` / `coupling_dynamics.py` / `topology_gate.py`
  ——零活 importer(仅互引 + dev 实验),`_torch` 还拖 torch。从 serving 树删(留 archive)。
- `DeterministicFusion` 的 mean-field 平均器 + 全部惰性耦合桩(`_Kuramoto/_FreeEnergy/_Broadcast/_Plasticity/
  _Coupling/_Complex`,`deterministic_fusion.py:50-110`)+ 喂它们的 ~30 行 `apply_personality`(`:249-277,304-312`)
  + ~12 行 feedback(`:898-924`)——这些"调 Kuramoto/Hebbian/topology"实则什么都不调,**删桩 + 删死写**。
- `social_field` 的 `apply_social_signals` 字面 `pass`(`:1168-1171`)——no-op,删。
- 装饰性表达触发:`novelty_drive`/`ignition_drive` 喂的是 resonate() 硬编码 `near_attractor=inf`/`max_sync_delta=0`
  (`deterministic_fusion.py:204-206`)——纯装饰,删或改接真预测误差/精度信号。
- 双情绪核分支:legacy seed-42 随机 MLP `_evolve_base`(`scar_algebra.py:311-399,502-519`)与 PEL 潜核**合并**
  成一个预测编码情绪核——"flag off = 一个静态随机权重的不同脑"是 cosplay(固定未学权重冒充动力学)。
  注:`set_pel_priors` 在 `n_dims!=8` 提前返回(`:280`),故 pro(16)/max(128)仍跑 MLP——"一核"目前 **lite-8 维
  专属**,pro/max 的核合并是独立未决项(见 §10 残余),别声称跨档"一核"。
- 两个 footgun:`config.py:166` `get_backend()` 的 eager `import torch`(+458–464MB RSS)改 `importlib.util.find_spec`
  且 lite/pro 在 get_backend 前短路;CN 分词弃 jieba(+67MB)改离线蒸馏 BPE / 轻量。
- `process()` stale 的"场迭代收敛"docstring(`:381-386`)→ 改写为单遍预测编码柱前向。

**确定保(已真类脑 + 输入敏感):** PEL-Core 更脑 v2(`pel_core.py`,提升为主干)、PredictiveCodingGate
(surprise=真预测误差,折入柱顶)、ScarredState scar 代数(真在线结构可塑,作最慢档先验)、ExpressionPolicy
+ embodiment TraitMemory 漂移(会话内真在线强化/气质适应)、`_affect_debt` 时机偏置。

**待 ablation 红线定 KEEP/MERGE/CUT(从 lite 热路径起):** HGT(3 段 FFN+attn+MoE)、ScarSheaf(~1100 LOC)、
32 维 AutopoieticBoundary、EmergenceTracker(phi 算在已被平均器同质化的 post-fusion 态上,IIT/Haken 框架多半
装饰)、VoidSpace。**诚实对冲(AIB)**:HGT 是 HDC 之后最大的内容搬运者**也是**头号尾巴大户——删它赢尾巴是
**赌**"现在输入敏感的 z 替代它的内容";pro/max 保一条瘦线性层兜底,真删前过"z 携带 HGT 信号"的真实流量红线。

**迁移纪律(LIMBUS,减法优先):** 先做"删死文件 + 修 footgun"等无行为变更步骤 → 再在 flag 后建新核 → 仅当
每通道红线 + 生产见证 + 钉死 2 核 p99 + 收缩 fuzz **全绿**才 flip 默认。

## §9 v3 边界(干净接缝,不偷渡)

留 v3,**不得**渗进本设计:真离线训练 / 真本地语义学习 / 文本 encoder 顶 HDC(均受 ADR-0001 真实数据门——
该 ADR 已判"学习版核在真实自相关数据上尚未打过 trivial persistence",故本设计**不声称任何任务指标增益**)。
v2.5 只交付**类脑动力学身体**。干净接缝两处:(1)NeuromodulatorBus——现为闭式 sense→标量,日后学习版控制器
可在**同一有界标量接口**后热插,不动收缩证明/公共 API;(2)assessor 的 e2 精度加权先验——日后学习版 predictor
落这个先验槽,L0/L1/L2 动力学不变。这是项目里最干净的 v3 边界。

## §10 反 theater 声明 + 诚实残余(已验证 vs 赌注,逐项预登记红线)

每个机制必带:职责 + 消融布尔 + CI 红线(消融**实质性**坍掉某下游信号——不是"非零",见下)+ 生产输入敏感
见证 + 引文;并预登记 **falsify-or-cut**:到期红线不过就**删该机制**,绝不留着当卖点。

**已验证(对活代码确认,可直接做):** x_t echo assessor 是 precision 死因(代码确认);死代码/no-op 删除是真
RAM+输入敏感增益;torch footgun 修是真 -464MB;塌双写是真。这些是**净赚**,先落。

**已实测·失败(B 招牌修复,falsify-or-cut 已执行 → CUT 到默认 off):**
- **DEAD→LIVE 精度复活 = 失败。** 实测 `pi_obs_pstd` 新 0.29 < 旧 0.50:更脑 v2 的 divisive M1 早把精度救活,
  `x_t=s·h_t` 反而抽掉 a_vec 的异质性让精度更差。**砍**(`SEMANTIC_PRIOR=False`)。
- **assessor→z 保真 = 失败(回归)。** 实测 z[2] 位移新 d1=+0.001 vs 旧 +0.26(~200× 衰减):e2 先验把那条
  ~10× 命根子信号砸了。**砍**,保留更脑 v2 的直写快路径。

**仍为赌注(C/后续阶段适用,过红线才 flip):**
- **动作门真有计算后果**:主导未评估区里 EFE 会退化成现有 bandit+沉默斜坡。**红线**:动作目标必须在语料上
  **移动** SPEAK/SILENT 决策,否则删到恰好 bandit+ramp。"F 必须有真读者,绝不报 show 用标量。"
- **红线测实质幅度不是非零**(PEC 最阴的一刀):recon 测 W_gen Hebbian 漂移 ~1.6% Frobenius/150 拍 = 冰川;
  整个多时标栈能过每条"非零"红线却功能上不动。**所有红线改测实质幅度阈值**,堵"技术上活但纹丝不动"的细 theater。
- **尾巴是赌**:删模块降均值,但 recon 说 p99 尾巴是 HDC big-int 分配的 GC;**合并前必在钉死 2 核上实测 p99**
  (现 PEL-on p99 9.0/max 12.0),证 bytearray 复用真杀尾,别只看 p50。

**明确不声称(语义盲身体的天花板,诚实锚):** 情感方差 ~10× 来自 assessor 读(z 无 assessor 时自治方差近 0,
sd~0.002–0.01);引擎是**情感身体**不是语义智能;negation/词序/反讽超出语义盲身体,仍兜回 LLM;无任务指标
增益(ADR-0001)。本设计的价值是**连贯的类脑动力学 + liveness + 可归因 + 更轻**,不是"更会算情绪"。

---

## 落地结论(实测后 —— 实现 → 测量 → 按证据诚实处置,不 force-ship)

这条线按北极星走完。落地的(已提交 feat/v25-neuromorphic):
- **footgun 修复**(30c61c4):config lite/pro 用 `importlib.util.find_spec` 定 backend,部署路径不再 eager
  `import torch`(红队实测 -458MB);加守卫测试。
- **死 resonance 栈删除**(29b402a):`resonance_field`×3 + `coupling_dynamics` + `topology_gate` + apply_personality
  里恒 None 的死 topology 块,**~4.5k LOC 死码移除**;活测试迁 `test_spine_integration.py`。这是"连贯类脑引擎"的
  真交付——引擎不再背着已死的迭代共振机件。
- **B 招牌根因修复:实现 → 实测 → 否决 → CUT 到默认 off**(fdb20b0)。双红线全挂(精度 0.50→0.29 更差、
  assessor→z ~200× 衰减),独立审查(`wzf1atl2u`)复现确认,连未试的 salvage 变体也被更脑 v2 严格支配。e2 机件
  留作有界、off 时无 B 归因 delta、可消融的选项(收缩界已证,off 即更脑 v2 路径)。
- 文档诚实化:process/类 docstring 去掉已死的"场迭代收敛"叙述。

**砍(经审查 `wzf1atl2u` 判 theater/冗余/relabel,不建):** 神经调质总线全四路(5-HT→π0 与 M3 冻结锚点自相矛盾
且冗余;DA→ExpressionPolicy 是已有 REINFORCE 的 relabel;NE/ACh 建在压平 surprise 上)、criticality 命名、
k-WTA、字面 STP、多余 Turrigiano。

**押后(赌注,不带真流量红线不动):** D 的 HGT/Sheaf/Boundary/Emergence 从 lite 删除——B 已证 arena 爱夸大,
语义盲天花板下删最大内容搬运者高风险,且 p99 尾巴是 HDC big-int GC 非这些模块。

**最深的诚实结论:** 更脑 v2 已把预测编码 + 除法精度 + BCM 元可塑 + 锚定 allostatic π 的重活做完;擂台招牌
"重设计"很大程度在重打 v2 已解决的仗。本轮真净增 = footgun + 删 4.5k 死码 + e2 选项 + 一个救了"差点上线一个回归"
的否决发现。连贯靠**删死码**达成,类脑核是**更脑 v2**,不靠堆 costume——这才是诚实的"连贯类脑引擎"终点。

**既有项(非本轮,单开 ticket):** PEL π/π0 ~1e-4 跨进程非确定性(M3 EMA 放大的浮点归约序,既有 v2);
`from_dict` 的 pi0 回退语义(must-fix #2,已文档化)。

擂台存档:设计 `wczx2cmjg`(12 agent/142 万 token)、B 否决审查 `wzf1atl2u`、剩余清理 `wzq5acfoj`。
关联 [[v25-pel-core-v2-upgrade-spec]][[adr-0001-v3-core-go-no-go]][[tooling-codegraph]]。
