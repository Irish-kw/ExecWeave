# ExecWeave 0.7.5 → 0.8.0 實作規劃書

> 本文件是交給實作者（Codex）逐階段執行的規格。
> 每個階段開一個獨立 branch、開一個獨立 PR、**不自行 merge**，最後統一送審。
> 基準 commit：`main` @ `80e23d5`（v0.7.4）。

---

## 0. 這一輪要解決的問題

使用者在 conversation 裡看到：

```
Provider-encrypted payload — plaintext is not exposed by the observed provider surface.
```

目標是把**實際拿得到**的 input / thinking / output / tool token 全部收進來，並且把**拿不到的部分誠實標記**，而不是用猜測填滿。

### 加密分三層，決定了什麼做得到

| 層 | 定義 | 本輪立場 |
|---|---|---|
| **L1 傳輸層 TLS** | client ↔ provider 之間的 HTTPS | **不碰**。不做 MITM，不做 eBPF |
| **L2 應用層封裝** | client 自己在 JSON 欄位再加密（Fernet `gAAAAA`） | 金鑰在本地才處理 |
| **L3 服務端加密** | provider 回傳即為密文，金鑰只在 provider | **放棄**，標記為不可得 |

**本輪只走 provider 官方表面與使用者自有端點。** 破 L1 的手段（TLS MITM、eBPF uprobe）一律不做，理由見 §2。

---

## 1. 不可違反的架構紅線

以下是現有版本的既定設計，**任何階段都不得改變**：

### 1.1 不做 TLS MITM

`src/execweave/http_proxy.py:321-322` 是刻意的設計決定：

```python
def do_CONNECT(self) -> None:
    self.send_error(405, "CONNECT is disabled; ExecWeave does not perform TLS MITM")
```

- 這行**必須保留原樣**。
- `tests/test_http_proxy.py:252`（`assert response.status == 405`）**必須永遠綠**。
- 0.7.9 階段要為它補上更明確的不變式測試，但**只能加強、不能放寬**。

### 1.2 證據與推論分離

ExecWeave 的信譽建立在「從不宣稱超過底層證據所支持的內容」。既有詞彙定義在 `src/execweave/agent_topology.py`：

- 路徑來源：`provider_declared` / `execweave_derived` / `legacy_unknown`
- 對話完整度：`provider_transcript` / `routing_only` / `unavailable`
- 拓樸證據：`EVIDENCE_*` 常數（`:123-130`）

**只能擴充，不能重寫、不能改名、不能改語意。**

### 1.3 provider 中立

不得為了讓某一家好看而在共用層寫特例。provider 專屬邏輯留在該 provider 的模組內。

---

## 2. 政策紅線：不得違反 provider 政策

### 2.1 正當 vs 不正當的界線

**核心區分：使用者主動重新設定自己的 client，不等於攔截。**

| 做法 | 判定 | 理由 |
|---|---|---|
| 讀 provider 官方 hook / rollout / 本地 transcript | ✅ 正當 | provider 主動提供的介面 |
| 使用者自己把 `base_url` 指向自己的 gateway | ✅ 正當 | 每家 provider 都支援的標準設定 |
| 擷取本地 runtime（Ollama 等）的 HTTP 流量 | ✅ 正當 | 沒有第三方服務、沒有加密 |
| 偽造 CA 憑證做 TLS MITM | ❌ 禁止 | 多數 provider ToS 禁止攔截或逆向其服務通訊 |
| eBPF uprobe 掛 `SSL_write` / `SSL_read` | ❌ 禁止 | 使用者明確排除；且需 root、Linux only |
| 逆向 provider 的加密封裝 | ❌ 禁止 | 同上 |

### 2.2 拿不到就放棄

**這是明確指示：拿不到的就算了，不要用技術手段硬取。**

具體而言，**Codex 的 `reasoning.encrypted_content` 屬於 L3，本輪放棄取得明文**，改為在 0.7.9 用可驗證的方式標記為不可得，並記錄「為什麼拿不到」。

