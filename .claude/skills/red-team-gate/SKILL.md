---
name: red-team-gate
description: SylannEngine 评审规程——任何实质性设计/实现/文档产物在"算数"之前必须走的对抗闸。适用于新机制设计、E 律/引擎核心改动、标准文档修订、以及任何声称"字节一致/零行为变更"的交付。触发词：红队、red team、对抗审查、评审闸、超级标准流程。
---

# Red-Team Gate —— SylannEngine 评审规程

固化自 v26 超级标准 Campaign 的实战流程（设计四道闸 → 数学红队 → 实现红队 → 终审）。
实战战绩（逐轮、可对账）：T 轨终审 8 major + 2 minor（confirmed 10/10）；B 轨数学红队
2 fatal + 10 major；A 轨 8 confirmed（约 7 major）——三轮独立红队合计约 25 条
fatal/major，全部处置，且每轮都逮到过"红队自身幻觉"或"作者假前提"各至少一例。
**核心纪律：每轨产物过独立红队后才算数。**

## 流程（五步，顺序执行）

1. **落地对账（grounding）**：动手前把设计主张逐条对到 canonical 代码的真实 `file:line`。
   设计稿可能是在别的分支/fork 上写的——**文档链里的错会遗传**（实例：上游调研称某函数
   "零调用点"，实际每回合都在被调，错误结论被原样搬运进呈报）。每条主张标
   matches / drifted / wrong / missing 四态。
2. **分阶段闸位实现**：Gate A（只算不写影子，字节一致）→ Gate B（夺权，flag 后的有意
   行为变更，fail-closed 回落）→ Gate C（不可逆权威写，原子提交 + 回滚环）。每阶段
   独立 commit、独立可回滚、全量测试绿。默认 flag 全关。
3. **独立对抗红队（workflow）**：按攻击面拆 3–5 个镜头（如 gating / math-wiring /
   parity / methodology-honesty），每镜头一个 agent，prompt 明令 "BREAK it, not admire
   it"，要求**对真代码验证每条攻击**（跑 python/pytest 复现，给 file:line）。attacker
   用 sonnet 档，结构化输出 {verdict, findings[{severity, target, claim, attack, fix}]}。
4. **主循环亲验承重主张**：红队自己也会幻觉（实例：咬定一个存在的测试文件不存在）。
   所有 fatal/major 在动手修之前由主循环亲自复核；分类器缺席警告出现时尤其要验。
5. **折叠 + 记录**：每条 confirmed finding 修复或显式带理由拒绝；修复 commit message
   逐条对应；文档类产物把"红队修订"标注在被改处（错误结论要留尸体示众，不静默改写）。

## 硬规则（红线）

- **字节一致类主张必须实证**：跑真对拍（基线 worktree vs HEAD、同驱动、快照逐字节
  diff），且必须 `random.seed(0)` + `PYTHONHASHSEED=0` 双播种——本仓库
  expression_policy/meta_learner 用未播种全局 random，不播种时 diff 全是探索噪声假阳性。
- **不可逆操作等显式 go**：合 main / 打 tag / 发 PyPI / flip 默认 flag，CI 绿 ≠ 授权。
- **常数即契约**：E 律常数被 `tests/test_conformance_vectors.py` 钉死（spec §13.4）；
  改常数 = 改动 + 重钉向量 + spec changelog，三件同 commit。
- **呈报不替用户做主**：产品手感决策（如"隔夜该多冷"）只呈事实、数字、选项与倾向，
  拍板留给用户。
- **诚实定位**：经典机制的工程实例明说是工程实例；具名贡献先过文献对标；
  "论文级/定理级"等自我描述与证据水平对齐（参照 affect-dynamics-derivation.md v2
  的降格先例——"分离定理"降为引理）。

## 快速模板（红队 workflow 骨架）

```js
const FINDINGS = { /* verdict + findings[] schema，见本目录 workflows/ 下副本 */ }
const LENSES = [ { key: '...', prompt: `${COMMON}\nLENS: ...攻击面清单...` }, ... ]
phase('Attack')
const results = await parallel(LENSES.map(l => () =>
  agent(l.prompt, { label: `attack:${l.key}`, model: 'sonnet', effort: 'high', schema: FINDINGS })))
```

历史脚本（副本随仓库走，可直接改用）：本 skill 目录下
`workflows/derivation-math-redteam.js`（数学推导四镜头）、
`workflows/a-track-redteam.js`（实现四镜头）、
`workflows/v26-final-redteam.js`（全 diff 终审 + fable5 判决）。
