# 正文來源導覽與封存引用驗證

基準：`a9a4333102065b559dd1197fbbad7787c691b94c`，PR #110。
範圍：W02／W04 的內容入口，以及 W08 的終止匯出驗證；不是整版功能完成。

## 正文入口

我把既有閱讀元件接到目前選取節點的明確內容來源。agent 面板可以讀取直接關聯的正文，以及有明確指派或呼叫邊的 task、tool call、model call 內容，不再只依賴原本工具／模型摘要卡片剛好露出的引用。

- 原始節點 ID 與明確的 projection member IDs 是查找依據；同名 agent、共用模型、父子關係或相近時間都不是合併依據。
- 不從模型資源反查所有呼叫者，不把其他角色的內容借到目前角色。
- 不同 call 使用相同正文 hash，仍保留不同來源項目。列出的數字是來源引用／觀測數，不冒充 delivery、consumption 或成功任務數。
- 一次顯示 25 筆，可逐批展開；切換角色後保留各自的展開數。原有對話卡片及 fold policy 不改動。
- 內容仍由上一批的相同閱讀元件處理，包含認證、hash、大小、純文字顯示與離線資料夾選取。
- 這不是完整對話時間線，也沒有補造缺少的 provider evidence。未存在於目前圖資料中的來源，仍需要後續資料正規化。

## 封存引用驗證

原先的必要輸出檢查只能證明三個主要檔案存在。現在終止匯出另外檢查 `graph.json` 中的 `observed_content`（包含 expansion cluster 裡的內容節點），以及 `conversations.json` 的內容引用。

- 逐一驗證合法的 `content/sha256/<hash>.<json|txt|bin>`、實際檔案、完整 bytes hash 與已記錄的大小。
- 重複引用只讀取一次；相同路徑的大小宣告衝突會失敗，不能被後續有效引用沖掉。
- 不解析 provider 正文來找其他檔案，不掃描任意 workspace。二進位與空內容也能驗證保存完整性，是否能預覽是另一個問題。
- JSON 格式錯誤、重複 key、已知 session 不一致、缺檔、符號連結／reparse point、非一般檔案、讀取中變更與驗證上限都有明確診斷。
- POSIX 使用 directory descriptors 與 `O_NOFOLLOW`。Windows 採讀取前後 reparse-point 與檔案身份檢查；此機制不是對抗同一可寫信任邊界內攻擊者的可信日誌。
- 預設上限為每個索引 64 MiB、內容讀取預算 1 GiB、100,000 筆引用；碰到限制會標為 incomplete，不能跳過後仍宣稱完整。錯誤細節最多保留 100 筆，總錯誤數與截斷狀態另外保留。
- 部分來源內容的 bytes 可能完整保存；這項驗證不等於 provider 可見性或 end-to-end recall。

`finalization.json` 使用 schema 0.2，保留既有欄位，新增 `artifact_errors` 與 `content_integrity`。錄製中是 `not_checked`；終止時未通過引用驗證不能標為 complete。診斷先寫入 manifest，再回報匯出失敗；已有 collector 原始錯誤時，不以新的內容診斷取代它。

驗證範圍是這兩份索引宣告的內容，不包含所有原始事件完整性的證明、viewer 內嵌資料語義比對或不可竄改承諾。尚未呼叫 `record_finalization` 的其他輸出路徑，沒有因此自動取得這項驗證。既有封存不會被背景改寫。

## 測試與回歸

本地執行：

```text
內容完整性與 finalization：61 項通過
正文來源元件：12 項通過（含 11 項 Chromium 操作測試）
合計：73 passed；1 項 full-shell integration test 未在本地執行
Python compilation：PASS
組合後 JavaScript syntax：PASS
```

內容完整性測試使用實際暫存檔案；來源元件測試執行實際 JavaScript 與既有閱讀元件，驗證選取、隔離、分批展開及錯誤入口。它們使用合成圖，不是真實 provider 錄製；沒有以 HTTP／SHA-256 替身把原生傳輸驗證算成通過。

本地 Chromium 的 loopback 導航被環境政策阻擋。新測試尚不能在本地證明原生 HTTP／auth；完整 Dashboard 組裝、既有全套測試、三 OS 及安裝套件由此提交的 PR 工作流驗證。真實 provider 重錄及獨立使用者操作驗收仍待執行。

原有 finalization 回歸中，成功案例使用的 `artifact` 純文字 placeholder 改為有效 graph／conversation JSON。原有斷言保留；新增多種無效 JSON 負向案例，不能用任意非空檔案通過新的引用驗證。

## 整合與回退

內容導覽只新增一個共用元件與閱讀元件的明確 `attach` 接口，沒有改 owner 推論、原始事件、圖布局或 recorder。

封存驗證集中在 `content_integrity.py` 與 `finalization.py`，不改寫來源檔案，也不提升套件版號。若回歸需要回退，可分開回退正文導覽與終止驗證；不能僅刪掉失敗測試或放寬不完整封存的判定。
