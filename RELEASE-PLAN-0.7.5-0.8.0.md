# ExecWeave 0.7.5 → 0.8.0 實作規劃書

> 本文件是交給實作者（Codex）逐階段執行的規格。
> **嚴格循序交付**：一個階段 merge 進 `main` 之後，下一個階段才從新的 `main` 開分支。
> 基準：`main` @ `80e23d5`（v0.7.4）。

---

## 0. 這一輪要解決的問題

使用者在 conversation 裡看到：

```
Provider-encrypted payload — plaintext is not exposed by the observed provider surface.
```

目標是把**實際觀察得到**的 input / reasoning / output / tool 內容與 usage 收進來，並且把**觀察不到的部分誠實標記原因**，而不是用猜測填滿。

### 三個層次，決定了什麼做得到

| 層 | 定義 | 本輪立場 |
|---|---|---|
| **傳輸層 TLS** | client ↔ provider 之間的 HTTPS | **不碰**。不做 MITM，不做 eBPF |
| **應用層封裝** | client 在 JSON 欄位再包一層加密 | 只有本機確實存在解密器時才處理 |
| **服務端加密** | 金鑰不在本機 | **不嘗試取得明文**，記錄為不可觀察並註明依據 |

**本輪只走 provider 官方表面與使用者自有端點。**

---

## 1. 不可違反的核心原則

以下適用於**每一個階段**，不因任何理由放寬：

1. **不做 TLS MITM。**
2. **不使用 eBPF / uprobe / kprobe / ptrace / `LD_PRELOAD` / memory scraping / 核心模組。**
3. **不破解 provider encryption。**
4. **provider 沒有明確曝露的內容不得猜測。**
5. **evidence 與 inference 必須分離。**
6. **能取得多少就宣稱多少**，不多報。
7. **拿不到的內容必須明確標示原因。**
8. **不得弱化既有測試、checker 或 evidence semantics。**
9. **provider-specific logic 不得污染共用層。**

### 1.1 不做 TLS MITM 的具體約束

`src/execweave/http_proxy.py:321-322` 是刻意的設計決定：

```python
def do_CONNECT(self) -> None:
    self.send_error(405, "CONNECT is disabled; ExecWeave does not perform TLS MITM")
```

- 這行**必須保留原樣**。
- `tests/test_http_proxy.py:252`（`assert response.status == 405`）**必須永遠綠**。
- 0.7.9 會為它補上更明確的不變式測試，**只能加強、不能放寬**。

### 1.2 既有證據詞彙只能擴充

定義在 `src/execweave/agent_topology.py`：

- 路徑來源：`provider_declared` / `execweave_derived` / `legacy_unknown`（`:51-53`）
- 對話完整度：`provider_transcript` / `routing_only` / `unavailable`（`:57-71`）
- 拓樸證據：`EVIDENCE_*` 常數（`:123-130`）

**只能擴充，不能重寫、改名或改語意。**

### 1.3 Evidence contract（每個階段都適用）

所有 schema / UI / Markdown 都必須讓以下五者**在資料上可區分**，不得互相塌縮：

```
provider-observed fact
≠ ExecWeave-derived interpretation
≠ estimate
≠ unknown
≠ unavailable
```

**Absence of evidence 不等於 negative evidence。** 不得因為 dashboard 想呈現得完整，就把 unknown 填成 `0`、`false`、空字串或推測值。

---

## 2. 政策紅線

### 2.1 正當 vs 不正當

**核心區分：使用者主動重新設定自己的 client 端點，不等於攔截。**

| 做法 | 判定 |
|---|---|
| 讀 provider 官方 hook / rollout / 本地 transcript | ✅ 正當 |
| 使用者**自行**把 client endpoint 指向 ExecWeave 端點 | ✅ 正當（需 opt-in） |
| 擷取本地 runtime（Ollama 等）的 HTTP 往返 | ✅ 正當 |
| 偽造 CA 憑證做 TLS MITM | ❌ 禁止 |
| eBPF uprobe 掛 `SSL_write` / `SSL_read` | ❌ 禁止 |
| 逆向或破解 provider 的加密封裝 | ❌ 禁止 |
| 自動改寫使用者的 client 設定 | ❌ 禁止 |
| 透明代理 / 未經設定即攔截 | ❌ 禁止 |

### 2.2 關於 endpoint 可設定性：不得過度宣稱

**不得寫「每家 provider 都支援 custom base_url」這種敘述。** 實際支援度依 client、client 版本、provider、auth mode、feature surface 而異。例如同一個 client：

- Agent mode 可能支援 custom endpoint
- autocomplete / Tab 補全可能不支援
- API-key auth 與 subscription auth 的行為可能不同

因此 endpoint 可設定性是 **0.7.5 要逐一實測的欄位**，不是預設前提。

### 2.3 拿不到就放棄

拿不到的內容不得用技術手段硬取。改為在 0.7.9 用可驗證的方式標記為不可觀察，並記錄依據。

---

## 3. 絕對禁止事項（防作弊）

任一項出現在 PR 中，該 PR 直接退回，不進行後續審查。

### 3.1 測試相關

