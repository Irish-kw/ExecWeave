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

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**AI Agent があなたのマシン上で実際に何をしたのかを可視化します。**

ExecWeave は source-available / local-first の observability プロジェクトです。AI Agent の活動をインタラクティブな execution graph に変換し、observed evidence、provider が明示的に供給した content、derived inference を明確に分離します。

> **Event が ground truth であり、Graph は materialized view です。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

この README は **v0.8.6** を説明します。

## ExecWeave を使う理由

- **ローカルの inspection surface を 1 つに統合。** Live run、完了済み run、standalone `viewer.html` は同じ dashboard renderer を使い、graph、logs、conversation、node details を 1 画面にまとめます。
- **Evidence-aware な設計。** Direct observation、identity link、保守的な inference、causal claim を同じ意味の edge として扱いません。
- **Provider-aware だが、隠れた挙動を作らない。** Provider が実際に公開した routing / identity evidence だけを使い、存在しない evidence を補完しません。
- **特定の Agent 専用ではない。** OS-runtime telemetry は任意のローカル command を包めます。対応 provider adapter がある場合は、より豊かな semantic evidence を追加します。

## インストール

PyPI から最新の公開済み package をインストールします。

```bash
python -m pip install -U execweave
```

開発用インストール：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 60 秒クイックスタート

Live OS-runtime telemetry は**任意のローカル command**で利用できます。以下の Agent/runtime 名は例であり whitelist ではありません。

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Hook の許可を求められたら承認してください。** 初回の provider-integrated run では、Agent/IDE が ExecWeave のローカル Hook integration を有効にしてよいか確認することがあります。**Allow / Yes** を選んでください。許可しなくても OS-runtime telemetry は動作する場合がありますが、provider-level の tool、model、conversation、supplied-content observability は低下または利用不可になります。

Google Antigravity の現在の CLI command は `agy` です。ExecWeave は friendly alias として `antigravity` も受け付け、`agy` に解決します。Cursor の `execweave live --open -- cursor` は、まず通常の PATH launcher を探し、見つからない場合は macOS / Windows の標準 Cursor desktop application binary を試します。

Finalized run artifacts を作るには：

```bash
execweave record --open -- python my_agent.py
```

Agent を起動 terminal で対話可能なまま、detached overview を開くには：

```bash
execweave top -- codex
```

## Dashboard

ExecWeave は run 終了時に別の viewer へ切り替えません。Live、finished、standalone viewing は同じ dashboard model を使います。

- **Execution graph：** agents、processes、files、network endpoints、tools、model/runtime entities、および対応 semantic relations を表示します。
- **Conversation rounds：** 最新 round はすぐ読め、古い round も個別に展開できます。新しい reply に上書きされません。
- **Node details：** process node は command / PID context、file node は path / history context、network node は endpoint / process context を表示します。
- **Large-run readability：** type ごとの予算を超えた場合、最近の member はそのまま表示し、古い member は inspection 可能な aggregate にまとめます。閾値は `--fold-budget N` で設定します。
- **Selection clarity：** multi-agent layout は安定した root / child hierarchy を維持し、agent 選択時には無関係な edges を薄く表示します。

### v0.8.3 Dashboard の変更点

v0.8.3 は raw evidence を変えずに、dense / multi-round run の読みやすさを改善します。

- conversation panel を round 単位にし、古い prompt と新しい reply の誤った組み合わせを防止；
- ユーザーが明示的に設定した open / closed state を 800 ms の Live refresh 後も保持；
- subagent response を実際に生成した agent に帰属したまま維持；
- process、file、network を選択した際の空の detail panel を解消；
- 高 cardinality の node type を設定可能な予算で fold し、数百・数千 node が graph を埋め尽くすのを防止；
- lifecycle return edge が root / child rank を歪めないようにし、共有 tool/model traffic の routed geometry を明確化。

これらは presentation-layer の変更です。Raw graph evidence は変わらず、Live、finished、`viewer.html` は引き続き同じ renderer を共有します。

## 対応 Integrations

| Integration | ExecWeave 配下で起動した場合の OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content + provider が公開した場合の exact subagent results |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + 検証可能な場合の conversation/subagent routing |
| Cursor | Yes | native hooks + 利用可能な場合の exact subagent task/summary routing |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | ローカル process を ExecWeave 配下で起動した場合のみ | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 設定済み proxy を ExecWeave 配下で起動した場合は Yes | metadata-oriented gateway callback/event integration |
| OpenRouter | remote service process ではなくローカル client を観測 | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

Cursor `tool_use_id`、Codex rollout thread identity、OpenCode `sessionID + callID` のような stable provider identifier は logical provider identity を示しますが、OS PID ではありません。Cross-agent content は provider が明示的な route、delegation、result を公開した場合にのみ表示されます。Gateway / local runtime が root request/response しか公開しない場合は root-only のままで、ExecWeave が subagent や hidden routing を作ることはありません。

OpenRouter `exchange` は caller-supplied request+response evidence であり、transparent wire interception ではありません。LiteLLM Proxy は現在の baseline ではより限定的な metadata-oriented integration です。Legacy Gemini CLI entry points は互換性のため残っていますが、新しい Google CLI 利用では Antigravity (`agy`) を使用してください。

## Evidence model

ExecWeave はすべての signal を 1 本の trace に平坦化せず、evidence layer の境界を保ちます。

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Relationship を causal とするのは、下位 telemetry がその claim を実際に支える場合だけです。保守的な Tool → Process bridge は derived evidence としてマークされます。

