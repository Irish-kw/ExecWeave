# Rule Packs

<!-- i18n-nav:start -->
<p align="center">
  <a href="rule-packs.md">English</a> |
  <a href="rule-packs.zh-TW.md">繁體中文</a> |
  <a href="rule-packs.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="rule-packs.ko.md">한국어</a> |
  <a href="rule-packs.fr.md">Français</a> |
  <a href="rule-packs.de.md">Deutsch</a> |
  <a href="rule-packs.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave Rule Pack は、第三者コードを実行せずにローカルで説明可能な observation finding を追加するための、境界を持つ JSON ポリシーです。Schema `0.1` は意図的に単一 edge matching のみをサポートします。組み込みの multi-edge correlation rule は引き続き ExecWeave コード内に残り、信頼されていない Rule Pack に置き換えられません。

## Contract

1 つの Rule Pack は最大 256 KiB、最大 128 rules、各 list matcher は最大 16 values に制限されます。未知の field は拒否されます。Pack と rule の identifier は長さ制限があり、英字、数字、`.`、`_`、`-` のみ使用できます。

Rule Pack は regular expression、custom summary、任意 attributes、path/sequence program、code hook、data-flow assertion を定義できません。Finding の文章は ExecWeave が固定生成し、すべての Rule Pack match は observation-only として扱われ、`data_flow_proven=false` と `exfiltration_proven=false` が強制されます。

## Schema

```json
{
  "rule_pack_schema_version": "0.1",
  "id": "local-policy",
  "rules": [
    {
      "id": "pem-read",
      "severity": "medium",
      "match": {
        "relations": ["OPENED_READ"],
        "source_types": ["process"],
        "target_types": ["file"],
        "target_name_contains": [".pem"],
        "backends": ["strace"],
        "causal": true
      }
    }
  ]
}
```

各 rule には `id`、`severity`、空でない `match` object が必要です。Severity は `high`、`medium`、`low`、`info` のいずれかです。Severity は Evidence Grade を変更せず、Evidence Grade は一致した canonical graph edge の provenance から引き続き導出されます。

## Match semantics

| Matcher | 意味 |
| --- | --- |
| `relations` | edge relation の完全一致。列挙値のいずれかが一致すればよい。 |
| `source_types` | source node type の完全一致。 |
| `target_types` | target node type の完全一致。 |
| `source_id_contains` | source node ID に対する大文字小文字を無視した substring match。 |
| `target_id_contains` | target node ID に対する大文字小文字を無視した substring match。 |
| `source_name_contains` | source node name に対する大文字小文字を無視した substring match。 |
| `target_name_contains` | target node name に対する大文字小文字を無視した substring match。 |
| `backends` | edge backend set との共通要素が必要。 |
| `attributions` | edge attribution set との共通要素が必要。 |
| `causal` | edge の `causal` boolean を完全一致。 |

異なる matcher field は AND で結合され、同じ list 内の複数 value は OR 候補です。どの matcher も regex を評価しません。

## CLI

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json
execweave-rule-pack graph.json --rule-pack base.json --rule-pack team.json --output report.json
```

同じ invocation で複数 pack を読み込む場合、pack ID は一意でなければなりません。出力は通常の security-analysis report に `analysis_schema_version: 0.4`、`rule_pack_schema_version`、読み込まれた pack ID と rule count を追加します。既存の `execweave analyze` の動作は変更されません。

## Security boundary

Rule Pack は data であり plugin ではありません。Pack の読み込みでは module import、command execution、expression evaluation、regex execution は行われません。Pack は観測された edge pattern に severity を割り当てられますが、resource 間で bytes が移動した、または exfiltration が発生したという強い主張は生成できません。そのような主張には、この最初の Rule Pack contract 以外の証拠とロジックが必要です。
