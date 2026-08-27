# Rule Packs

<!-- i18n-nav:start -->
<p align="center">
  <a href="rule-packs.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="rule-packs.zh-CN.md">简体中文</a> |
  <a href="rule-packs.ja.md">日本語</a> |
  <a href="rule-packs.ko.md">한국어</a> |
  <a href="rule-packs.fr.md">Français</a> |
  <a href="rule-packs.de.md">Deutsch</a> |
  <a href="rule-packs.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave Rule Pack 是有界限的 JSON 原則檔，用來新增本機、可解釋的 observation finding，同時不執行第三方程式碼。Schema `0.1` 刻意只支援單一 edge matching。內建的多 edge correlation rule 仍保留在 ExecWeave 程式碼中，不會被不受信任的 Rule Pack 取代。

## Contract

單一 Rule Pack 上限為 256 KiB、最多 128 條 rule，每個 list matcher 最多 16 個值。未知欄位一律拒絕。Pack 與 rule identifier 都有長度限制，而且只能使用英文字母、數字、`.`、`_`、`-`。

Rule Pack 不能定義 regular expression、自訂 summary、任意 attributes、path/sequence program、code hook 或 data-flow assertion。Finding 文字由 ExecWeave 固定產生，所有 Rule Pack match 都會標記為 observation-only，並強制 `data_flow_proven=false` 與 `exfiltration_proven=false`。

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

每條 rule 都必須包含 `id`、`severity` 與非空的 `match` object。Severity 只能是 `high`、`medium`、`low` 或 `info`。Severity 不會改變 Evidence Grade；Evidence Grade 仍由實際命中的 canonical graph edge provenance 推導。

## Match semantics

| Matcher | 意義 |
| --- | --- |
| `relations` | 精確比對 edge relation；列出的任一值可命中。 |
| `source_types` | 精確比對 source node type。 |
| `target_types` | 精確比對 target node type。 |
| `source_id_contains` | 對 source node ID 做不分大小寫的 substring match。 |
| `target_id_contains` | 對 target node ID 做不分大小寫的 substring match。 |
| `source_name_contains` | 對 source node name 做不分大小寫的 substring match。 |
| `target_name_contains` | 對 target node name 做不分大小寫的 substring match。 |
| `backends` | 必須與 edge 的 backend set 有交集。 |
| `attributions` | 必須與 edge 的 attribution set 有交集。 |
| `causal` | 精確比對 edge 的 `causal` 布林值。 |

不同 matcher 欄位之間採 AND；同一 list 內多個值視為 OR 選項。任何 matcher 都不會執行 regex。

## CLI

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json
execweave-rule-pack graph.json --rule-pack base.json --rule-pack team.json --output report.json
```

同一次執行載入多個 pack 時，pack ID 必須唯一。輸出會在一般 security-analysis report 上加入 `analysis_schema_version: 0.4`、`rule_pack_schema_version`，以及已載入 pack ID 與 rule count。既有 `execweave analyze` 行為完全不變。

## Security boundary

Rule Pack 是資料，不是 plugin。載入 Rule Pack 不會 import module、執行 command、evaluate expression 或執行 regex。Rule Pack 可以替某個已觀測 edge pattern 指定 severity，但不能自行產生「資源之間已有 bytes 傳輸」或「exfiltration 已發生」這類更強的結論；這些主張必須依賴第一版 Rule Pack contract 之外的證據與邏輯。
