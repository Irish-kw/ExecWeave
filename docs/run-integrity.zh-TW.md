# Run Integrity（執行完整性）

<!-- i18n-nav:start -->
<p align="center">
  <a href="run-integrity.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="run-integrity.zh-CN.md">简体中文</a> |
  <a href="run-integrity.ja.md">日本語</a> |
  <a href="run-integrity.ko.md">한국어</a> |
  <a href="run-integrity.fr.md">Français</a> |
  <a href="run-integrity.de.md">Deutsch</a> |
  <a href="run-integrity.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave v0.6.5 可以把已完成的 run 封存成 deterministic SHA-256 inventory，並在之後重新驗證。此功能用於偵測本機封存後的損毀與修改。當 manifest 與 evidence 仍位於相同、可寫入的 trust boundary 時，我們刻意不把它描述成可抵抗攻擊者的 tamper evidence。

## 範圍

`execweave-integrity seal` 會遞迴盤點指定 run directory 下的每個 regular file，但排除 `integrity.json` 本身。項目依 relative POSIX path 決定性排序，記錄 path、byte size 與 SHA-256 digest。Symbolic link 會被拒絕，不會被跟隨，也不會靜默正規化。

seal 應只在 capture 與所有需要的 derived artifacts 都完成後執行。seal 之後新增的檔案會被回報為 unsealed；任何 sealed file 若被修改、替換或刪除，驗證都會失敗。

## Seal 與 verify

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

`seal` 不會覆寫已存在的 integrity contract。`verify` 只有在 manifest schema 合法、manifest body digest 相符、每個 sealed file 的 size 與 SHA-256 都符合，而且 seal 後沒有額外 regular file 出現時才回傳成功。

## Manifest contract

| 欄位 | 意義 |
| --- | --- |
| `schema_version` | Integrity schema 版本；v0.6.5 從 `0.1` 開始。 |
| `files` | 依決定性順序保存的 sealed file inventory。 |
| `manifest_body_sha256` | 排除本 digest 欄位後，canonical manifest content 的 SHA-256。 |
| `trust_model` | 明確陳述此 local seal 能證明與不能證明的內容。 |


## 僅限本機的一致性與信任界限

<!-- ew:trust:local-only -->

本機 `seal` / `verify` 可偵測意外損壞，以及沒有重新封存的事後修改。**如果寫入者能改寫執行證據及 `integrity.json`，就能重新計算雜湊並重新 seal。** `valid: true` 只表示本機一致性，不等於具防竄改保證的稽核。

<!-- ew:trust:privileged -->

具有 root、sudo 權限的 Agent，或任何可寫入輸出目錄的程序，都可能同時改寫事件與 manifest。應使用作業系統權限與程序隔離保護資料；只換路徑但保留同樣寫入權限並不構成隔離。

<!-- ew:compat:no-downgrade -->

**不支援使用 v0.8.34 reader 降級讀取 v0.8.35 以上的紀錄。** 舊版可能無警告地捨棄 `observation_assessment`，並錯誤呈現觀測完整性。只有 v0.8.35 以上的 reader 結論才可信。回滾 recorder 不代表可回滾 reader。

只對完成的 run 執行 seal，使用封存證據前先 verify。驗證失敗只代表本機資料不一致，並非直接證明惡意操作。本工具不會自動上傳執行資料或摘要，也不提供獨立的權限邊界。
