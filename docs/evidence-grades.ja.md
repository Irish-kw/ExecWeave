<!-- i18n-nav:start -->
<p align="center">
  <a href="evidence-grades.md">English</a> |
  <a href="evidence-grades.zh-TW.md">繁體中文</a> |
  <a href="evidence-grades.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="evidence-grades.ko.md">한국어</a> |
  <a href="evidence-grades.fr.md">Français</a> |
  <a href="evidence-grades.de.md">Deutsch</a> |
  <a href="evidence-grades.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Evidence Grade

ExecWeave の Evidence Grade は、実行グラフの provenance が finding をどの程度強く裏付けるかを示します。重大度、悪意、確率、正しさそのものを表すものではありません。

## 目的

Finding の severity と証拠強度は独立した軸です。重大な挙動がサンプリング証拠でしか観測されないこともあれば、低 severity の挙動が強い syscall attribution を持つこともあります。そのため ExecWeave は両者を別々に公開し、収集能力が弱いという理由だけで severity を下げません。

## Contract

| Grade | 意味 | 現在の導出 |
| --- | --- | --- |
| `A` | 直接かつ因果的な native attribution | 認識済み `syscall` attribution を持つ causal graph edge |
| `B` | 直接かつ因果的な sampled process attribution | `polling` または `process_polling` attribution を持つ causal edge |
| `C` | session-correlated または明示的 non-causal evidence | non-causal edge、または `session_observation` attribution |
| `D` | 明示的に inferred / heuristic な evidence | `inferred=true`、または inference method が記録された edge |
| `U` | provenance が不明、または分類情報が不足 | support/attribution の欠落、未知・混在 vocabulary、その他未分類 provenance |

この vocabulary は意図的に保守的です。新しい backend や attribution 文字列は自動的に上位 grade へ昇格せず、contract が明示的に拡張されるまでは `U` のままです。

## Finding の導出

各 finding は `edge_ids` を通じて 1 本以上の graph edge を参照します。ExecWeave は graph に保持された `causal`、`inferred`、`attributions`、`backends`、`inference_methods` などの provenance から各 supporting edge を grade します。

Finding 全体には**supporting edge のうち最も弱い grade**を採用します。これにより、強い 1 本の edge が、より弱い support を含む multi-edge / delegated finding 全体を強い証拠に見せることを防ぎます。supporting edge が見つからない場合は推測せず `U` とします。

## Severity との独立性

Evidence grade は `severity` を書き換えません。例えば次は正当な組み合わせです。

```json
{
  "severity": "high",
  "evidence_grade": "B"
}
```

これは rule 上の優先度は high だが、supporting observation に sampled process evidence が含まれることを意味します。「80% confidence」や悪意の証明を意味しません。

## 保守的な既定値

明示的 inference は causal flag より優先され `D` になります。明示的 non-causal evidence は `C` です。未知の attribution vocabulary は他の field が強く見えても `U` です。これは将来 backend を追加した際の claim inflation を防ぐためです。

Report には finding ごとの `evidence_basis` も含まれ、各 edge の grade、attribution modes、backend labels、inference methods、grade の理由を確認できます。

## 非保証事項

Evidence grade は probability、trust score、tamper-resistance guarantee、correctness proof ではありません。byte-level data flow、exfiltration、complete process coverage、malicious intent も立証しません。これらの claim は underlying event と fidelity contract に従います。