1. **不得刪除或修改既有測試來讓自己通過。**

   **baseline test node ID 保存**（不是只看數量）：階段開始前記錄

   ```bash
   pytest -q --collect-only -q | grep "::" | sort > .baseline-test-ids.txt
   ```

   驗收條件：

   ```
   baseline_test_ids ⊆ current_test_ids
   ```

   任何 baseline node ID 消失即 **FAIL**，除非該項是**經審查核可的合法 migration**（例如測試被改名或拆分，但斷言內容等價或更嚴格），且在 PR 說明中逐一列出「舊 ID → 新 ID → 為什麼等價或更嚴格」。

   > 只看 `collected count` 不足以防守：刪 20 個舊測試、加 25 個新測試，數量仍會上升。

2. **不得使用 `pytest.mark.skip` / `xfail` / `pytest.skip()` 繞過失敗。** 現有 6 個 skip 是環境相依（如 `node` 不存在），新增 skip 必須同性質且在 PR 說明。

3. **不得放寬既有 checker 的門檻。**
   - `scripts/check_conversation_records.py` 的重複偵測預設 FAIL，不得改成 warning。
   - 不得用 `--allow-duplicate-agent` 之類的逃生門掩蓋真實缺陷。
   - `scripts/audit_i18n_parity.py` 的 `0.62` 比例門檻不得調低。

4. **不得在測試中寫死期望值來製造通過。** 測試必須驗證行為，不是驗證「我剛剛寫進去的字串」。

5. **新測試的有效性要求，依測試類型區分：**

   | 類型 | 要求 |
   |---|---|
   | **Feature behavior test** | 必須在**套用修改前的 main** 上失敗。PR 說明要寫出會怎麼失敗 |
   | **Regression / invariant guard** | **不要求**在 main 上失敗。這類測試（`do_CONNECT` 回 405、TLS MITM 維持關閉、credential sanitization 成立）在 main 上本來就該通過，它們的價值是鎖住不變式 |

   PR 說明必須**標明每個新測試屬於哪一類**。把 feature test 偽裝成 invariant guard 以規避「必須在 main 上失敗」的要求，視同作弊。

### 3.2 證據誠信相關

6. **不得捏造證據。** 沒有 provider 明確給出的東西，不得標記為 `provider_transcript`、`provider_declared`、`observed`、`reported`。不確定的一律走 `unavailable` / `unknown` / `execweave_derived`。**寧可少報，不可多報。**

7. **不得把 observation 升級成 fact。** 詳見 §4。「本機找不到解密器」是 observation，不得升級成「金鑰只存在 provider server」這種 fact。

8. **不得用推測填補缺口。** 拿不到 reasoning 就標記拿不到，不得用 output 反推、不得用其他 agent 的內容代替。

9. **不得偽造 fixture。** 宣稱來自真實 provider 輸出的 fixture 就必須真的是。可去識別化（使用者名稱、本機絕對路徑、無關檔名、金鑰、私人內容），但結構欄位必須保留原樣。

10. **credentials 不得進入任何 artifact。** API key、`Authorization` header、token、cookie 一律不得寫入 events、content store、graph、viewer、conversations。既有的 `filter_transport_credentials`（`content_evidence.py`）與 `_sanitize_metadata`（`inference_gateway_full_fidelity.py:146`）必須沿用，不得繞過。

### 3.3 技術手段相關

11. **不得啟用 TLS MITM。** 不得修改 `do_CONNECT`、不得加入憑證產生、不得修改系統 trust store。
12. **不得使用 eBPF / uprobe / kprobe / 核心模組 / `LD_PRELOAD` / `ptrace` / 記憶體讀取。**
13. **不得關閉 TLS 驗證，不得 unset `HTTPS_PROXY`。**
14. **不得引入需要 root / `CAP_BPF` / 管理員權限的功能。**

### 3.4 架構相關

15. **不得建立第二套 full-fidelity schema。** 既有的 `FullFidelityContentStore`、`content_observation_event`、`*_to_content_events` 系列是唯一的 full-fidelity 路徑。
16. **不得建立平行的 conversation ingestion pipeline。**
17. **provider-specific logic 不得污染共用層。** provider 專屬邏輯留在該 provider 的模組內。

### 3.5 流程相關

18. **不得自行 bump 版本、打 tag、建 release。**
19. **不得 merge 自己的 PR，不得直接 push `main`，不得 force push，不得改寫既有歷史。**
20. **不得跨階段混合。** 一個 branch 只做該階段的事。發現其他問題就記錄，不要順手改。
21. **不得把新文件加入 `scripts/audit_i18n_parity.py` 的 `DOCS` 清單**，除非同時提供 7 種語言翻譯（`zh-TW` `zh-CN` `ja` `ko` `fr` `de` `ru`）。
22. **不得修改 8 個 README 的版本錨點。** README 由版本發布流程統一處理。

---

## 4. Capability taxonomy：observation-based，不得過度宣稱

這是 0.7.5 的核心產出，也是後續所有階段的詞彙基礎。

### 4.0 兩層責任邊界：conversation-level vs field-level

**這兩層必須分開，且必須能同時存在。**

| 層級 | 描述的是 | 放在哪 | 值 |
|---|---|---|---|
| **Conversation-level completeness** | 一個 agent conversation **整體**有多少 conversational evidence | `agent_topology.py`（**語意不得更動**） | `provider_transcript` / `routing_only` / `unavailable` |
| **Content / field-level availability** | **某一個 content field 或 observation** 的可得性 | `content_evidence.py`，或新增 `evidence_availability.py` | 見 §4.2 |

