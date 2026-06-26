# HANDOFF — v2.5 PEL-Core "更脑 v2" 迭代

> 给新会话接手用。本会话(脏了)把设计跑完并红队+完整性批判过,**未实现**。新会话从「下一步」起手。

## TL;DR — 现在在哪
- v2.5 **PEL-Core 已 ship**(v1),藏在 config flag `pel_core_enabled`(默认 False),lite 8 维专属,分支 `feat/pel-core`(5 commit 371433b→ae5dd16,版本 2.1.0)。全量 580 绿、`_field` 字节未动、契约保住,已独立复核。
- **「更脑 v2」= 让脑机件在真实流量上真的活起来**(不是做大)。设计已定稿、红队过、完整性批判过(workflow `wbzee2fts`)。**尚未实现。**
- 实测病理(recon 钉死):真 spine 路径上精度 Π 全钉在 `[5.0]×8`(100% 饱和,跨维 std=0)→ 注意力死;W_gen 漂移弱;π 往 0 漂、身份侵蚀;无 metaplasticity。

## v2 设计(权威 spec)
全文:`docs/design/v25-pel-core-v2-upgrade-spec.md`。三机制,全在现有 flag 后,各自独立可消融:
- **M1 除法归一化精度**(budget 守恒)— 解饱和(跨维 std 0→0.67 实测)。替换 `pel_core.py:289-300` + 新 helper `_divisive_precision` + 新常量组。
- **M2 BCM 式滑动阈值元可塑增益** 加在三因子 Hebbian 上 — 多时标 θ(~100 拍)。替换 `pel_core.py:281-287`。
- **M3 锚定 allostatic π** — 朝 ⟨z⟩ 漂 **且** 拉回冻结的 trait 先验 π0 — 止住身份侵蚀(渐近保留 ~80% π0)。替换 `pel_core.py:309-312`。
- Schema bump v1→v2(+`pi0`、`theta`、`s_bar`)。**收缩证明已重验通过**:κ·λ_max(H)=0.635≪2;精度只经"每维 max"进雅可比,budget 归一化不进上界;π 凸更新前向不变(d+a=5e-3≤1)。11 条红队 must-fix 全折入。

## 上线前硬 MUST-FIX(来自完整性批判 `v25-pel-core-v2-critic.md`,实现时必带)
1. **CI bug:** 测试 #15(b) 的 θ 方差阈值(1e-4 / 1e-6)会**误杀一个正常工作的 BCM**(实测 1.8e-5 / 3.4e-7)。**删掉这两条**,M2 改用 m-spread(0.58)+ path-length 当见证。温度二级 tol 只 2.3× 偏薄,软化或降为 observability。
2. **快照迁移语义坑:** v1 回退 `pi0 := data["pi"]` 会把**已经漂走的身份**当锚点冻住(不恢复真 trait 先验)。须文档化;最好 host 首次加载时重调 `set_pel_priors`(它有人格)恢复真 π0。
3. **既有 flag 泄漏(v2 默认开后更严重):** `scar_algebra.py:708` 一旦快照里有 `"pel"` 键就强制 `_pel_enabled=True` → 即便 config flag 关,快照也能把 PEL 打开,破"flag 关=字节一致"。修或显式标注。
4. **生产侧见证缺口(头号风险):** 所有 CI 门都读 curated CORPUS;除法归一化的 liveness 是**数据依赖**的——真流量若误差平坦,精度会再次饿死,而 CI 仍全绿(读的是精选语料,不是真流量)。**合并前必加**:把 `cross-dim pstd(pi_obs)` + 乘积 spread `var(pi_obs·m)` 暴露进 `pel_diagnostics()`,真流量上发射,稳态窗 spread 跌破 T-DIV tol 就告警。这是让"我们语料上活"变成"生产上死了能被发现"的唯一办法。
5. 数值:真实 max η = **0.015**(非 spec 写的 0.01),如实写。措辞软化:"four-timescale self-modifying stack" → "multi-timescale input-driven modulation"(别沾共振场的"无目的自治")。

