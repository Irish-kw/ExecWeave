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

**AI Agent があなたのマシン上で実際に何をしたのかを見る。**

ExecWeave は、AI Agent と AI 支援開発ツール向けの local-first observability プロジェクトです。Provider 側のセマンティクスと OS runtime の証拠を 1 つのインタラクティブな Execution Graph に統合しつつ、証拠レイヤーの違いを明示的に保ちます。

> **Event は証拠です。Graph は証拠から materialize された view です。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave live dashboard demo" width="100%">
</p>

## ExecWeave を使う理由

Agent は「ツールを使った」「ファイルを編集した」「サービスへ接続した」と報告できます。これは有用な Provider semantic evidence ですが、OS が実際に観測した事実とは同じではありません。ExecWeave は両方を同じ画面で確認できるようにしながら、異なる強さの証拠を混同しません。

- **Live と Finished を同じ Dashboard で表示。** 実行中、完了後、standalone `viewer.html` が同じ Graph / conversation model を使います。
- **Provider-aware semantics。** Hook、rollout transcript、plugin、runtime API が公開されている場合に利用します。
- **OS runtime evidence。** Process、File、Network endpoint を Provider semantic とは独立に観測できます。
- **Evidence-aware attribution。** Direct observation、exact identity、保守的 inference、causal claim を分離します。
- **Local-first storage。** Run artifacts は自分で共有しない限りローカルに残ります。
- **特定の Agent に限定されません。** 専用 adapter がなくても通常のローカル command を包んで観測できます。

## インストール

PyPI からインストール：

```bash
python -m pip install -U execweave
```

開発用：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## クイックスタート

任意のローカル command を `execweave live` で包みます：

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- python my_agent.py
```

完了済み artifact を主に残したい場合：

```bash
execweave record --open -- python my_agent.py
```

Agent を現在の terminal で対話的に使いながら別の overview を開く場合：

```bash
execweave top -- codex
```

### Provider integration の許可

一部の Agent / IDE は、ローカル hook や plugin を初めて有効にするときに許可を求めます。Prompt、Response、Tool、Model、Conversation などの Provider-level evidence を見たい場合は ExecWeave integration を許可してください。許可しなくても OS runtime 観測は利用できる場合がありますが、semantic coverage は減ります。

Google Antigravity の実際の CLI command は現在 `agy` です。ExecWeave は覚えやすい alias として `antigravity` も受け付けます。

Windows で bare `cursor` を使う場合、ExecWeave はユーザーの PATH が指している Cursor installation を利用します。明示的な launcher path はそのまま尊重されます。

## Ollama

ExecWeave は主に 2 つのローカル Ollama workflow をサポートします。

### Managed server capture

ExecWeave 経由で Ollama server を起動：

```bash
execweave live --open -- ollama serve
```

別 terminal では通常どおり Ollama を使います：

```bash
ollama run deepseek-r1:1.5b
```

SDK、OpenAI-compatible local request、managed local endpoint に送られた `curl` request も同じ ExecWeave run に関連付けられます。2 つ目の terminal を再度 ExecWeave で包む必要はありません。

Managed relay は local loopback endpoint のみに限定され、wildcard や外部公開 listener は書き換えません。

### Direct client capture

Ollama Server が既に動いている場合は client を直接包めます：

```bash
execweave live --open -- ollama run deepseek-r1:1.5b
```

このモードは Ollama Server を起動しないため、到達可能な upstream server が必要です。

## Dashboard

Dashboard は、大規模・multi-agent run でも読みやすさを保ちつつ、元の evidence を変えないことを目的としています。

- **Execution graph:** Agent、Process、File、Network endpoint、Tool、Model/runtime entity、対応 relation。
- **Conversation rounds:** 新旧の round が正しい Agent に残り、後の message で上書きされません。
- **Node details:** Process identity、File history、Network endpoint、Tool、Provider conversation content を確認できます。
- **Stable live updates:** Run の状態が変わっても同じ document 内で更新されます。
- **Large-run folding:** 高 cardinality の node type は古い member を折りたたみつつ検査可能に保ちます。
- **Selection-focused layout:** 選択した Agent / runtime object と無関係な Graph traffic を弱めます。

大規模 run では次を調整できます：

```text
--fold-budget N
--viewer-max-nodes N
--viewer-max-edges N
--viewer-max-dom-elements N
```

## 対応 integration

| Integration | OS runtime 観測 | Specialized evidence |
| --- | --- | --- |
| Claude Code | ExecWeave 配下で起動した場合 | native hooks と Provider supplied conversation/tool content |
| OpenAI Codex | 対応 | lifecycle hooks、validated rollout transcripts、公開される agent/subagent routing |
| Google Antigravity | 対応 | passive hooks と公開される conversation/subagent routing |
| Cursor | 対応 | native hooks と公開される task/subagent routing |
| OpenCode | 対応 | project plugin、session/task routing、supplied plugin content |
| Ollama | 対応 | managed local relay と model-runtime evidence |
| llama.cpp | 対応 | model-runtime event/exchange/probe |
| vLLM | 対応 | model-runtime event/exchange/probe |
| LM Studio | local process を観測できる場合 | model-runtime catalog/runtime evidence |
| LiteLLM Proxy | local proxy を観測できる場合 | gateway metadata / event integration |
| OpenRouter | local client のみ観測可能 | caller-supplied gateway event/exchange evidence |

Tool-call ID、session ID、rollout thread ID、subagent route などの Provider identifier は logical identity であり OS PID ではありません。ExecWeave は証拠が十分な場合だけレイヤー間を接続します。

## Evidence model

ExecWeave は evidence を大きく次のレイヤーに分けます：

```text
Agent / IDE semantics と supplied content
                ↓