以下組合是**完全合理**的，必須支援：

```
conversation_completeness = provider_transcript
reasoning_availability    = opaque_encrypted
```

**不得因為 reasoning 看不到，就把整個 conversation 降成 `unavailable`。** 一個 agent 的 transcript 被完整存下來，就是 `provider_transcript`，其中某個欄位是密文是另一回事。

### 4.1 為什麼不能用 `L3_server_side`

先前的草案把 Codex 的 `reasoning.encrypted_content` 直接標成 `L3_server_side`。**這違反 ExecWeave 自己的 evidence discipline。**

目前實際掌握的證據只有：

- ciphertext 外觀符合 Fernet（`gAAAAA` 前綴）
- 本機目前找不到解密器
- rollout 中其他欄位有類似封裝

這些**都不足以證明**「金鑰一定只存在 provider server」。因此 taxonomy 必須把**觀察到什麼**與**能不能解密**分成兩個獨立維度。

### 4.2 Field-level availability：單一欄位的可得性

**這是欄位層唯一的可得性詞彙**，由 0.7.5 定義、0.7.9 正式落地。放在 `content_evidence.py` 或新增的 `evidence_availability.py`，**不得放進 `agent_topology.py`**。

| 值 | 意義 |
|---|---|
| `available` | 該欄位可得 |
| `complete_from_surface` | 該表面實際曝露的內容被完整保存（宣稱邊界見 §4.6） |
| `summary` | 只有摘要，沒有完整內容 |
| `redacted` | provider 主動遮蔽（例如 `[redacted]` 標記） |
| `opaque_encrypted` | 出現的是密文，內容不可讀 |
| `opaque_signed` | 出現的是簽章/雜湊之類的不可逆表示 |
| `not_exposed` | 該表面根本沒有這個欄位 |
| `not_observed` | 這次觀察沒看到，但不代表不存在 |
| `capture_disabled` | 使用者未啟用擷取 |
| `capture_interrupted` | 擷取中斷 / 串流不完整 |
| `unknown` | 尚未判定 |

命名不強制與上表完全一致，但**責任邊界必須清楚**：這些值描述單一 field，**不描述整個 conversation**。

### 4.3 `decryptability`：能不能在本機解開

| 值 | 意義 |
|---|---|
| `locally_decryptable` | 本機存在可用的解密器，且已驗證 |
| `no_local_decryptor_observed` | **本機沒有觀察到解密器**（這是 observation，不是結論） |
| `provider_documented_unavailable` | **provider 官方文件明確說明不提供**（這才是 fact） |
| `unknown` | 尚未判定 |

### 4.4 升級規則

**只有在下列其中一種情況下，才允許使用比 `no_local_decryptor_observed` 更強的宣稱：**

1. provider 官方文件明確說明 → `provider_documented_unavailable`，並記錄文件出處
2. 有直接可驗證的證據

**「沒有在本機找到 key」只能記錄成 `no_local_decryptor_observed`，永遠不得自動升級成 server-side fact。**

具體到 Codex：`reasoning.encrypted_content` 目前應記為
`availability: opaque_encrypted` + `decryptability: no_local_decryptor_observed`，
並在 `notes` 記錄 Fernet 外觀與同 scheme 觀察。**不得寫成 server-side-only。**

### 4.5 Capability matrix 的粒度

**不得只做 `provider × field`。** 同一個 client 的不同 surface 行為可能完全不同，矩陣必須以**實際 surface** 為單位，至少包含：

| 欄位 | 說明 |
|---|---|
| `client` | 例如 codex-cli、claude-code、cursor |
| `client_version` | 實測時的版本 |
| `provider` | 上游 provider |
| `auth_mode` | api_key / subscription / oauth / local |
| `surface` | agent mode / autocomplete / chat / background task |
| `transport_mode` | direct / user_routed_gateway / local_runtime |
| `field` | 觀察的欄位 |
| `availability` | 見 §4.2 |
| `decryptability` | 見 §4.3 |
| `evidence_source` | 這筆判定來自哪裡 |
| `evidence_strength` | 直接觀察 / 文件 / 推論 |
| `notes` | 補充 |

### 4.6 `complete_from_surface` 的宣稱邊界

ExecWeave 能證明的是：**它完整保存了 provider surface 實際曝露給它的 payload**。ExecWeave **無法**從 API / hook / transcript 證明那等於模型內部的全部 reasoning 或隱藏階段。

這與 `main` 上既有的 `ContentReference.complete_from_source` 語意一致（`content_store.py:20-21`）：

> `complete_from_source` means ExecWeave stored the complete value supplied by the integration point. It does not claim the provider exposed hidden stages.

viewer 也已經如此措辭（`viewer_content_inspector.py:212`）：

> "Complete from source: the selected integration supplied this complete value. **This does not imply visibility into hidden model/provider state.**"

因此 `complete_from_surface` 的定義固定為：

> **ExecWeave 完整保存 provider surface 實際曝露的 payload；不宣稱這是模型內部的全部 reasoning。**

**全文件、UI、Markdown 一律禁止使用**：`full reasoning`、`Full CoT`、`complete chain of thought`、「完整思維鏈」。
**建議措辭**：`Provider-exposed reasoning`。

