# Rule Packs

<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="rule-packs.zh-TW.md">繁體中文</a> |
  <a href="rule-packs.zh-CN.md">简体中文</a> |
  <a href="rule-packs.ja.md">日本語</a> |
  <a href="rule-packs.ko.md">한국어</a> |
  <a href="rule-packs.fr.md">Français</a> |
  <a href="rule-packs.de.md">Deutsch</a> |
  <a href="rule-packs.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave rule packs are bounded JSON policies for adding local, explainable observation findings without executing third-party code. Schema `0.1` intentionally supports only single-edge matching. Built-in multi-edge correlation rules remain in ExecWeave code and are not replaced by untrusted rule packs.

## Contract

A rule pack is limited to 256 KiB, at most 128 rules, and at most 16 values per list matcher. Unknown fields are rejected. Rule and pack identifiers are bounded and may contain only letters, digits, `.`, `_`, and `-`.

Rule packs cannot define regular expressions, custom summaries, arbitrary attributes, path/sequence programs, code hooks, or data-flow assertions. ExecWeave generates the finding text and always marks rule-pack matches as observation-only with `data_flow_proven=false` and `exfiltration_proven=false`.

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

Each rule requires `id`, `severity`, and a non-empty `match` object. Severity is one of `high`, `medium`, `low`, or `info`. Severity does not change the evidence grade: evidence grade is still derived from the matched canonical graph edge.

## Match semantics

| Matcher | Meaning |
| --- | --- |
| `relations` | Exact edge relation; any listed value may match. |
| `source_types` | Exact source-node type. |
| `target_types` | Exact target-node type. |
| `source_id_contains` | Case-insensitive substring match on source node ID. |
| `target_id_contains` | Case-insensitive substring match on target node ID. |
| `source_name_contains` | Case-insensitive substring match on source node name. |
| `target_name_contains` | Case-insensitive substring match on target node name. |
| `backends` | Requires intersection with the edge backend set. |
| `attributions` | Requires intersection with the edge attribution set. |
| `causal` | Exact boolean match on the edge `causal` value. |

Different matcher fields are combined with AND. Multiple values inside one list are OR alternatives. No matcher performs regex evaluation.

## CLI

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json
execweave-rule-pack graph.json --rule-pack base.json --rule-pack team.json --output report.json
```

Multiple packs in one invocation must have unique pack IDs. The output extends the normal security-analysis report with `analysis_schema_version: 0.4`, `rule_pack_schema_version`, and a list of loaded pack IDs and rule counts. Existing `execweave analyze` behavior is unchanged.

## Security boundary

Rule packs are data, not plugins. Loading a pack does not import modules, execute commands, evaluate expressions, or run regex. A pack can assign severity to an observed edge pattern, but it cannot create a claim that bytes moved between resources or that exfiltration occurred. Those stronger claims require evidence and logic outside this first rule-pack contract.
