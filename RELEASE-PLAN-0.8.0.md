# ExecWeave 0.8.0 實作規劃書

> 基準：`main` @ `bfdfb1b`（v0.7.9）。
> 本文件是逐項執行的規格，不是提案。每一項都要有對應的瀏覽器驗證。

---

## 0. 這一輪要解決什麼

v0.7.9 把 Live / 完成後 / `viewer.html` 收斂成同一套 Dashboard，agent 面板縮成
「root：Prompt + Final response」「subagent：Task + Thinking + Response」。

實際跑一個五 agent、兩輪提問的 run 之後，暴露三件事：

1. 有兩個 subagent 的 Response 不見了，顯示成加密。
2. `/root` 面板把第一個問題配上第二個問題的答案，中間那輪的真正答案完全看不到。
3. process / file / tool_call 這些節點點下去幾乎沒有資訊，在圖上失去意義。

前兩件是缺陷，第三件是缺口。

---

## 1. 修正：subagent 的 Response 被誤判為注入內容

### 現象

同一個 run，五個 subagent 之中兩個的 Response 欄位顯示：

```
Observed — plaintext not exposed by provider.
```

但 `conversations.json` 裡那則 `subagent_final_response` 是 `plaintext`，內容完好。

### 根因

v0.7.9 的 `_mark_shared_injected_context()`（`src/execweave/_conversation_records_core.py`）規則是：

> 一段文字（≥400 字元）逐字出現在兩個以上 agent 之下，就標記為
> `content_role = "shared_injected_context"`。

這條規則是為了擋掉 provider 加在每個 subagent 前面的外掛清單。但 **child 的回答本來
就會同時出現在兩個地方**：它自己的 rollout，以及 root 的紀錄（因為它把答案回報給
root）。於是回答被當成注入內容，`viewer_agent_panel.py` 的 `isInjected()` 把它濾掉。

五個 agent 之中只有兩個中招，是因為另外三個的答案**短於 400 字元**，僥倖躲過門檻。

### 修法

該規則只能套用在**送進來的交辦**上：

- 僅考慮 `recipient === <該 agent>` 且 `sender !== <該 agent>` 的訊息
- agent 自己撰寫的訊息（`sender === <該 agent>`）一律不套用
- 門檻維持 400 字元，但不再是唯一判準

### 驗證

- 單元：用該 run 的真實 `conversations.json` 斷言五個 agent 的 Response 全為 plaintext
- 瀏覽器：五個 subagent 面板逐一點開，Response 不得出現加密字樣
- 反向：把規則改回舊版，測試必須紅

---

## 2. 面板分輪

### 輪次定義

| 面板 | 一輪的範圍 |
|---|---|
| `/root` | 一則使用者提問 → 該輪的最終回答 |
| subagent | 一次被交辦 → Task / Thinking / Response |

### 呈現

- **最新的一輪在最上面，且展開**
- 較舊的摺疊成一行：`17:22 · 開五個 agent 分析這個專案的相依套件風險`
- **只有一輪時不做摺疊框**，維持 v0.7.9 的樣子
- subagent 摺疊行的時間，用**它所屬的那個 root 輪次的時間**，不是它自己被交辦的
  時間；這樣 root 與 agent 兩邊的摺疊行可以對應
- 同一天只顯示時間；跨日才補 `08-31` 這樣的日期前綴

### 歸屬規則

每個 subagent 輪次歸到「時間落在哪一個 root 輪次區間」。root 輪次區間 =
該輪提問時間 → 下一輪提問時間（最後一輪到 run 結束）。

### 驗證

- 瀏覽器：兩輪提問的 run，`/root` 面板要有兩個輪次；最新展開、較舊摺疊
- 瀏覽器：展開舊輪次後，該輪的提問與**該輪自己的**回答成對出現
- 瀏覽器：subagent 的摺疊行時間與其所屬 root 輪次相同

---

## 3. 非 agent 節點的面板

目前 process / file / tool_call / network_endpoint 點下去沒有內容。以下**只列現有
資料真的支援的**，不得顯示不存在的欄位。

| 節點 | 顯示 | 資料來源 |
|---|---|---|
| `process` | 指令、執行檔、pid / ppid、出現時間 | `cmdline`、`exe`、`pid`、`ppid`、`create_time` |
| `file` | 檔名、建立 / 修改 / 刪除與各自時間 | 邊的 `event_types`、`first_seen`、`last_seen` |
| `tool_call` | 工具名、時間、輸入欄位名 | `tool_name`、`input_keys`、`tool_use_id` |
| `session` | 啟動指令、工作目錄、backend | `command`、`cwd`、`backend` |
| `network_endpoint` | 位址、首末出現時間、哪個 process 連的 | 節點名與邊 |
| `model` / `tool` / `provider_session` | provider、名稱、session id | 節點屬性 |

### process 的 cmdline 已經含腳本內容

`cmdline` 是逐字擷取的，換行也保留。像

```
['/bin/zsh', '-lc', 'if [[ -n "$ZDOTDIR" ]]; then\n  rc="$ZDOTDIR/.zshrc"\n…']
```

這種 inline 執行，**腳本內容今天就已經在資料裡**，只是沒有顯示。面板要把它完整
呈現（過長時摺疊）。

### tool_call 的內容界線

`collaborationspawn_agent` / `collaborationsend_message` / `collaborationwait_agent`
這類工具，其 input / output **就是 agent 之間的對話本身**。

- **對話路由類工具：不顯示 message 內容**，只說明它是送給哪個 agent 的訊息，
  內容在該 agent 的面板
- **非對話類工具**（如 `webrun`）：顯示 prompt 與 response

理由：v0.7.9 立下「對話屬於 agent，非 agent 節點不得顯示對話」。若 tool_call 面板
照實渲染 input，`collaborationsend_message` 就成為從非 agent 節點讀取 agent 對話的
入口，等於換個門把同一個洞開回來。

### 驗證

- 瀏覽器：點 `collaborationsend_message` 節點，不得出現任何 agent 對話內容
- 瀏覽器：點 `webrun` 節點，看得到查詢與回應
- 瀏覽器：點 process 節點，看得到完整 cmdline

---

## 4. 不可違反

沿用 v0.7.9 的紅線，不因本輪放寬：

1. Live / 完成後 / `viewer.html` 只有一套 renderer。
2. 完成不得 `fetch('/final')`、`document.write()`、替換 DOM。
3. 對話屬於 agent。非 agent 節點不得顯示 agent 對話。
4. 主 Dashboard 不得重新出現 Conversation records、Raw node evidence、
   Show all agents、Open raw conversation evidence、Saved views、Timeline、Filters、
   provider/relation/bytes 之類的來源標註。
5. 加密內容顯示為「已觀測、未公開明文」，不得顯示為「未觀測」。
6. 每一項新契約都要有 Chromium 行為驗證，不得退化成字串比對。

---

## 5. 不在本輪

檔案內容的擷取與 diff 顯示放在 0.8.1，因為它要動收集層。本輪的 file 節點只顯示
建立 / 修改 / 刪除與時間。