例外：provider 官方 surface 本身明確如此定義，且有直接證據 —— 此時必須在 `notes` 記錄文件出處。

---

## 5. 交付順序：嚴格循序

**不使用六個平行、互不相依的 branch。** 後面的階段依賴前面建立的 schema 與能力：

- 0.7.8 依賴 0.7.5 建立的 capability / evidence taxonomy
- 0.7.9 消費 0.7.6–0.7.8 建立的 capture / evidence semantics
- 0.8.0 的 usage ledger 依賴 0.7.6–0.7.9 的結果

因此流程固定為：

```
0.7.5 branch (from latest main)
  → tests / CI / review
  → merge main
0.7.6 branch (from NEW main)
  → tests / CI / review
  → merge main
0.7.7 branch (from NEW main)
  → ...
```

**每一階段開始前都必須重新 fetch 最新 `main`：**

```bash
git fetch origin main
git checkout -b <branch> origin/main
```

前一階段尚未 merge 進 `main` 之前，**不得開始下一階段**。

---

## 6. 每個階段的共通交付規則

- [ ] 從**最新的 `main`** 開分支
- [ ] 階段開始前記錄 baseline test node IDs
- [ ] `ruff check .` 全綠
- [ ] `pytest -q` 全綠，且 `baseline_test_ids ⊆ current_test_ids`
- [ ] `python scripts/audit_i18n_parity.py` → `failures=0`
- [ ] 新功能有對應測試，且**標明是 feature test 還是 invariant guard**
- [ ] 新的擷取路徑一律 **opt-in**（預設不啟用）
- [ ] 未啟用時行為與前一版**完全相同**
- [ ] PR 說明包含：做了什麼、為什麼、新增哪些測試（分類）、動到哪些既有測試及原因
- [ ] **不 merge**，等待審查

---

## 7. 階段規劃

### 0.7.5 — Capability & Evidence Matrix

**Branch：`feat/provider-capability-matrix`**

#### 目標
只做**探測與 taxonomy**，不新增任何 capture 能力。

#### 為什麼放第一個
後續四個階段的範圍完全取決於這裡的量測結果。目前對 Codex `reasoning.encrypted_content` 的判斷是推論而非證明，不該讓四個版本建在未驗證的假設上。

#### Required Capability Inventory

**驗收對象是這份 inventory，不是理論上的 Cartesian product。** 不要求把所有 client × surface × auth_mode 組合測完。

**Tier A — Required / release-blocking**

涵蓋 ExecWeave 目前主要宣稱支援、或必須明確知道其 capability 的 client：

| client | provider | auth_mode | surface | transport_mode |
|---|---|---|---|---|
| Codex CLI | OpenAI | api_key / subscription | agent | direct |
| Claude Code | Anthropic | api_key / subscription | agent | direct |
| Gemini CLI | Google | api_key | agent | direct |
| Cursor Agent | Cursor / 上游 | subscription | agent | direct |
| OpenCode | 依設定 | api_key | agent | direct |
| Ollama | 本地 | local | chat / generate | local_runtime |

每個 Tier A row 都必須明確指定：`client`、實測的 `client_version`（或最低版本）、`provider`、`auth_mode`、`surface`、`transport_mode`、以及 **required fields to probe**（至少：system / prompt / messages、tool definitions、tool arguments、tool results、assistant output、reasoning、usage）。

**若某 row 在測試環境無法取得，不得刪除該 row**，必須標 `not_observed` 並在 `notes` 寫明原因（例如「無此 client 授權」「環境無 GPU」）。

**Tier B — Optional / environment-dependent**

Cursor autocomplete / Tab、background agent surfaces、其他 auth modes、其他本地 runtime（LM Studio / llama.cpp / vLLM）、其他 gateway 組合。

依環境測試，**不阻塞 0.7.5 release**，但結果仍可進 matrix。

#### 交付
- field-level availability / `decryptability` 兩組常數與升級規則（§4.2–4.4），實作為可測試的模組，**放在 `content_evidence.py` 或新增的 `evidence_availability.py`，不得放進 `agent_topology.py`**
- Required Capability Inventory（Tier A / Tier B）的機器可讀定義
- `scripts/probe_provider_capability.py` — 對每個 provider 的**既有本地產物**（rollout / transcript / hook 輸出）做欄位盤點
- 機器可讀的 capability matrix，欄位依 §4.5，**以 surface 為粒度**
- 對應測試
- 內部文件記錄判定依據（放在**不受 i18n `DOCS` 清單管轄**的路徑）

#### 明確不做
- 不新增任何網路擷取
- 不嘗試解密任何內容
- 不修改任何既有 provider adapter
- 不對 endpoint 可設定性做未經實測的宣稱
- **不修改 `agent_topology.py` 的 conversation completeness**

#### 驗收
- [ ] **Required Capability Inventory 中每個 Tier A（release-blocking）row 都有明確結果**；未觀察到就標 `not_observed` 並寫原因，**不得刪除該 row，不得猜測**
- [ ] Tier B row 若未測，明確標示為未測，不得留白
- [ ] Codex `reasoning.encrypted_content` 記為 `opaque_encrypted` + `no_local_decryptor_observed`，**不得**出現 server-side-only 的宣稱
- [ ] 有測試驗證「升級規則」：沒有官方文件或直接證據時，不允許產生 `provider_documented_unavailable`
- [ ] 有測試驗證 field-level availability **不會**被寫入 conversation completeness
- [ ] 探測器對缺少產物的 provider 回報「無資料」而非空矩陣

