# Rule Packs

<!-- i18n-nav:start -->
<p align="center">
  <a href="rule-packs.md">English</a> |
  <a href="rule-packs.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="rule-packs.ja.md">日本語</a> |
  <a href="rule-packs.ko.md">한국어</a> |
  <a href="rule-packs.fr.md">Français</a> |
  <a href="rule-packs.de.md">Deutsch</a> |
  <a href="rule-packs.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave Rule Pack 是有边界的 JSON 策略文件，用于新增本地、可解释的 observation finding，同时不执行第三方代码。Schema `0.1` 刻意只支持单一 edge matching。内建的多 edge correlation rule 仍保留在 ExecWeave 代码中，不会被不受信任的 Rule Pack 替代。

## Contract

单个 Rule Pack 上限为 256 KiB、最多 128 条 rule，每个 list matcher 最多 16 个值。未知字段一律拒绝。Pack 与 rule identifier 都有长度限制，并且只能使用英文字母、数字、`.`、`_`、`-`。

Rule Pack 不能定义 regular expression、自定义 summary、任意 attributes、path/sequence program、code hook 或 data-flow assertion。Finding 文本由 ExecWeave 固定生成，所有 Rule Pack match 都会标记为 observation-only，并强制 `data_flow_proven=false` 与 `exfiltration_proven=false`。

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

每条 rule 都必须包含 `id`、`severity` 和非空 `match` object。Severity 只能是 `high`、`medium`、`low` 或 `info`。Severity 不会改变 Evidence Grade；Evidence Grade 仍由实际命中的 canonical graph edge provenance 推导。

## Match semantics

| Matcher | 含义 |
| --- | --- |
| `relations` | 精确匹配 edge relation；列出的任一值可命中。 |
| `source_types` | 精确匹配 source node type。 |
| `target_types` | 精确匹配 target node type。 |
| `source_id_contains` | 对 source node ID 做不区分大小写的 substring match。 |
| `target_id_contains` | 对 target node ID 做不区分大小写的 substring match。 |
| `source_name_contains` | 对 source node name 做不区分大小写的 substring match。 |
| `target_name_contains` | 对 target node name 做不区分大小写的 substring match。 |
| `backends` | 必须与 edge 的 backend set 有交集。 |
| `attributions` | 必须与 edge 的 attribution set 有交集。 |
| `causal` | 精确匹配 edge 的 `causal` 布尔值。 |

不同 matcher 字段之间采用 AND；同一 list 内多个值视为 OR 选项。任何 matcher 都不会执行 regex。

## CLI

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json
execweave-rule-pack graph.json --rule-pack base.json --rule-pack team.json --output report.json
```

同一次执行加载多个 pack 时，pack ID 必须唯一。输出会在普通 security-analysis report 上加入 `analysis_schema_version: 0.4`、`rule_pack_schema_version`，以及已加载 pack ID 和 rule count。现有 `execweave analyze` 行为保持不变。

## Security boundary

Rule Pack 是数据，不是 plugin。加载 Rule Pack 不会 import module、执行 command、evaluate expression 或运行 regex。Rule Pack 可以给某个已观测 edge pattern 指定 severity，但不能自行生成“资源之间已经有 bytes 传输”或“exfiltration 已发生”这类更强结论；这些主张必须依赖第一版 Rule Pack contract 之外的证据和逻辑。
