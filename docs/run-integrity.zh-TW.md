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

manifest 固定記錄 `malicious_writer_resistance: false` 與 `external_trust_anchor: false`。這些不是可省略的文件措辭，而是 schema contract 的一部分。

## Trust boundary

local digest 適合偵測 accidental corruption、不完整複製，或相對於 seal 時刻發生的 post-seal changes。但它無法阻止同時能改寫 run evidence 與 `integrity.json` 的 process；該 process 可以重新計算 hashes，建立一份新的、內部仍一致的 manifest。

若需要更強保證，請把 `manifest_body_sha256` 或完整 manifest 複製到 observed process 無法寫入的位置，或使用該 process 無法取得的 key 進行保護／簽章。真正的 trust anchor 來自這個外部動作；ExecWeave 不宣稱同目錄 manifest 本身能建立 trust anchor。

## 操作規則

只對已完成的 run 執行 seal。在依賴 archived 或 transferred evidence 前先 verify。任何 verification error 都代表目錄已不再精確符合 sealed inventory，不代表已證明存在惡意行為。若 seal 後仍需產生新 artifact，應先完成那些 artifact，再對新的 finalized copy 執行 seal，而不是靜默重寫原 manifest。