---

### 0.7.6 — Local Runtime Live Capture + Streaming Reconstruction

**Branch：`feat/local-runtime-live-capture`**

#### 這一階段**不是**從零做本地擷取

`main` 上已經存在的能力（**必須重用，不得重造**）：

| 既有實作 | 已具備 |
|---|---|
| `model_runtime_full_fidelity.py:291` `runtime_exchange_to_content_events()` | request / request messages / prompt / input / system / tools / tool result messages / provider-facing config / response / assistant tool calls，並標記 `caller_supplied_exchange: True`、`wire_interception_asserted: False` |
| 同檔 `:447-501` | ollama / llamacpp / vllm / lmstudio 各自的 helper |
| `http_proxy.py:172` `record_exchange_fail_open()` | 已有 live relay，已標記 `transport_relay_observed: True` |
| `http_proxy.py:91` `_stream_items()` | 已解析 `text/event-stream` 與 ndjson，原始分片保存在 `stream_chunks` |

#### 真正的缺口

`http_proxy.py:189`：

```python
response = chunks[-1] if chunks and isinstance(chunks[-1], dict) else _json(response_body)
```

canonical `response` 直接取**最後一個 chunk**。OpenAI 式串流的最後一片通常是空 delta（`{"choices":[{"delta":{},"finish_reason":"stop"}]}`），因此**串流內容目前並未進入 canonical record**；原始分片雖然保留在 `stream_chunks`，但從未被重組。

**這一階段要補的就是 canonical stream assembler。**

#### 目標架構

```
client
  → ExecWeave-owned local relay
  → forward to Ollama / LM Studio / llama.cpp / vLLM
  → observe streaming or non-streaming response
  → canonical stream assembler          ← 本階段新增
  → 既有 FullFidelityContentStore / evidence emitters
```

#### 明確要求
- **擴充現有模組**，不建立第二套 full-fidelity schema
- **不建立平行的 conversation ingestion pipeline**
- streaming 與 non-streaming 最終必須產生**相同的 canonical semantics**
- 原始 raw stream evidence 可以保留，但 **canonical conversation 不得被 chunk fragmentation 污染**
- 不碰 HTTPS、不碰 `do_CONNECT`

#### Streaming reconstruction semantics（驗收標準）

驗收標準是 **canonical semantic equivalence**，不是模糊的「結果一致」。至少必須覆蓋：

| # | 情境 |
|---|---|
| 1 | text / content delta 累積 |
| 2 | reasoning / thinking delta 累積 |
| 3 | 跨 chunk 分片的 tool call **name** |
| 4 | 跨 chunk 分片的 tool call **arguments** |
| 5 | 多個平行 tool calls（依 index 正確歸位） |
| 6 | `finish_reason` |
| 7 | 只帶 usage 的最終 chunk |
| 8 | multi-choice 回應 |
| 9 | UTF-8 字元被切在 chunk 邊界 |
| 10 | 格式錯誤的 chunk |
| 11 | 不完整的串流（沒有終止標記） |
| 12 | 連線中斷 |

**tool arguments 跨 chunk 的具體例子：**

```
chunk 1: {"pa
chunk 2: th":"
chunk 3: foo"}
```

**不得逐 chunk 當成完整 tool call 入庫。** 必須先重組成 `{"path":"foo"}` 再產生 canonical record。

情境 10–12（錯誤與截斷）**不得靜默吞掉**：必須產生明確的不完整標記，走 §4 的 taxonomy，不得假裝拿到完整內容。

#### 驗收
- [ ] 12 個 streaming 情境各有測試
- [ ] 同一組語意內容，streaming 與 non-streaming 產生等價的 canonical record（欄位級比對）
- [ ] canonical record 中不存在未重組的分片
- [ ] `stream_chunks` 原始證據仍保留
- [ ] 未啟用時行為與 v0.7.5 完全相同

---

### 0.7.7 — User-Routed Live Gateway Capture

**Branch：`feat/user-routed-gateway-capture`**

#### 這一階段**不是**從零做 gateway full fidelity

`main` 上已經存在的能力（**必須重用**）：

`inference_gateway_full_fidelity.py` 已支援 OpenRouter exchange、request messages、prompt / input、tool definitions、tool results、tool calls、provider-facing parameters、response，以及 metadata credential filtering（`_sanitize_metadata:146`、`_secret_metadata_key:137`）。
`inference_gateway.py:289` 已有 LiteLLM 支援，`litellm_callback_cli.py` 已有 callback 安裝路徑。

#### 真正的缺口

現有的是**事後 exchange 記錄**與 **callback**。缺的是使用者明確把 client endpoint 指向 ExecWeave 自有端點的 **live route**：

```
client
  → ExecWeave-owned gateway     ← 本階段
  → provider / upstream
```

ExecWeave 記錄自己實際收到與送出的內容。

#### 明確要求
- **重用現有 gateway full-fidelity emitters**，不建立第二套 schema
- **不自動修改 client 設定** —— 使用者自己設 endpoint，ExecWeave 不代勞
- **不做 transparent interception**
- **未 opt-in 時 ExecWeave 完全不介入**
- 沿用 0.7.6 的 canonical stream assembler，不另寫一套

