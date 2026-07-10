# 超级标准 Campaign —— 情感动力学从"设计"升格为"标准"

日期 2026-07-10 · 分支 `feat/v26-affect-dynamics` · 状态：进行中

用户指令：四个方向全要 + **论文级别推导**。四轨按依赖排序执行——推导先行（它是 punch-up
的设计数学与标准的引用基座），代码补齐居中（标准不准写桩），标准与 SOP 收尾。

## 轨道与顺序

**B. 论文级推导（先行，本文档的姊妹篇 `affect-dynamics-derivation.md`）——✅ 已完成（v2）**
形式化 E 律全系统：不变集/有界性定理、指数收敛与收缩率、scar 粘滞的一致指数稳定、
快-慢双时标耦合的有界漂移定理（锚回弹半径）、delta-rule 增益可塑性的投影稳定性设计
（**先证后写**）、迟滞抗抖的换标频率界。
**红队结果（2026-07-10）**：四镜头裁定 3×SOUND_WITH_FIXES + composition BROKEN；
2 fatal + 10 major 全部处置——3 处代码闸（`_trait` 域强制 / `from_dict` 复原契约 /
`_affect_decay` 入口皮带，commit `b1636ab`，798 绿）+ 推导 v2（commit `76987b0`）。
**贡献收窄**：原"分离定理"（C3）降格为投影不变性引理、退出具名贡献；定理 5 按出厂
递推（q 双调制）重证；标题从"论文级"降为"定理证明级内部草案"；§9 补齐心理学
affect-dynamics 文献对标（Kuppens/DynAffect、kindling、Loossens）。具名贡献余
C1（scar 耦合时间常数调制）+ C2（工程契约级锚回弹有界可塑性）。

**A. Punch-up 实现（依赖 B 的 delta-rule 数学）**
1. assessor schema 直出 `intent`（修死路；注意：接电即激活 canonical 里从未活过的
   意图路径，须 gated + 行为对拍）；后续演进为直出 8 维 appraisal。
2. G 上 delta-rule 可塑性（按 B 的投影收缩设计：`G⁺=Π_{[ε,1]}(G+α·δ·φ)`，
   有界性与学习解耦）。
3. R 接活（`_relationship_deltas`→[0,1] 相位标量的映射需显式决策）+ Sylanne-Six
   桥接或删死项（二选一，不留矛盾 docstring）。
4. warmth 行为标定 harness + "隔夜该多冷"产品决策呈报（文献常数不替用户做主）。

**C. 标准化（依赖 A/B：标准里没有死路、常数有行为背书）**
1. 情感动力学专章入 `docs/theoretical_spec.md`（公理化 + 定理引用 B + conformance
   测试套件映射：每条定理 ↔ 一组 property test，Theorem 1 ↔ 现有
   `test_bounded_given_gain_le_1` 谱系）。
2. 全引擎标准升级：SPEC/theoretical_spec 版本化、conformance 等级（L1 纯函数一致 /
   L2 动力学一致 / L3 全管线一致）、参考测试向量、协议演进规则——服务 SDK 定位。
3. PEL 取舍论证与退役路径写进标准（coherence 镜头 3 分的病根：撤退不许再沉默）。

**D. 评审 SOP 固化（收尾）**
把本轮流程（canonical 落地对账 workflow → 分阶段闸位实现 → 独立对抗红队 → 多镜头
设计终审 → 主循环亲验承重主张）固化为仓库评审规程（`.claude/` skill/workflow 文件）。

## 红线（继承）

每轨产物过独立红队后才算数；不可逆操作（合 main/tag/发布/flip flag）等用户明确 go；
"字节一致"类主张必须实证（播种 `random.seed(0)`+`PYTHONHASHSEED=0` 对拍）。
