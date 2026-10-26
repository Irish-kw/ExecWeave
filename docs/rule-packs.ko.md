# Rule Packs

<!-- i18n-nav:start -->
<p align="center">
  <a href="rule-packs.md">English</a> |
  <a href="rule-packs.zh-TW.md">繁體中文</a> |
  <a href="rule-packs.zh-CN.md">简体中文</a> |
  <a href="rule-packs.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="rule-packs.fr.md">Français</a> |
  <a href="rule-packs.de.md">Deutsch</a> |
  <a href="rule-packs.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave Rule Pack은 제3자 코드를 실행하지 않고 로컬의 설명 가능한 observation finding을 추가하기 위한 제한된 JSON 정책입니다. Schema `0.1`은 의도적으로 단일 edge matching만 지원합니다. 내장 multi-edge correlation rule은 계속 ExecWeave 코드에 남으며 신뢰되지 않은 Rule Pack으로 대체되지 않습니다.

## Contract

Rule Pack 하나는 최대 256 KiB, 최대 128 rules, 각 list matcher는 최대 16 values로 제한됩니다. 알 수 없는 field는 거부됩니다. Pack과 rule identifier에는 길이 제한이 있으며 영문자, 숫자, `.`, `_`, `-`만 사용할 수 있습니다.

Rule Pack은 regular expression, custom summary, 임의 attributes, path/sequence program, code hook, data-flow assertion을 정의할 수 없습니다. Finding 문구는 ExecWeave가 고정 생성하며 모든 Rule Pack match는 observation-only로 표시되고 `data_flow_proven=false`, `exfiltration_proven=false`가 강제됩니다.

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

각 rule에는 `id`, `severity`, 비어 있지 않은 `match` object가 필요합니다. Severity는 `high`, `medium`, `low`, `info` 중 하나입니다. Severity는 Evidence Grade를 변경하지 않으며, Evidence Grade는 실제로 일치한 canonical graph edge의 provenance에서 계속 계산됩니다.

## Match semantics

| Matcher | 의미 |
| --- | --- |
| `relations` | edge relation의 정확한 일치. 나열된 값 중 하나가 일치하면 됩니다. |
| `source_types` | source node type의 정확한 일치. |
| `target_types` | target node type의 정확한 일치. |
| `source_id_contains` | source node ID에 대한 대소문자 무시 substring match. |
| `target_id_contains` | target node ID에 대한 대소문자 무시 substring match. |
| `source_name_contains` | source node name에 대한 대소문자 무시 substring match. |
| `target_name_contains` | target node name에 대한 대소문자 무시 substring match. |
| `backends` | edge backend set과 교집합이 있어야 합니다. |
| `attributions` | edge attribution set과 교집합이 있어야 합니다. |
| `causal` | edge의 `causal` boolean을 정확히 일치시킵니다. |

서로 다른 matcher field는 AND로 결합되고, 하나의 list 안의 여러 value는 OR 대안입니다. 어떤 matcher도 regex를 평가하지 않습니다.

## CLI

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json
execweave-rule-pack graph.json --rule-pack base.json --rule-pack team.json --output report.json
```

한 번의 invocation에서 여러 pack을 로드하면 pack ID는 고유해야 합니다. 출력은 일반 security-analysis report에 `analysis_schema_version: 0.4`, `rule_pack_schema_version`, 로드된 pack ID와 rule count를 추가합니다. 기존 `execweave analyze` 동작은 변경되지 않습니다.

## Security boundary

Rule Pack은 data이지 plugin이 아닙니다. Pack을 로드할 때 module import, command 실행, expression 평가, regex 실행을 하지 않습니다. Pack은 관측된 edge pattern에 severity를 지정할 수 있지만 resource 사이에 bytes가 이동했다거나 exfiltration이 발생했다는 더 강한 주장을 만들 수 없습니다. 그런 주장은 첫 번째 Rule Pack contract 밖의 증거와 로직이 필요합니다.