#### Credential filtering 的責任邊界（務必精確）

**這是最容易做錯的一項。** 先前寫成「涵蓋 header、body、metadata 三處」是危險的敘述，容易讓實作者做出一個對整份 payload 遞迴清洗的 sanitizer。

`main` 上既有的原則已經寫在 `content_evidence.py:26-29`：

> Remove transport credentials **from provider metadata only**.
> **Do not apply this to prompts, completions, tool input/output, or file content.**
> Those are full-fidelity evidence and remain unredacted.

**這個原則正式納入 roadmap，必須遵守。**

**必須移除的 —— transport envelope / integration metadata credentials：**

`Authorization`、`Proxy-Authorization`、`Cookie` / `Set-Cookie`、`x-api-key`、`api-key`、gateway authentication metadata、`access_token`、`refresh_token`、`client_secret`。這些**不得進入任何 artifact**。

**不得因 key 名稱自動刪除的 —— semantic payload：**

prompt、completion、reasoning content、tool arguments、tool results、file content、provider-visible message content。

**具體風險（已驗證存在）**：`content_evidence.py` 的 `_TRANSPORT_CREDENTIAL_KEYS`（`:7-22`）**包含 `"password"`**，而 `filter_transport_credentials` 是**任意深度的遞迴 key-name walker**（`:34-47`）。若把它套到 semantic payload，下列合法證據會被靜默刪除：

```json
{"role": "user", "content": "The JSON field is called password"}
```

```json
{"password": "example test fixture value"}
```

第二例是 tool argument。**不能因為 key 名稱叫 `password` 就被 generic transport sanitizer 刪掉**，否則 full fidelity 就破了。目前唯一的防線只有那句 docstring，**沒有機制性強制** —— 本階段要補上測試。

責任描述固定為：

> **transport envelope / integration metadata credentials must be removed；semantic payload must not be recursively redacted by transport credential filters.**

#### 驗收
- [ ] 未設定 endpoint 指向時，ExecWeave 完全不介入（有測試）
- [ ] **transport credential leakage test**：`Authorization` / `x-api-key` / `Cookie` / `access_token` 等不得出現在任何 artifact
- [ ] **semantic fidelity preservation test**：prompt / tool arguments / tool results 中出現 `password`、`token`、`api_key` 這類**欄位名或字樣**時，**不得**被 transport sanitizer 刪除
  - 註：此測試不要求保存真實秘密，fixture 用明顯的假值即可。驗證目標是「transport sanitization 不得誤傷 semantic evidence」
- [ ] 只有真的拿到完整往返時才標記為完整；部分失敗走 §4.2 field-level availability
- [ ] streaming 走 0.7.6 的同一個 assembler，不重複實作

---

### 0.7.8 — Provider-Exposed Reasoning

**Branch：`feat/provider-exposed-reasoning`**

#### 目標
只擷取 provider **明確曝露**的 reasoning / thinking。範圍**完全由 0.7.5 的矩陣決定**。

#### reasoning state 必須可區分

沿用 §4.2 的 field-level availability 詞彙，不另立一套：

| 值 | 意義 |
|---|---|
| `complete_from_surface` | **ExecWeave 完整保存 provider surface 實際曝露的 reasoning payload；不宣稱這是模型內部的全部 reasoning** |
| `summary` | 只有摘要 |
| `redacted` | provider 主動遮蔽 |
| `opaque_encrypted` | 密文 |
| `opaque_signed` | 只有簽章 |
| `not_exposed` | 該表面沒有這個欄位 |
| `unknown` | 尚未判定 |

**先前草案用 `full` 表示「完整 reasoning」，這是過強宣稱，已移除。** ExecWeave 從 API / hook / transcript 無法證明所觀察到的等於模型內部的全部 reasoning 或隱藏階段；它只能證明自己完整保存了 surface 給出的東西。這與既有的 `ContentReference.complete_from_source`（`content_store.py:20-21`）語意一致。

#### 用語規定

**禁止**（程式碼、schema、dashboard、Markdown、文件一律適用）：
`full reasoning`、`Full CoT`、`complete chain of thought`、「完整思維鏈」、「完整 CoT」

**使用**：`Provider-exposed reasoning`

#### 明確不做
- 不嘗試任何解密
- 不處理 `opaque_encrypted` 的內容還原
- 若 0.7.5 顯示某 provider 的 reasoning 不在官方表面，**該 provider 直接跳過**，寫進矩陣，不要想辦法繞

#### 驗收
- [ ] reasoning 與 output 在資料型別上分開，不混為一談
- [ ] 每筆 reasoning 都帶 reasoning state（§4.2 詞彙）
- [ ] 沒有 reasoning 的 provider 不會產生空殼或假造的 reasoning 欄位
- [ ] 有測試驗證 `summary` 不會被呈現成 `complete_from_surface`
- [ ] **有測試或檢查驗證全文件與 UI 不出現禁用的 full-CoT 措辭**
- [ ] reasoning 的 availability 為 `opaque_encrypted` 時，該 agent 的 `conversation_completeness` **不因此被降級**

---

### 0.7.9 — Evidence Availability Taxonomy

**Branch：`feat/evidence-availability-taxonomy`**

