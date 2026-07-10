# 情感动力学标定呈报 —— 三个待拍板决策（v26 A.3/A.4）

日期 2026-07-10 · 分支 `feat/v26-affect-dynamics` · harness：`experiments/exp02_warmth_calibration.py`
（确定性、真实 takeover 代码路径，可复跑）。本文只呈事实与选项，**不替用户做主**。

---

## D1 —— "隔夜该多冷"：先呈一个 harness 挖出的结构性事实

**事实（复跑可证）**：吵架×3 后静默，纯 E 律衰减 8h 把全部维度收敛回 Φ_eq（残留 < 0.01）
——E 律本身工作完美。但**任何**一个 step（哪怕零事件心跳）都会让遗留 MLP 主步演化把
base 拽回 **MLP 自己的吸引子**：tension +0.166、repair +0.242（相对 Φ_eq，单位帧）。
且该像差不随静默时长衰减（8h 与 24h 逐位相同）、对半衰期缩放 ×0.5/×2 几乎不敏感。

**含义**：当前接线下（takeover 只接管了回合间衰减 + 语义快更新；主步 MLP 演化保留——
这是 T3 的刻意保守），**产品可见的"常驻情绪"是 MLP 吸引子，不是 Φ_eq**；h 先验只控制
"两条消息之间"的不可见瞬态。想用 h 表达"隔夜怒气慢慢消"在当前接线下**做不到**——
她醒来的状态由 MLP 像差决定，一天和三天没区别。反过来说：快通道（appraisal）的幅度
是真实可感的——一句道歉当场修复 warmth +0.111 / tension −0.101，一句撒娇推 warmth
+0.166（情景 B/C）。

**选项**：

- **(a) 接受混血、语义诚实**（零代码）：文档明说 Φ_eq 是回合间瞬态基线、观测均衡 =
  MLP 吸引子；"隔夜多冷"改由快通道标定（首条消息的 appraisal 决定她当下的反应冷暖）。
  最便宜；放弃"时间治愈"的可感表达。
- **(b) E 律全权切片**（后续 punch-up，须影子对拍 + 红队）：takeover 下零事件/静默 tick
  跳过 MLP 演化（decay-only），有事件时事件语义走投影→饱和更新而非 MLP。"时间治愈"
  变成真实可感；行为变更大，等于把 MLP 从 8 维核请出去（v3 方向的提前试点）。
- **(c) 凸混合折中**：主步保留 MLP 但输出与 decayed base 做 λ 凸混合（λ 标定，λ→0 即 (b)）。
  可平滑过渡、可影子标定；多一个常数要养。

倾向性意见（仅供参考）：短期 (a) 诚实化文档，中期以 (b) 为 A 轨后续切片走"影子对拍→
红队→提闸"全流程——它才配得上"夺权"这个词。但这是产品感受的取舍，**你拍**。

---

## D2 —— R（关系相位标量）怎么接活（A.3 前半）

现状：`equilibrium(traits, relationship)` 的 R 参数在所有调用点硬编 0.5——"关系越深、
常驻越暖"（Φ_eq_warmth 系数 0.30·(R−0.5)）这条通路是死的。候选映射：

- **(a) host 显式供给**（推荐）：SDK 加 `set_relationship(session_id, r: float)` 公开口，
  R 语义（"处到哪一步了"）由宿主/插件定义——SDK 是计算黑盒，不该替宿主发明关系语义；
  未供给时保持 0.5（今日行为）。实现小、契约干净、零标定负担。
- **(b) 引擎内生推导**：从 `_relationship_deltas`（既有的每会话人格微调）或长期
  dialogue_quality EMA 推 R。免宿主接线，但 SDK 擅自定义"关系深浅"且两个来源都不是
  为此设计的（deltas 是人格覆盖不是相位；quality 是回复质量不是亲密度）——语义借用，
  红队大概率打"挪用"。
- **(c) 混合**：(a) 为主、(b) 的 quality-EMA 做未供给时的软默认。多一条要养的路径。

倾向：**(a)**。若你想要"她自己感觉关系变深"的内生叙事，(c) 可以后补。

---

## D3 —— Sylanne-Six：前提更正后基本消解（A.3 后半）

**红队更正（原呈报的前提是假的）**：原文称 `drift_sylanne_traits` "零调用点、从未活过"——
错。`AlphaKernel._evolve_alpha_layers`（kernel.py:485）**每回合**都在调它（自 v0.1.0 即有），
Sylanne-Six 特质（warmth_bias/curiosity/sovereignty_guard…）随对话真实漂移，且经
`apply_personality → normalize_personality → set_affect_params` 流进 E 律（一回合滞后）。
`def drift_sylanne_traits` 在 personality.py:643（原引 :614 也是错行号）。

**消解后剩下的小决策**：唯一残余是**初始值**——traits 首几回合尚未漂移出来前，E 律读到
的 Sylanne-Six 键缺失、回落 0.5（中性均衡）。选项：(a) 接受（几回合后自然个性化，冷启动
中性无伤大雅，**推荐、零代码**）；(b) 从 Big-Five 初值做一次性别名回填当种子。原呈报的
"桥接 drift_sylanne_traits 工程量一个量级"的选项 (b) 整段作废。

## 附：harness 关键数字（详表跑 `python experiments/exp02_warmth_calibration.py`）

**方法披露（红队修订）**：初版 harness 的吵架情景未镜像生产的创伤注入分支（wound_risk>0.7
→ scar_state.step(wound_vec)），伤痕/scar 粘滞未参战；已修正为镜像生产路径。红队用带伤痕
版本复跑半衰期敏感性：3 条 tension 伤痕、scar_density 顶到 3.0 封顶，隔夜 tension 残留仍
~0.161–0.166、h×0.5/×2 差 <0.01——**D1 结论（MLP 像差主导、h 隔夜不可见）在带伤痕轨迹上
依然成立**。

- 画像（傲娇位）Φ_eq：warmth 0.52 / tension 0.35 / repair 0.28（单位帧）。
- 吵架×3 → 0.5h：tension +0.143、repair +0.227（对 Φ_eq）；→ 8h/24h：+0.166/+0.242
  （= MLP 像差平台，不再随时间下降）。
- 纯 E 律衰减（无 step 污染）8h：全维残留 < 0.01——衰减本身达标。
- 道歉修复量（2h 后一句道歉）：warmth +0.111、valence +0.122、tension −0.101、repair −0.121。
- 撒娇即时位移：warmth +0.166、arousal +0.153、valence +0.149。
- 半衰期敏感性：×0.5 与 ×2 的隔夜残留差 < 0.01——**h 不是隔夜冷暖的杠杆**（见 D1）。