---

## 3. 絕對禁止事項（防作弊）

以下任何一項出現在 PR 中，該 PR 直接退回，不進行後續審查。

### 3.1 測試相關

1. **不得刪除或修改既有測試來讓自己通過。**
   - 基準：`pytest -q --collect-only` = **757 collected**。
   - 每個階段結束後，收集數只能**增加**。
   - 若某個既有測試因為新功能而必須調整，**必須在 PR 說明中單獨列出、說明為什麼原本的斷言不再正確**，並附上該測試在 `main` 上通過、在新分支上為何不再適用的推理。不得默默改掉。

2. **不得使用 `pytest.mark.skip` / `xfail` / `pytest.skip()` 繞過失敗。**
   - 現有 6 個 skip 是環境相依（如 `node` 不存在），新增 skip 必須是同性質的環境相依，且要在 PR 說明。

3. **不得放寬既有 checker 的門檻。**
   - `scripts/check_conversation_records.py` 的重複偵測預設 FAIL，**不得改成 warning**。
   - **不得用 `--allow-duplicate-agent` 之類的逃生門掩蓋真實缺陷。** 該旗標只為「一個 agent 真的跑了多段獨立對話」的 fixture 而存在。
   - `scripts/audit_i18n_parity.py` 的 `0.62` 比例門檻不得調低。

4. **不得在測試中寫死期望值來製造通過。**
   - 測試必須驗證行為，不是驗證「我剛剛寫進去的字串」。
   - 新功能的測試**必須在未套用修改的程式碼上失敗**。PR 說明要寫出「這些測試在 main 上會怎麼失敗」。

### 3.2 證據誠信相關

5. **不得捏造證據。**
   - 沒有 provider 明確給出的東西，不得標記為 `provider_transcript`、`provider_declared`、`observed`。
   - 不確定的一律走 `unavailable` / `execweave_derived` / `unresolved`。
   - **寧可少報，不可多報。**

6. **不得用推測填補缺口。** 拿不到 thinking 就標記拿不到，不得用 output 反推、不得用其他 agent 的內容代替。

7. **不得偽造 fixture。** 新增的測試 fixture 若宣稱來自真實 provider 輸出，就必須真的是（可經過去識別化處理，但結構欄位必須保留原樣）。去識別化範圍：使用者名稱、本機絕對路徑、無關檔名、金鑰、私人內容。

### 3.3 技術手段相關

8. **不得啟用 TLS MITM。** 不得修改 `do_CONNECT`、不得加入憑證產生、不得修改系統 trust store。

9. **不得使用 eBPF / uprobe / kprobe / 核心模組 / `LD_PRELOAD` / `ptrace` 注入 / 記憶體讀取。**

10. **不得關閉 TLS 驗證，不得 unset `HTTPS_PROXY`。**

11. **不得引入需要 root / `CAP_BPF` / 管理員權限的功能。**

### 3.4 流程相關

12. **不得自行 bump 版本、打 tag、建 release。** 版本元資料由審查後統一處理（見 §7）。

13. **不得 merge 自己的 PR，不得 push 到 `main`，不得 force push，不得改寫既有歷史。**

14. **不得跨階段混合。** 一個 branch 只做該階段的事。發現其他問題就記錄下來，不要順手改。

15. **不得把新文件加入 `scripts/audit_i18n_parity.py` 的 `DOCS` 清單**，除非同時提供 7 種語言翻譯（`zh-TW` `zh-CN` `ja` `ko` `fr` `de` `ru`）。新增規劃/內部文件放在不受該清單管轄的路徑。

16. **不得修改 8 個 README 的版本錨點。** README 由版本發布流程統一處理。

---

## 4. 每個階段的共通交付規則

每個 branch 都必須滿足：