## 待拍开放项 E-1…E-7(spec §7 都带推荐)
载重的:**E-4**(`pel_core_enabled=True` 时 v2 即为 on-path 默认,不另开第二 flag)荐 yes;**E-1**(budget+clip 除法形式)荐 yes;**E-2**(eta_w ×5 复原设计均值)荐 yes;**E-5**(surprise-gate 出厂关)荐 yes;**E-3**(RHO_ANCHOR 4e-3)荐 yes。其余 E-6/E-7 见 spec。确认或改。

## 下一步(新干净会话照做)
1. 拍 E-1…E-7(或全默认放行)。
2. 把 v2 spec 折进 `docs/design/v25-pel-core-techspec.md` 作 §3.5/§3.6 + 测试行 #13–#19(**带上 critic 的 CI 阈值修正**,别照搬 #15(b) 的错阈值)。
3. 在 `pel_core.py` 落 M1/M2/M3(spec §1 给了逐行替换 + 常量 + helper)+ schema v2 + 上面迁移/flag 修复 + 生产见证 diagnostics。
4. 开 build workflow(仿 `wj6ul0nh8`):implement→对抗 review→audit 到全绿。**硬规矩**:绝不改弱现有测试;默认 flag 关时全量保绿;PEL-on 的 #1/#2/#5/#8/ablation 重验(**别预先放松 tol**,观测到再调)。
5. 自己独立复核(跑全量 + codegraph sync + 契约检查)。再定 push/merge/下游。

## 物料与指针
- 分支 `feat/pel-core`(2.1.0)。核:`sylanne_core/compute/pel_core.py`(376 行)。接线:`scar_algebra.py:471-476`(dispatch)、`:703-708`(快照)、`:227-236`(diagnostics);`resonance_integration.py`(x_t 装配、assessor_advisable、free_energy 键)。
- 设计文档:`v25-pel-core-{prd,design,techspec}.md`(v1);`v25-pel-core-v2-{upgrade-spec,critic,recon}.md`(v2,本会话落的)。
- 设计 workflow:`wbzee2fts`(transcript 在 `.../subagents/workflows/wf_f5059f43-4ee`)。饱和复现脚本:`scratchpad/verify_pel_v2.py` 与 `recon_pel_saturation.py`(scratchpad 是临时,要长留就拷进 repo)。
- 工具链:`ruff==0.14.2`(E,F,W,I,UP,B,SIM;E501 ignore)、py310、行宽 100;`mypy strict packages=["sylanne_core"]`;`pytest tests/`。(2 个 pre-existing mypy stub 错 jsonschema/cupy,非 PEL。)
- **codegraph 已修好可用**:本会话发现它的 MCP 被误写进 `C:\Users\pidan\.claude.json`,而真配置在 `G:\claude-data\.claude.json`(CLAUDE_CONFIG_DIR);已挪到正确处,`claude mcp get codegraph` = √ Connected。SylannEngine 已索引,改完代码 `codegraph sync` 再用 callers/impact/explore 复核。

## 环境收尾(本会话遗留,干净会话里处理)
- **content-create 插件**:5 个 MCP 全挂(minimax/wenyan/lark 要你没有的 API key;rss/redbook 现下载超时),跟 Sylanne 无关。你已选卸载 → 跑 `/plugin uninstall content-create@xyzbit-plugins`(slash 命令我代跑不了)。
- **dev-enegine skills 路径报错**:**已修**(在插件 cache 建了缺失的 `skills/` 空目录)。
- **mcp-all-in-one + dev-enegine playwright**:npx/uvx 启动超时(裸命令不在启动器 PATH / 重下载)。你选了"试修启动"——可预热 npx 缓存、或命令换全路径、或不用就禁掉。

## 不可违反的约束(沿用)
- 不训练、不碰语义(那是 v3);只在线局部可塑;LLM/assessor = 感官。
- 公共 API 冻死;`_field`(DeterministicFusion)字节不动;默认 off flag;每拍便宜(<10ms CI);有界+收缩闭式可证。
- 反 theater:成功 = 真实路径上的 liveness + 跨维分化 + 多时标调制,**不是**指标赢(离线证不了)。别吹过头。