Inference gateway / routing evidence
                ↓
Model runtime / inference-server evidence
                ↓
OS runtime evidence: process / file / network
```

Telemetry が因果関係を支える場合だけ relation を causal と扱います。保守的 bridge は derived evidence として明示されます：

```text
inferred: true
causal: false
```

Exact shared request identity は identity を証明できますが causal を証明しません：

```text
identity_exact: true
inferred: false
causal: false
```

Attribution が曖昧なら、ExecWeave は強い relation を推測するのではなく edge を作りません。

### Full-fidelity supplied content

対応 hook、plugin、API が明示的に渡した完全な値は、ローカル SHA-256 content-addressed store に保存できます：

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Integration によっては Prompt、Message、Request/Response object、Tool input/result、Assistant response、公開された reasoning text、Shell output、supplied file content が含まれます。

`complete_from_source: true` は、その integration point が渡した完全な値を保存したことを意味します。公開されていない model state や Provider 内部データを観測したという意味ではありません。

## よく使う command

### Agent / IDE recorder

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateway / model runtime

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` は一方向の event evidence です。`exchange` は caller が提供した request/response pair を保存し、transparent wire interception を主張しません。

### Runtime / Graph / Security / Integrity

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

## Run artifacts

Provider-integrated run には次のようなファイルが含まれます：

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
└── integrity.json
```

Raw observation と derived semantic/correlation output は分離されたままです。

## 制限とプライバシー

- Portable collector は Linux、macOS、Windows で動作します。Portable filesystem observation は常に process-causal ではなく session-correlated で、polling は非常に短い activity を取りこぼすことがあります。
- Linux では `strace` reference backend も利用でき、対応 execution でより強い syscall-attributed evidence を取得できます。
- Provider semantic coverage は各 integration が実際に公開する情報に依存します。未公開 Prompt、hidden reasoning、remote Provider internals、未公開 routing は可靠に再構築できません。
- Full-fidelity content には Credential、Secret、Source code、Prompt、Tool value、Model response、Shell output、File content が含まれる場合があります。
- Conversation isolation は attribution rule であり redaction boundary ではありません。Provider が明示的に route した content は複数 participant に現れる場合があります。
- Local integrity manifest は manifest に対する変更を検出しますが、evidence と manifest が同じ writable trust boundary にある場合、adversary-resistant trusted logging にはなりません。
- 共有前に run directory 全体を確認してください。

## 開発

テスト：

```bash
python -m pytest
```

Lint：

```bash
python -m ruff check .
```

Issue と Pull Request を歓迎します。新しい integration では、直接観測・Provider supplied・derived evidence を明確に区別してください。

## ライセンス

ExecWeave は **PolyForm Noncommercial License 1.0.0** の下で配布されます。詳細は [LICENSE](LICENSE) を参照してください。
