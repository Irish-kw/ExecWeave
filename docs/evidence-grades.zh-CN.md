<!-- i18n-nav:start -->
<p align="center">
  <a href="evidence-grades.md">English</a> |
  <a href="evidence-grades.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="evidence-grades.ja.md">日本語</a> |
  <a href="evidence-grades.ko.md">한국어</a> |
  <a href="evidence-grades.fr.md">Français</a> |
  <a href="evidence-grades.de.md">Deutsch</a> |
  <a href="evidence-grades.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# 证据等级

ExecWeave 的证据等级描述执行图中的 provenance 能以多强的程度支撑一个 finding。它不描述行为有多严重、多恶意、概率多高，也不代表 finding 一定正确。

## 目的

Finding 的 severity 与证据强度是彼此独立的维度。高严重度行为可能只由采样式证据观测到，而低严重度行为也可能具有很强的 syscall attribution。因此 ExecWeave 会同时呈现两者，而不会因为采集能力较弱就暗中降低 severity。

## 合约

| 等级 | 含义 | 当前推导方式 |
| --- | --- | --- |
| `A` | 直接、具因果性的原生归因 | 具因果性的 graph edge，且具有已认可的 `syscall` attribution |
| `B` | 直接、具因果性的采样进程归因 | 具因果性的 edge，且 attribution 为 `polling` 或 `process_polling` |
| `C` | session 关联或明确非因果证据 | edge 明确为 non-causal，或具有 `session_observation` attribution |
| `D` | 明确由推断或 heuristic 产生的证据 | edge 具有 `inferred=true` 或记录 inference method |
| `U` | provenance 未知或分类信息不足 | 缺少支撑、缺少 attribution、混合／未知 attribution vocabulary，或尚未被合约分类 |

这套 vocabulary 刻意采用保守策略。新的 backend 或 attribution 字符串不会自动被提升为更强等级；在合约明确扩展之前，一律保持 `U`。

## Finding 推导方式

每个 finding 原本就会通过 `edge_ids` 指向一个或多个 graph edge。ExecWeave 会使用 graph 中保留的 provenance 字段，例如 `causal`、`inferred`、`attributions`、`backends` 与 `inference_methods`，逐一计算支撑 edge 的证据等级。

Finding 最终采用**所有支撑 edge 中最弱的等级**。这可以避免某一条强证据把包含较弱 edge 的多跳或 delegated finding 整体“洗”成高等级。找不到的支撑 edge 会保守标为 `U`，不会猜测。

## Severity 保持独立

Evidence grade 永远不会改写 `severity`。例如 finding 可以合理地同时是：

```json
{
  "severity": "high",
  "evidence_grade": "B"
}
```

这表示规则判定该行为具有高优先级，但其中的支撑观测包含采样式 process evidence。它不表示“80% 置信度”，也不代表恶意行为已经被证明。

## 保守默认

明确 inference 的优先级高于 causal flag，因此会标为 `D`。明确 non-causal 的证据标为 `C`。未知 attribution vocabulary 即使其他字段看起来很强，也只会标为 `U`。这些规则用于避免未来加入新 backend 时意外夸大安全声明。

报告也会为每个 finding 提供 `evidence_basis`，让分析者检查每条 edge 的 grade、attribution modes、backend labels、inference methods，以及该 grade 的推导理由。

## 不代表的事情

Evidence grade 不是概率、trust score、防篡改保证或正确性证明。它不建立 byte-level data flow、exfiltration、完整 process coverage 或恶意意图。这些声明仍必须遵守底层 event 与 fidelity contract。