```text
inferred: true
causal: false
```

Gateway と Model Runtime が exact shared request identity を持つことは identity evidence であり、causal evidence ではありません。

```text
identity_exact: true
inferred: false
causal: false
```

曖昧な場合は edge を作りません。

### Full-fidelity supplied content

**v0.6.9** 以降、対応 integration point は provider / hook / API が明示的に渡した完全な値をローカル SHA-256 content-addressed store に保存し、semantic event stream には reference だけを残せます。

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Integration に応じて、prompt/message、request/response object、tool input/result、assistant response、明示的に公開された reasoning/thinking text、shell/MCP output、provider hook が提供した file content などを保存できます。

`complete_from_source: true` は、その integration point から渡された値を完全に保存したことだけを意味します。Hidden model state、公開されていない provider-side stage、観測していない final wire request、intercept していない bytes を見たという意味では**ありません**。

## よく使うコマンド

### Agent / IDE recorders

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateways と model runtimes

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl

execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` は response-only evidence です。`exchange` は caller-supplied request+response object を保存しますが transparent interception を主張しません。Runtime catalog relation は source-specific な意味を維持し、`LOADED_MODEL`、`SERVES_MODEL`、`ADVERTISES_MODEL` は相互に置き換えられません。LM Studio の catalog visibility は `ADVERTISES_MODEL` であり、weights が memory に resident していた証明ではありません。

### Runtime、graph、security、integrity

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave analyze run.graph.json --output analysis.json
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Security finding の evidence grade は severity とは独立しています。現在の grade は `A`、`B`、`C`、`D`、`U` で、probability や trust score ではなく evidence-strength category です。Rule pack は bounded / explainable な single-edge observation policy であり、third-party code を実行せず、byte-level exfiltration を証明することもできません。

## Run artifacts

Provider-integrated run には次のような artifact が含まれます。

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
└── integrity.json            # after an explicit seal
```

Derived correlation が raw runtime や provider sidecar evidence を書き換えることはありません。

## 制限とプライバシー

- Portable collector は Linux、macOS、Windows で動作します。Portable filesystem observation は session-correlated であって process-causal ではなく、polling は非常に短い activity を取りこぼす場合があります。
- Linux には syscall-backed `strace` reference backend もあり、対応 execution ではより強い process-attributed syscall evidence を得られます。
- Native Linux eBPF、Windows ETW、macOS Endpoint Security collector は planned work であり、現在の能力としては主張していません。
- Full-fidelity provider content は prompt、tool value、model response、shell output、supplied file に含まれる secret も保存し得ます。ExecWeave は汎用 secret scanner / content redactor では**ありません**。
- Conversation isolation は attribution/display rule であり redaction boundary ではありません。Provider が content を他 agent へ明示的に route した場合、参加 endpoint にその content が表示されるのは正当です。
- Commands、paths、endpoints、identifiers、model metadata、prompts、tool values、content blobs はすべて sensitive になり得ます。共有前に run directory 全体を確認してください。
- Local integrity seal は manifest に対する file change を検出できますが、evidence と manifest が同じ writable trust boundary にある場合、adversary-resistant tamper evidence とは表現できません。

## パフォーマンス

ExecWeave には bounded filesystem/viewer protection、incremental Live JSONL tailing、large-graph safety guard、detached Top、設定済み provider integration 用の provisional live sidecar が含まれます。

再現可能な incremental `GraphAccumulator` reference result は、文書化された GitHub Actions workload の 1M synthetic events で **164,273 ev/s** に達します。これは graph-accumulation benchmark であり、end-to-end collector / browser throughput ではありません。

代表的な host/workload で package-level benchmark を実行してください。

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data と methodology は [`docs/benchmarks/`](docs/benchmarks/) にあります。

## ドキュメント

| 分野 | ドキュメント |
| --- | --- |
| Runtime と graph | [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md) · [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md) · [`Live Graph`](docs/live-graph.md) · [`Semantic Telemetry`](docs/semantic-telemetry.md) |
| Agent / IDE integrations | [`Claude Code`](docs/claude-code-hooks.md) · [`OpenAI Codex`](docs/codex-hooks.md) · [`Google Antigravity`](docs/antigravity-hooks.md) · [`Cursor`](docs/cursor-hooks.md) · [`OpenCode`](docs/opencode-plugin.md) |
| Gateways と runtimes | [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md) · [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md) |
| Trust と analysis | [`Runtime Threat Model`](docs/runtime-threat-model.md) · [`Evidence Grades`](docs/evidence-grades.md) · [`Rule Packs`](docs/rule-packs.md) · [`Run Integrity`](docs/run-integrity.md) · [`Security Analysis`](docs/security-analysis.md) |
| Performance | [`Benchmarks`](docs/benchmarks/README.md) |

## コントリビューション

Native OS collector、Agent/IDE adapter、inference gateway、model runtime、evidence/correlation method、privacy/redaction、graph UX、multi-agent conversation attribution、performance evaluation への貢献を歓迎します。

## ライセンス

v0.6.8 以降、ExecWeave は **PolyForm Noncommercial License 1.0.0** の下で提供されます。非商用の利用・変更・再配布はライセンス条件に従って許可されます。商用利用には licensor との別途の書面 commercial license が必要です。詳しくは [`LICENSE`](LICENSE) を参照してください。