- [ ] 從**最新的 `main`** 開分支（`git fetch origin main && git checkout -b <branch> origin/main`）
- [ ] `ruff check .` 全綠
- [ ] `pytest -q` 全綠，且 collected 數 ≥ 上一階段
- [ ] `python scripts/audit_i18n_parity.py` → `failures=0`
- [ ] 新功能有對應測試，且該測試在 `main` 上會失敗
- [ ] 新的擷取路徑一律 **opt-in**（預設不啟用，需明確旗標或環境變數）
- [ ] PR 說明包含：做了什麼、為什麼、哪些測試新增、哪些既有測試被動到（若有）及原因
- [ ] **不 merge**，等待審查

---

## 5. 階段規劃

### 0.7.5 — Provider 能力探測與真相表

**Branch：`feat/provider-capability-probe`**

#### 目標
用**實測**取代猜測，建立每個 provider 到底拿得到什麼的機器可讀矩陣。這一階段**不新增任何擷取能力**，只做量測與記錄。

#### 為什麼放第一個
目前對 Codex `reasoning.encrypted_content` 是否為 L3，結論是**強推論但未經證明**（依據：rollout 中 reasoning CoT 與 `spawn_agent` 參數使用相同 Fernet scheme、timestamp 型態一致，指向金鑰在 server 側）。後面四個階段的範圍取決於這個答案，必須先解掉。

#### 交付
- `scripts/probe_provider_capability.py` — 對每個 provider 的**既有本地產物**（rollout / transcript / hook 輸出）做欄位盤點，輸出機器可讀矩陣
- 矩陣欄位：provider、欄位名稱、是否存在、是否明文、若非明文則加密層級（`L2_local_key` / `L3_server_side` / `unknown`）、判定依據
- `tests/test_provider_capability_probe.py`
- 一份內部文件記錄 Codex Fernet 取證的結論（**放在不受 i18n 清單管轄的路徑**）

#### 明確不做
- 不新增任何網路擷取
- 不嘗試解密任何內容
- 不修改任何既有 provider adapter

#### 驗收
- [ ] 矩陣對六個 provider（codex / claude / gemini / cursor / opencode / ollama）都有明確判定，未知就寫 `unknown`，不得猜
- [ ] Codex `reasoning.encrypted_content` 的層級判定有明確依據記錄
- [ ] 探測器對缺少產物的 provider 回報「無資料」而非空矩陣

---

### 0.7.6 — 本地 runtime 完整擷取

**Branch：`feat/local-runtime-full-capture`**

#### 目標
本地模型 runtime（Ollama / LM Studio / llama.cpp / vLLM）走的是 **localhost 明文 HTTP**，沒有加密、沒有第三方服務、沒有 ToS 問題。這是最乾淨、最完整的一條路，拿完整的 input + thinking + output + tool tokens。

#### 基礎
既有模組：`model_runtime.py`、`model_runtime_full_fidelity.py`、`openai_compatible.py`、`openai_compatible_full_fidelity.py`、`http_proxy.py` 的明文 relay 路徑（`do_GET` / `do_POST` → `_relay()`）。

**擴充既有模組，不要另起一套平行實作。**

#### 交付
- 完整 request / response 保真擷取，含 tool call 與 tool result
- 支援 streaming 回應的重組（串流分片必須還原成完整訊息才入庫）
- 每個欄位帶 provenance，寫進既有 `FullFidelityContentStore`
- `scripts/check_local_runtime_capture.py` + CI 步驟
- 對應測試

#### 明確不做
- 不碰 HTTPS、不碰 `do_CONNECT`
- 不為了本地 runtime 修改共用的 conversation 合併層語意

#### 驗收
- [ ] 一次本地 runtime 執行的 input / thinking（若模型輸出）/ output / tool token 全部進入 `conversations.json`
- [ ] streaming 與非 streaming 的結果一致
- [ ] 未啟用時行為與 v0.7.4 完全相同

---

### 0.7.7 — 使用者自有 gateway 全保真

