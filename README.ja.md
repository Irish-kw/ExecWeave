# ExecWeave

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

**AI Agent があなたのマシン上で実際に何をしたのかを可視化します。**

ExecWeave は source-available / local-first の observability プロジェクトです。AI Agent の活動をインタラクティブな execution graph に変換し、observed evidence、provider content、derived inference を明確に分離します。

> **Event が ground truth であり、Graph は materialized view です。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## インストール

PyPI から最新の wheel/sdist をインストールします。

```bash
python -m pip install -U execweave
```

現在のリリースは **v0.7.2** です。

開発環境では次のようにインストールできます。

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## クイックスタート

Live OS-runtime telemetry は **任意のローカルコマンド**に利用できます。以下の Agent/runtime 名は例であり、ホワイトリストではありません。

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Hook の許可を求められたら承認してください。** provider integration を初めて使うとき、Agent/IDE が ExecWeave のローカル Hook を有効化してよいか確認する場合があります。**Allow / Yes** を選択してください。承認しなくても OS-runtime telemetry は動作できますが、provider-level の tool、model、supplied-content observability は制限されます。

Google Antigravity の現在の CLI コマンドは `agy` です。ExecWeave は `antigravity` を friendly alias として受け付け、自動的に `agy` に解決します。Cursor の `execweave live --open -- cursor` は、まず通常の PATH launcher を探し、見つからない場合は macOS/Windows の標準 Cursor desktop application binary にフォールバックします。

finalized artifact pipeline を作成する場合：

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` は Agent を起動 terminal 上でインタラクティブなまま保ち、ホスト環境に応じて detached Top dashboard を開くか既存のものに attach します。

**v0.7.2 — provider-neutral かつ agent-local な multi-agent conversation。** ExecWeave は provider が実際に公開した conversation evidence を agent ごとの dashboard thread に投影し、同じ完全 transcript をすべての agent node に複製しません。provider が権威ある identity / routing evidence を公開している場合、parent → child の task assignment、inter-agent message、wait/result、child → parent final response を保持します。Child agent には、その agent が実際に受け取った task と自身の conversation だけを残し、継承された parent history や sibling-private content は除外します。共通 merge layer も provider、raw thread identity、agent identity を組み合わせて scope するため、provider が同じ thread ID を再利用しても Agent 1 と Agent 2 が混ざりません。

統合 dashboard では execution graph、logs、conversation records を同じ inspection flow で確認できます。Finalized run は `conversations.md` と `conversations.json` を生成し、検証済み provider transcript は run-local SHA-256 content store にコピーされます。Claude Code、OpenAI Codex、Cursor、OpenCode、Google Antigravity は、それぞれが実際に公開する最も強い multi-agent evidence を利用します。gateway や local runtime が root request/response しか公開しない場合、ExecWeave は root conversation だけを表示し、subagent や hidden routing を捏造しません。

## v0.6.9：明示的な evidence boundary を持つ full-fidelity observability

v0.6.9 では、コンパクトな metadata だけでなく、対応 integration point が明示的に渡した**完全な値**をローカルの SHA-256 content-addressed store に保存できるようになりました。semantic event stream には reference のみを保持します。

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

adapter と upstream hook/API surface に応じて、prompt/message、model request/response object、tool input/result、assistant response、明示的に公開された reasoning/thinking text、shell/MCP output、provider hook が渡した file content などを保存できます。

`complete_from_source: true` は、その integration point が渡した値を ExecWeave が完全に保存したことだけを意味します。hidden model state、provider-side の非公開 stage、観測していない最終 wire request、取得していない bytes を見たという意味ではありません。

Full fidelity は privacy boundary も変えます。content に application-level secret が含まれていれば、そのまま保存されます。既知の transport credential は adapter が明示的に定義した一部の provider-metadata projection でのみフィルタされます。ExecWeave は汎用 secret scanner や content redactor ではありません。

### 対応している semantic / inference surface

| Integration | ExecWeave 配下で起動した場合の OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity hook content + provider が公開した subagent result |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcript + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + 検証できる場合の conversation/subagent routing |
| Cursor | Yes | native hooks + 利用可能な場合の exact subagent task/summary routing |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | ローカル process を ExecWeave から起動した場合のみ | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 設定済み proxy を ExecWeave から起動した場合は Yes | metadata-oriented gateway callback/event integration |
| OpenRouter | remote service process ではなくローカル client を観測 | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` は caller-supplied request+response evidence であり、transparent wire interception ではありません。LiteLLM Proxy は現行 baseline ではより限定的な metadata-oriented integration です。Provider-neutral conversation projection は、存在しない provider evidence を架空の agent relationship に昇格させません。

