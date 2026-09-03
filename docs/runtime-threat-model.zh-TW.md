<!-- i18n-nav:start -->
<p align="center">
  <a href="runtime-threat-model.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="runtime-threat-model.zh-CN.md">简体中文</a> |
  <a href="runtime-threat-model.ja.md">日本語</a> |
  <a href="runtime-threat-model.ko.md">한국어</a> |
  <a href="runtime-threat-model.fr.md">Français</a> |
  <a href="runtime-threat-model.de.md">Deutsch</a> |
  <a href="runtime-threat-model.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Runtime 威脅模型與已知規避邊界

本文件定義 ExecWeave v0.6.5 視為可測試契約的一部分之觀測限制。這是**可觀測性威脅模型**，不是 sandbox 安全保證：被觀測的命令可以是不受信任的，也可能刻意讓活動難以被觀測；但假設作業系統核心與 ExecWeave 安裝本身未遭核心層級攻陷。

## Portable backend

Portable backend 使用 psutil snapshot 觀測 process/network，並使用 watchdog 觀測 filesystem 變化。

- **短生命週期 process：** 若 child 在兩次 process sample 之間啟動並結束，可能完全漏掉。設定的 poll interval 也不是 blind window 的保證上限，因 scheduler delay 可能讓實際間隔更長。
- **短生命週期 socket：** 若連線在兩次 socket observation 之間建立又消失，可能漏掉；權限或平台 API 限制也可能隱藏 socket state。
- **比 root command 活得更久的 descendant：** 當 root observation 結束時，若 child 仍存活，ExecWeave 不會捏造 exit event；但 portable run 並不是 always-on monitor。之後仍存活或被 reparent 的 descendant 所做活動，已超出該完成 run 的觀測時間窗。
- **Filesystem attribution：** watchdog 事件是 session-correlated observation，刻意標為 `causal=false`，不能當作某個 PID 寫入檔案的證明。
- **Negative evidence：** portable backend 沒有 process/network/filesystem event，不能解讀成該活動沒有發生。

## Linux strace backend

strace backend 以 `strace -ff` 追蹤被啟動 command 的 lineage 與選定 syscall 類別。

- 在該 traced lineage 內，clone/fork 證據可保留 portable polling 可能漏掉的短命 descendant。
- 有支援的 syscall 證據時，filesystem 與 network event 可以 attribution 到被 trace 的 process。
- 這**不是 OS-wide visibility**。trace lineage 之外的活動、未支援或未解析的 syscall pattern、permission/ptrace 限制，以及選定 evidence class 之外的 kernel behavior 都不在此能力聲明內。
- open 的 read/write access mode 不等於 byte-level data flow；ExecWeave 不宣稱知道 process 後續實際讀寫的內容。

## Specialized hooks 與 direct API integrations

Claude、Codex、Antigravity、Cursor、OpenCode、model-runtime、gateway、proxy 與 direct-API integration 可以在明確 integration point 提供更強的 semantic content evidence，但不會揭露 provider-hidden state。

- response-only integration 只能證明提供給 ExecWeave 的 response fields。
- caller-supplied request+response exchange 只能證明該份被提供的 exchange；不能宣稱為 transparent wire interception。
- hook coverage 受 upstream agent/IDE 實際暴露給 hook 的資料限制。
- full-fidelity storage 的意思是完整保存 integration point 實際暴露的內容，不代表完整看見 model provider 或 operating system 的所有狀態。

## Regression contract

`tests/test_threat_model.py` 以 deterministic executable tests 鎖住下列邊界：

1. 只存在於兩次 process sample 之間的 portable child；
2. 只存在於兩次 socket sample 之間的 portable socket；
3. root-process observation 結束時仍存活的 child，不捏造 exit event；
4. portable filesystem change 仍為 session-correlated、non-causal；
5. 對應的 strace trace case 能為短命 child 保留 `SPAWNED` attribution。

測試刻意不採用「sleep N 毫秒，希望 CI 剛好漏掉」這種 timing race，而是把 blind window 建模成兩次 observation 之間的明確狀態，因此可在 Linux、macOS、Windows 重現。

## Missing event 代表什麼

Missing event 只代表該 run 的 canonical evidence 中沒有這項 observation。在未來某個 backend 明確定義並證明完整的 negative-evidence scope 之前，它不是「事件沒有發生」的證據。Finding severity 與 evidence fidelity 必須維持為兩個獨立維度。