**Branch：`feat/gateway-full-fidelity`**

#### 目標
使用者**主動**把 client 的 `base_url` 指向自己架的 gateway（LiteLLM proxy 或自架 OpenAI-compatible endpoint）。這是每家 provider 都支援的標準設定方式，**不是攔截**。

#### 界線（務必遵守）
- ✅ 使用者自己設定 `base_url` / `OPENAI_BASE_URL` 之類的環境變數
- ✅ ExecWeave 提供 gateway、記錄流經自己的請求
- ❌ 不得自動改寫使用者的 client 設定
- ❌ 不得攔截未經使用者設定就流向 provider 的流量
- ❌ 不得做任何形式的透明代理

#### 基礎
`inference_gateway.py`、`inference_gateway_full_fidelity.py`。

#### 交付
- gateway 模式下的完整 request / response 保真擷取
- 文件明確說明「這需要使用者自己設定，ExecWeave 不會替你改」
- `scripts/check_gateway_full_fidelity.py` + CI 步驟
- 對應測試

#### 驗收
- [ ] 未設定 `base_url` 時，ExecWeave 完全不介入
- [ ] 擷取到的內容標記為 `provider_transcript` 僅在真的拿到完整往返時
- [ ] 憑證、API key 不得寫入任何產物（要有測試守）

---

### 0.7.8 — 官方表面的 reasoning 擷取

**Branch：`feat/sanctioned-reasoning-capture`**

#### 目標
對 provider **主動回傳給呼叫端**的 reasoning / thinking 欄位做擷取。範圍由 0.7.5 的矩陣決定。

預期涵蓋：Claude 的 thinking blocks、Gemini 的 reasoning 欄位 —— 前提是 0.7.5 證實這些欄位在官方表面就是明文。

#### 明確不做
- **不處理 Codex 的 `reasoning.encrypted_content`**（L3，本輪放棄）
- 不嘗試任何解密
- 若 0.7.5 顯示某 provider 的 reasoning 不在官方表面，**該 provider 直接跳過**，寫進矩陣，不要想辦法繞

#### 交付
- reasoning 內容納入 conversation record，與一般訊息**在型別上可區分**
- viewer 與 Markdown 對 reasoning 有明確標示
- 對應測試

#### 驗收
- [ ] reasoning 與 output 在資料上分開，不混為一談
- [ ] 沒有 reasoning 的 provider 不會產生空殼或假造的 reasoning 欄位

---

### 0.7.9 — 不可得證據的標記模型

**Branch：`feat/unavailable-evidence-taxonomy`**

#### 目標
把「這裡有東西但我們看不到，原因是 X」變成**一等公民、可測試、不可偽造**的狀態。這是整個規劃裡對產品信譽最重要的一環。

#### 做法
**擴充** `agent_topology.py` 既有詞彙，不是取代。現有：

```python
COMPLETENESS_PROVIDER_TRANSCRIPT = "provider_transcript"
COMPLETENESS_ROUTING_ONLY = "routing_only"
COMPLETENESS_UNAVAILABLE = "unavailable"
```

新增的是**原因**維度：內容存在但被 provider 加密（Codex L3）、provider 根本不曝露該欄位、使用者未啟用擷取 —— 這三種在目前都塌縮成同一個 `unavailable`，使用者無法分辨。

#### 交付
- 不可得原因的列舉常數 + 對應的 `_RANK` 處理
- viewer 與 Markdown 顯示具體原因，取代現在單一那句 `Provider-encrypted payload —`
- **強化 MITM 不變式測試**：明確斷言 `do_CONNECT` 回 405、斷言原始碼中不存在憑證產生或 eBPF 相關呼叫
- `scripts/check_conversation_records.py` 增加檢查：宣稱 `provider_transcript` 的 entry 必須真的有 messages
- 對應測試

#### 明確不做
- 不改既有三個 completeness 常數的名稱或語意
- 不降低任何既有檢查的嚴格度