## Evidence layers

ExecWeave はすべての信号を一つの trace に潰さず、evidence layer を分離して保持します。

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

relationship を causal とするのは、基礎 telemetry がその claim を支持する場合だけです。Tool → Process bridge は保守的な derived evidence のままです。

```text
inferred: true
causal: false
```

曖昧な場合は edge を作りません。Gateway と Model Runtime 間の exact shared request identity も、causal evidence ではなく identity evidence として扱います。

```text
identity_exact: true
inferred: false
causal: false
```

## Agent / IDE integrations

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude

execweave-codex-hook --print-config
execweave-codex-record --open -- codex

execweave-antigravity-hook --print-config
execweave-antigravity-record --open -- antigravity

execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor

execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Provider-integrated recorder は raw runtime、semantic、correlated、conversation artifacts を分離して保存します。Cursor `tool_use_id`、Codex rollout thread identity、OpenCode `sessionID + callID` のような stable provider identifier は provider 内部の logical identity を示しますが、OS PID ではありません。cross-agent content は provider が明示的に route、delegation、result を公開した場合にのみ表示されます。Legacy Gemini CLI hook entry point は既存環境との互換性のため残っていますが、新しい Google CLI 利用では Antigravity (`agy`) を推奨します。

## Inference gateway と model runtime

OpenRouter または LiteLLM gateway evidence を取得します。

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Ollama、llama.cpp、vLLM、LM Studio の model-runtime evidence を取得します。

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` は response-only evidence です。`exchange` は caller-supplied request+response object を保存しますが、transparent interception を主張しません。Runtime catalog relation の意味は source ごとに保持され、`LOADED_MODEL`、`SERVES_MODEL`、`ADVERTISES_MODEL` は交換可能ではありません。LM Studio の catalog visibility が `ADVERTISES_MODEL` でも、weights が memory resident だったことの証明にはなりません。

## Security analysis、evidence grades、bounded rule packs

組み込み analysis を実行します。

```bash
execweave analyze run.graph.json --output analysis.json
```

Finding は severity と独立した evidence grade を持ちます。現在の grade は `A`、`B`、`C`、`D`、`U` で、直接 syscall attribution から inferred/unknown provenance までを表します。これは probability や trust score ではありません。

Local rule pack は第三者コードを実行せず、bounded で説明可能な**single-edge observation** policy を追加できます。

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule pack は code を実行できず、regex/path program を定義できず、byte-level data flow や exfiltration を断定できません。rule-pack finding は observation-only のままです。

Security finding は強い claim をしないことも明示します。

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

完了した run を seal し、後から regular-file inventory が seal 時点から変わっていないか検証できます。

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Deterministic manifest は file size/SHA-256 を記録し、symbolic link を拒否します。seal 後に regular file が欠落、変更、置換、追加されると検証に失敗します。

この local seal は、evidence と manifest が同じ writable trust boundary にある場合、adversary-resistant tamper evidence とは説明しません。Manifest は `malicious_writer_resistance: false` と `external_trust_anchor: false` を記録します。より強い trust anchor が必要なら manifest digest を boundary の外へコピー・保護してください。

## Runtime evidence と graph operations

Portable collector は Linux、macOS、Windows で動作します。Linux には syscall-backed `strace` reference backend もあります。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation は session-correlated であり process-causal ではありません。polling は十分短い活動を見逃す可能性があります。Linux `strace` は対応 execution でより強い process-attributed syscall evidence を提供します。Linux eBPF、Windows ETW、macOS Endpoint Security の native collector は今後の計画です。

## Performance と large-run safety

ExecWeave には bounded filesystem/viewer protection、incremental Live JSONL tailing、large-graph safety guard、detached Top、設定済み provider integration 用の provisional live sidecar が含まれます。

再現可能な incremental `GraphAccumulator` reference result は、文書化された GitHub Actions workload の 1M synthetic events で **164,273 ev/s** に達します。これは graph accumulation benchmark であり、end-to-end collector/browser throughput ではありません。

代表的な host/workload で package-level overhead benchmark を再実行してください。

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data と methodology は [`docs/benchmarks/`](docs/benchmarks/) を参照してください。

## Layered artifacts

Provider-integrated run には次のような artifact が含まれる場合があります。

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── conversations.md
├── conversations.json
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
├── viewer.correlated.html
└── integrity.json            # explicit seal 後
```

