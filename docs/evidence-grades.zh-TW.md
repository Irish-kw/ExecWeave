<!-- i18n-nav:start -->
<p align="center">
  <a href="evidence-grades.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="evidence-grades.zh-CN.md">简体中文</a> |
  <a href="evidence-grades.ja.md">日本語</a> |
  <a href="evidence-grades.ko.md">한국어</a> |
  <a href="evidence-grades.fr.md">Français</a> |
  <a href="evidence-grades.de.md">Deutsch</a> |
  <a href="evidence-grades.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# 證據等級

ExecWeave 的證據等級描述執行圖中的 provenance 能以多強的程度支撐一個 finding。它不描述行為有多嚴重、多惡意、機率多高，也不代表 finding 一定正確。

## 目的

Finding 的 severity 與證據強度是彼此獨立的維度。高嚴重度行為可能只由抽樣式證據觀測到，而低嚴重度行為也可能具有很強的 syscall attribution。因此 ExecWeave 會同時呈現兩者，而不會因蒐集能力較弱就偷偷降低 severity。

## 合約

| 等級 | 意義 | 目前推導方式 |
| --- | --- | --- |
| `A` | 直接、具因果性的原生歸因 | 具因果性的 graph edge，且具有已認可的 `syscall` attribution |
| `B` | 直接、具因果性的抽樣程序歸因 | 具因果性的 edge，且 attribution 為 `polling` 或 `process_polling` |
| `C` | session 關聯或明確非因果證據 | edge 明確為 non-causal，或具有 `session_observation` attribution |
| `D` | 明確由推論或 heuristic 產生的證據 | edge 具有 `inferred=true` 或記錄 inference method |
| `U` | provenance 未知或分類資訊不足 | 缺少支撐、缺少 attribution、混合／未知 attribution vocabulary，或尚未被合約分類 |

這套 vocabulary 刻意採保守策略。新的 backend 或 attribution 字串不會自動被提升成較強等級；在合約明確擴充前，一律維持 `U`。

## Finding 推導方式

每個 finding 原本就會透過 `edge_ids` 指向一個或多個 graph edge。ExecWeave 會使用 graph 中保留的 provenance 欄位，例如 `causal`、`inferred`、`attributions`、`backends` 與 `inference_methods`，逐一計算支撐 edge 的證據等級。

Finding 最終採用**所有支撐 edge 中最弱的等級**。這可以避免某一條強證據把包含較弱 edge 的多跳或 delegated finding 整體「洗」成高等級。找不到的支撐 edge 會保守標為 `U`，不會猜測。

## Severity 保持獨立

Evidence grade 永遠不會改寫 `severity`。例如 finding 可以合理地同時是：

```json
{
  "severity": "high",
  "evidence_grade": "B"
}
```

這代表規則判定該行為具有高優先級，但其中的支撐觀測包含抽樣式 process evidence。它不代表「80% 信心」，也不代表惡意行為已被證明。

## 保守預設

明確 inference 的優先級高於 causal flag，因此會標為 `D`。明確 non-causal 的證據標為 `C`。未知 attribution vocabulary 即使其他欄位看起來很強，也只會標成 `U`。這些規則是為了避免未來加入新 backend 時意外膨脹安全聲明。

報告也會為每個 finding 提供 `evidence_basis`，讓分析者檢查每條 edge 的 grade、attribution modes、backend labels、inference methods，以及該 grade 的推導理由。

## 不代表的事情

Evidence grade 不是機率、trust score、防竄改保證或正確性證明。它不建立 byte-level data flow、exfiltration、完整 process coverage 或惡意意圖。這些聲明仍必須遵守底層 event 與 fidelity contract。