#### 驗收
- [ ] 使用者能分辨「provider 加密了」vs「provider 沒提供」vs「你沒開擷取」
- [ ] 每個 `unavailable` 都帶得出原因，不得留空
- [ ] MITM 不變式有測試守住

---

### 0.8.0 — 統一 token 帳本

**Branch：`release/0.8.0-token-ledger`**

#### 目標
跨 provider 的統一 token 帳本：input / thinking / output / tool，每一欄都帶來源與可信度，拿不到的明確標記為拿不到。這是整輪的收束。

#### 交付
- 統一 token ledger 資料結構，每個計數帶 provenance（來自 provider 回報 vs ExecWeave 計算 vs 不可得）
- dashboard 呈現
- **完整的能力矩陣文件**：每個 provider 各欄位拿不拿得到、為什麼
- 8 語言 README 更新（由審查後統一處理，見 §7）

#### 驗收
- [ ] provider 回報的 token 數與 ExecWeave 自算的數字**分開呈現**，不得混用
- [ ] 缺漏欄位明確標記，不得補 0 充數
- [ ] 矩陣文件與 0.7.5 探測器的實際輸出一致

---

## 6. 最終審查會檢查什麼

每個 branch 送審時，會逐項核對：

| 項目 | 如何驗證 |
|---|---|
| 測試數未減少 | `pytest -q --collect-only`，對照 757 基準 |
| 沒有偷改既有測試 | `git diff origin/main --stat -- tests/`，逐一檢視被動到的既有測試 |
| 沒有 skip/xfail 繞過 | `grep -rn "skip\|xfail" tests/` 差異比對 |
| 新測試真的有效 | 在 `main` 上套用新測試，確認會失敗 |
| MITM 紅線未破 | `http_proxy.py:321-322` 原封不動；`tests/test_http_proxy.py` 405 測試綠 |
| 無禁用技術 | `grep -rn "ebpf\|uprobe\|LD_PRELOAD\|ptrace\|ssl_write"` 應為空 |
| 證據未膨脹 | 檢查所有新的 `provider_transcript` / `provider_declared` 標記是否有實據 |
| checker 未被放寬 | `git diff origin/main -- scripts/` 逐行看門檻 |
| 無金鑰外洩 | 檢查產物與 fixture 是否含 API key、路徑、使用者名稱 |
| i18n 未受影響 | `python scripts/audit_i18n_parity.py` |
| opt-in | 未啟用時行為與前一版一致 |

**只要發現一項違反 §3，該 PR 退回重做。**

---

## 7. 版本發布流程（審查通過後才執行）

版本 bump 由審查方統一處理，實作者不要碰。記錄在此供參考：

需同步的位置：
- `pyproject.toml:7` 註解 `# ExecWeave vX.Y.Z release metadata`
- `pyproject.toml:8` `version`
- `src/execweave/__init__.py:3` `__version__`
- `tests/test_v069_dashboard_release.py` 中三處寫死的版本斷言
- 8 個 README 各 3 處：current release 行、release 說明段、總結段

強制檢查：
- `scripts/audit_i18n_parity.py` 的 `README_REQUIRED_SNIPPETS` 含 `current_release_tag()`，8 個 README 都必須出現新版本號
- `.github/workflows/publish.yml` 會驗 tag 與 `pyproject.toml` 版本一致，不一致直接失敗

發布順序：
1. workflow_dispatch 跑 CI full matrix（tag push 會展開 3 OS × Python 3.10/3.12，不要讓 tag CI 當第一次 3.10 測試）
2. bump commit → push `main` → 等 CI 綠
3. GitHub UI 建 release、tag `vX.Y.Z`、target `main`
4. `publish.yml` 自動觸發 → PyPI

---

## 8. 一句話總結

**能從官方表面拿到的，全部拿完整；拿不到的，誠實說拿不到並說明原因。不繞過加密、不違反政策、不動既有測試。**