Derived correlation は raw runtime や provider sidecar evidence を書き換えません。

## Privacy

ExecWeave は local-first で、capture、content blob、graph、report、viewer は既定でローカルに残ります。**OS runtime collector** は file content や raw read/write byte buffer を意図的には収集しません。ただし、この boundary と v0.6.9 で導入された **provider full-fidelity content store** を混同しないでください。対応 hook/API が prompt、tool argument/result、model response、reasoning/thinking text、shell output、file content などを明示的に渡した場合、ExecWeave はその値を完全に保存できます。

Conversation isolation は attribution/display の規則であり redaction boundary ではありません。provider が Agent 1 の内容を Agent 2 に明示的に送れば、その routed evidence は参加 endpoint に表示され得ます。content が secret-redacted 済みだと仮定しないでください。Command、path、endpoint metadata、identifier、model metadata、prompt、tool value、content blob はすべて機密情報になり得ます。共有前に run directory 全体を確認してください。

## 現在の状態

v0.7.2 は cross-platform runtime collection、materialized execution graph、standalone/live dashboard、保守的な provider↔runtime correlation、content-addressed full-fidelity provider evidence、attributable multi-agent execution trace、run-local conversation access、provider-neutral projection 上の agent-local conversation isolation を統合します。各 integration は provider が実際に公開した最も強い identity/routing evidence のみを保持し、不足する場合は abstain します。Observed evidence と inference は設計上分離されたままです。

## ドキュメント

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ja.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ja.md)
- [`Live Graph`](docs/live-graph.ja.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ja.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ja.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ja.md)
- [`Google Antigravity Hooks`](docs/antigravity-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.ja.md)
- [`OpenCode Plugin`](docs/opencode-plugin.ja.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.ja.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.ja.md)
- [`Runtime Threat Model`](docs/runtime-threat-model.ja.md)
- [`Evidence Grades`](docs/evidence-grades.ja.md)
- [`Rule Packs`](docs/rule-packs.ja.md)
- [`Run Integrity`](docs/run-integrity.ja.md)
- [`Security Analysis`](docs/security-analysis.ja.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## コントリビューション

native OS collector、Agent/IDE adapter、inference gateway、model runtime、evidence/correlation method、privacy/redaction、graph UX、multi-agent conversation attribution、performance evaluation への contribution を歓迎します。

## License

v0.6.8 以降、ExecWeave は **PolyForm Noncommercial License 1.0.0** で提供されます。非商用での利用、変更、再配布はライセンス条件の範囲で許可されます。商用利用には licensor から別途書面による commercial license が必要です。詳細は [`LICENSE`](LICENSE) を参照してください。