#### 目標
把「這裡有東西但我們看不到，原因是 X」變成**一等公民、可測試、不可偽造**的狀態。這是整輪對產品信譽最重要的一環。

#### 做法：兩層分開，不得混用

**這一階段最容易做錯的是把 field-level 的原因塞進 conversation-level 的 completeness。禁止這麼做。**

| 層級 | 檔案 | 本階段可否更動 |
|---|---|---|
| Conversation-level completeness（`provider_transcript` / `routing_only` / `unavailable`） | `agent_topology.py` | **不得新增值、不得改語意、不得改 `_COMPLETENESS_RANK`** |
| Field-level availability（§4.2） | `content_evidence.py` 或 `evidence_availability.py` | 本階段正式落地 |

**明確禁止：**

- 不得把 `capture_disabled`、`capture_interrupted`、`opaque_encrypted`、`not_exposed` 之類的 **field-level reason 加進 conversation completeness 的列舉或其 rank**
- 不得因為某個 field 不可得，就把整個 conversation 降級

以下組合必須成立且有測試：

```
conversation_completeness = provider_transcript   # transcript 完整存下來了
reasoning_availability    = opaque_encrypted      # 其中 reasoning 欄位是密文
```

現況問題在 **field 層**：目前不同原因都塌縮成同一句 `Provider-encrypted payload —`，使用者無法分辨「provider 加密了」/「provider 沒曝露」/「你沒開擷取」/「擷取中斷」。這要在 field 層解決，不是在 conversation 層。

#### 交付
- field-level availability 正式落地（0.7.5 定義、此處接上實際 pipeline），含 reason 與 evidence strength
- viewer 與 Markdown 顯示**具體原因**，取代目前單一那句 `Provider-encrypted payload —`
- **anti-overclaim checks**：
  - 宣稱 `provider_transcript` 的 entry 必須真的有 messages
  - 宣稱 `complete_from_surface` 的必須真的有保存到 surface 給出的內容
  - 每個不可得的 field 必須帶得出原因，不得留空
  - **不得出現 §4.6 禁用的 full-CoT 措辭**
- **強化 MITM 不變式測試**：明確斷言 `do_CONNECT` 回 405、斷言原始碼不存在憑證產生與禁用技術的呼叫
- `scripts/check_conversation_records.py` 增加對應檢查

#### 明確不做
- 不改既有三個 completeness 常數的名稱、語意或 rank
- 不把 field-level reason 併入 conversation completeness
- 不降低任何既有檢查的嚴格度

#### 驗收
- [ ] 使用者能分辨「provider 加密了」/「provider 沒提供」/「你沒開擷取」/「擷取中斷」
- [ ] 每個不可得的 field 都帶原因
- [ ] **有測試驗證 `provider_transcript` + `opaque_encrypted` 可同時成立**，且 conversation 不被降級
- [ ] **有測試驗證 field-level reason 不會出現在 conversation completeness 的列舉或 rank 中**
- [ ] anti-overclaim checks 有測試，且會對刻意造假的輸入 FAIL
- [ ] MITM 不變式有測試守住（invariant guard 類）

---

### 0.8.0 — Usage Ledger + Dashboard

**Branch：`release/0.8.0-usage-ledger`**

#### 為什麼不能直接分成 input / thinking / output / tool

不同 provider 的 usage schema 差異很大，可能提供 `input_tokens`、`output_tokens`、`total_tokens`、`reasoning_tokens`、`cached_input_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens`、`audio_tokens` 等。

而且 **tool tokens 通常不是獨立的計費類別**：

- tool definitions 可能已包含在 input
- tool results 在下一輪可能已包含在 input
- tool call arguments 可能已包含在 output

**若再獨立加一個 tool tokens 進 total，會 double counting。**

#### 雙層模型

**第一層 — Native Usage**

完整保留 provider 原始 usage schema，**不丟失任何欄位**、不改名、不重新詮釋。

**第二層 — Normalized Ledger**

可提供：`input` / `output` / `reasoning` / `cache_read` / `cache_write` / `tool_input_estimate` / `tool_output_estimate` / `other`

每個 normalized field **必須攜帶**：

| 屬性 | 說明 |
|---|---|
| `value` | 數值 |
| `unit` | 單位 |
| `status` | 見下 |
| `provenance` | 來源 |
| `confidence` | 可信度 |
| `native_field` | 對應的原始欄位 |
| `included_in_total` | 是否已計入 total（防重複加總） |
| `model` | 模型 |
| `tokenizer` | 使用的 tokenizer（若為估算） |

`status` 至少區分：`reported` / `derived` / `estimated` / `not_reported` / `not_applicable` / `unavailable`

#### 禁止
- **`unavailable` 填 `0`**
- **`estimated` 偽裝成 provider-reported**
- **tool estimate 與 input/output 重複計入 total**
- **provider usage 與 ExecWeave tokenizer estimate 混成同一個數字**

#### 交付
- Native usage 保存 + normalized ledger（含上述完整 metadata）
- dashboard 呈現，provider-reported 與 ExecWeave-estimated **視覺上與資料上都分開**
- 完整能力矩陣文件，與 0.7.5 探測器的實際輸出一致
- 8 語言 README 更新（由版本發布流程統一處理，見 §9）

