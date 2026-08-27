<!-- i18n-nav:start -->
<p align="center">
  <a href="runtime-threat-model.md">English</a> |
  <a href="runtime-threat-model.zh-TW.md">繁體中文</a> |
  <a href="runtime-threat-model.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="runtime-threat-model.ko.md">한국어</a> |
  <a href="runtime-threat-model.fr.md">Français</a> |
  <a href="runtime-threat-model.de.md">Deutsch</a> |
  <a href="runtime-threat-model.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Runtime 脅威モデルと既知の回避境界

この文書は、ExecWeave v0.6.5 がテスト可能な契約の一部として扱う観測上の限界を定義します。これは**可観測性の脅威モデル**であり、sandbox の安全性保証ではありません。観測対象のコマンドは信頼できない可能性があり、活動を観測しにくくしようとする場合があります。一方、OS カーネルと ExecWeave 自体はカーネルレベルで侵害されていないものとします。

## Portable backend

Portable backend は process/network に psutil snapshot、filesystem 変更に watchdog を使用します。

- **短命 process:** child が 2 回の process sample の間だけ起動・終了すると、完全に見逃す可能性があります。設定された poll interval は blind window の最大値を保証しません。scheduler delay により実際の間隔が長くなることがあります。
- **短命 socket:** 接続が 2 回の socket observation の間だけ存在すると見逃す可能性があります。権限や platform API の制約で socket state が見えない場合もあります。
- **root command より長く生存する descendant:** root observation 終了時に child が生存していても、ExecWeave は偽の exit event を生成しません。ただし portable run は always-on monitor ではなく、その後に生存または reparent された descendant が行う活動は完了済み run の観測範囲外です。
- **Filesystem attribution:** watchdog の変更は session-correlated observation です。意図的に `causal=false` とされ、特定 PID が書き込んだ証拠ではありません。
- **Negative evidence:** portable backend に process/network/filesystem event がないことは、活動が発生しなかった証拠ではありません。

## Linux strace backend

strace backend は `strace -ff` で起動した command の lineage と選択された syscall class を追跡します。

- traced lineage 内では、clone/fork 証拠により portable polling が逃す短命 descendant を保持できます。
- 対応する syscall 証拠がある場合、filesystem/network event を traced process に attribution できます。
- これは **OS-wide visibility ではありません**。traced lineage 外の活動、未対応・未解析 syscall pattern、permission/ptrace 制限、選択した evidence class 外の kernel behavior は対象外です。
- open の read/write access mode は byte-level data flow を証明しません。ExecWeave は後続で実際に読み書きされた内容を主張しません。

## Specialized hooks と direct API integrations

Claude、Codex、Gemini、Cursor、OpenCode、model-runtime、gateway、proxy、direct-API integration は明示された integration point で強い semantic content evidence を提供できますが、provider-hidden state は見えません。

- response-only integration が証明するのは ExecWeave に渡された response fields のみです。
- caller-supplied request+response exchange が証明するのは提供された exchange のみであり、transparent wire interception を意味しません。
- hook coverage は upstream agent/IDE が hook に公開する情報に限定されます。
- full-fidelity storage は integration point で公開された内容を完全保存するという意味であり、model provider や OS 全体を完全観測するという意味ではありません。

## Regression contract

`tests/test_threat_model.py` は次の境界を deterministic executable tests として固定します。

1. 2 回の process sample の間だけ存在する portable child。
2. 2 回の socket sample の間だけ存在する portable socket。
3. root-process observation 終了時に生存する child に偽の exit event を付けないこと。
4. portable filesystem change が session-correlated / non-causal のままであること。
5. 対応する strace trace case が短命 child の `SPAWNED` attribution を保持すること。

テストは「N ミリ秒 sleep して CI がたまたま見逃すことを期待する」timing race を使いません。blind window を observation 間の明示的な状態としてモデル化し、Linux、macOS、Windows で再現可能にします。

## Missing event の意味

Missing event は、その run の canonical evidence に該当 observation が存在しないことだけを意味します。将来の backend が完全な negative-evidence scope を明示し証明しない限り、「発生しなかった」証拠ではありません。Finding severity と evidence fidelity は独立した次元として扱います。
