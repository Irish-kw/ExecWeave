<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="evidence-grades.zh-TW.md">繁體中文</a> |
  <a href="evidence-grades.zh-CN.md">简体中文</a> |
  <a href="evidence-grades.ja.md">日本語</a> |
  <a href="evidence-grades.ko.md">한국어</a> |
  <a href="evidence-grades.fr.md">Français</a> |
  <a href="evidence-grades.de.md">Deutsch</a> |
  <a href="evidence-grades.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Evidence Grades

ExecWeave evidence grades describe how strongly the graph provenance supports a finding. They do not describe how severe, malicious, probable, or correct the behavior is.

## Purpose

Finding severity and evidence strength are independent dimensions. A high-severity behavior can be observed through sampled evidence, while a low-severity behavior can have strong syscall attribution. ExecWeave therefore exposes both values instead of silently lowering severity when capture is weaker.

## Contract

| Grade | Meaning | Current derivation |
| --- | --- | --- |
| `A` | Direct, causal native attribution | Causal graph edge with recognized `syscall` attribution |
| `B` | Direct, causal sampled process attribution | Causal edge with `polling` or `process_polling` attribution |
| `C` | Session-correlated or explicitly non-causal evidence | Non-causal edge or recognized `session_observation` attribution |
| `D` | Explicitly inferred or heuristic evidence | Edge has `inferred=true` or records an inference method |
| `U` | Unknown or insufficiently classified provenance | Missing support, missing attribution, mixed/unknown attribution vocabulary, or otherwise unclassified provenance |

The vocabulary is deliberately conservative. A new backend or attribution string is **not** automatically promoted to a stronger grade; it remains `U` until the contract is explicitly extended.

## Finding derivation

Each finding already references one or more graph edges through `edge_ids`. ExecWeave grades each supporting edge from the provenance fields retained in the graph, including `causal`, `inferred`, `attributions`, `backends`, and `inference_methods`.

The finding receives the **weakest supporting edge grade**. This prevents one strong edge from laundering a multi-edge or delegated finding whose other support is weaker. Missing supporting edges are graded `U` rather than guessed.

## Severity is independent

Evidence grade never rewrites `severity`. For example, a finding can legitimately be:

```json
{
  "severity": "high",
  "evidence_grade": "B"
}
```

This means the behavior is high priority under the rule, while the supporting observation includes sampled process evidence. It does not mean “80% confidence,” and it does not imply malicious intent.

## Conservative defaults

Explicit inference takes precedence over a causal flag and is graded `D`. Explicitly non-causal evidence is graded `C`. Unknown attribution vocabulary is graded `U`, even if another field looks strong. These rules are intended to prevent accidental claim inflation during future backend integrations.

The report also includes `evidence_basis` for each finding so analysts can inspect the per-edge grade, attribution modes, backend labels, inference methods, and the reason for the grade.

## Non-claims

Evidence grades are not probabilities, trust scores, tamper-resistance guarantees, or correctness proofs. They do not establish byte-level data flow, exfiltration, complete process coverage, or malicious intent. Those claims remain governed by the underlying event and fidelity contracts.