#### 驗收
- [ ] 有測試驗證 double counting 不會發生（`included_in_total` 生效）
- [ ] 有測試驗證 `unavailable` 不會被填成 0
- [ ] provider-reported 與 estimated 在資料上可區分，且 dashboard 不混用
- [ ] native usage 欄位無遺失（對照原始 payload 逐欄比對）

---

## 8. 最終審查會檢查什麼

| 項目 | 如何驗證 |
|---|---|
| baseline 測試未消失 | `baseline_test_ids ⊆ current_test_ids`，逐一核對缺失項 |
| 沒有偷改既有測試 | `git diff origin/main --stat -- tests/`，逐一檢視被動到的既有測試 |
| 沒有 skip/xfail 繞過 | `grep -rn "skip\|xfail" tests/` 差異比對 |
| feature test 真的有效 | 在 pre-change `main` 上套用，確認會失敗 |
| invariant guard 分類正確 | 檢查被標為 invariant 的測試是否真的是不變式，而非規避 |
| MITM 紅線未破 | `http_proxy.py:321-322` 原封不動；405 測試綠 |
| 無禁用技術 | `grep -rniE "ebpf\|uprobe\|kprobe\|LD_PRELOAD\|ptrace\|SSL_write\|SSL_read"` 應為空 |
| 證據未膨脹 | 檢查所有新的 `provider_transcript` / `provider_declared` / `reported` / `complete_from_surface` 標記是否有實據 |
| observation 未升級成 fact | 檢查是否出現未經文件佐證的 server-side-only 宣稱 |
| 兩層未混用 | `git diff origin/main -- src/execweave/agent_topology.py`；不得有新的 completeness 值或 rank 變動 |
| 無過強 reasoning 宣稱 | `grep -rniE "full[ _-]?cot\|complete chain of thought\|full reasoning\|完整思維鏈\|完整 ?CoT"` 應為空 |
| semantic payload 未被誤刪 | 檢查 `filter_transport_credentials` 是否被套用到 prompt / tool IO / file content |
| 無第二套 schema | 檢查是否重用既有 full-fidelity emitters |
| checker 未被放寬 | `git diff origin/main -- scripts/` 逐行看門檻 |
| 無 credential 外洩 | 檢查產物與 fixture 是否含 API key、Authorization、路徑、使用者名稱 |
| i18n 未受影響 | `python scripts/audit_i18n_parity.py` |
| opt-in | 未啟用時行為與前一版一致 |

**只要發現一項違反 §3，該 PR 退回重做。**

---

## 9. 版本發布流程（審查通過後才執行）

版本 bump 由審查方統一處理，實作者不要碰。記錄在此供參考：

需同步的位置：
- `pyproject.toml:7` 註解 `# ExecWeave vX.Y.Z release metadata`
- `pyproject.toml:8` `version`
- `src/execweave/__init__.py:3` `__version__`
- `tests/test_v069_dashboard_release.py` 中三處寫死的版本斷言
- 8 個 README 各 3 處：current release 行、release 說明段、總結段

強制檢查：
- `scripts/audit_i18n_parity.py` 的 `README_REQUIRED_SNIPPETS` 含 `current_release_tag()`，8 個 README 都必須出現新版本號
- `.github/workflows/publish.yml` 會驗 tag 與 `pyproject.toml` 版本一致

發布順序：
1. workflow_dispatch 跑 CI full matrix（tag push 會展開 3 OS × Python 3.10/3.12）
2. bump commit → push `main` → 等 CI 綠
3. GitHub UI 建 release、tag `vX.Y.Z`、target `main`
4. `publish.yml` 自動觸發 → PyPI

---

## 10. 尚未解決的設計問題

以下問題**在對應階段開始前必須先有答案**，不得邊做邊猜：

1. ~~**0.7.5 的實測涵蓋範圍**~~ — **已解決**。由 §7 的 Required Capability Inventory 定義：Tier A 六個 client 為 release-blocking，Tier B 依環境。驗收對象是 inventory 中的 row，不是理論組合。實作者不需要、也不得自行決定最小必測集。

2. **0.7.8 的範圍可能塌縮** — 若 0.7.5 顯示多數 provider 的 reasoning 不在官方表面，0.7.8 可能幾乎沒有可做的內容。**那時候應該重排階段而不是硬做。** 這個決策點必須在 0.7.5 review 時處理。

3. **normalized ledger 的 tool estimate 是否值得做** — 若 `included_in_total` 對所有 provider 都是 false（代表 tool tokens 一律已含在 input/output），那 `tool_input_estimate` / `tool_output_estimate` 的價值需要重新評估。建議 0.8.0 開始前依 0.7.5 矩陣決定。

4. **tokenizer 來源** — normalized ledger 的 `estimated` 值需要 tokenizer。使用哪一個、如何處理 tokenizer 與 provider 實際計算不一致，尚未決定。不得預設「用某個 tokenizer 算出來的就是對的」。

5. **0.7.6 / 0.7.7 的 assembler 共用邊界** — canonical stream assembler 應該放在哪一層才不會變成共用層裡的 provider 特例？0.7.6 實作時必須先確定，0.7.7 直接沿用。

---

## 11. 一句話總結

**能從官方表面觀察到的，完整收進來；觀察不到的，誠實記錄看到什麼、為什麼解不開。不繞過加密、不違反政策、不動既有測試、不重造已有能力。**
