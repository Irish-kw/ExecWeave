> Codex + AGY и остальные поддерживаемые провайдеры теперь согласованы по conversation history, dashboard graph, raw events и file targets.

# ExecWeave

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**Узнайте, что AI Agent действительно делает на вашей машине.**

ExecWeave — source-available, local-first проект наблюдаемости, который превращает активность AI Agent в интерактивный execution graph и явно разделяет observed evidence, явно предоставленный provider content и derived inference.

> **Event — это ground truth. Graph — materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

Этот README описывает **v0.8.9**.

## Почему ExecWeave

- **Единая локальная inspection surface.** Live runs, завершённые runs и standalone `viewer.html` используют один dashboard renderer для graph, logs, conversations и node details.
- **Evidence-aware by design.** Direct observations, identity links, консервативные inference и causal claims остаются различимыми, а не превращаются в один тип связи.
- **Provider-aware без выдумывания скрытого поведения.** ExecWeave использует только routing / identity evidence, которые provider действительно раскрывает; отсутствующая evidence остаётся отсутствующей.
- **Не привязан к одному Agent.** OS-runtime telemetry может оборачивать любую локальную command, а поддерживаемые provider adapters добавляют более богатую semantic evidence.

## Установка

Установите последний опубликованный package из PyPI:

```bash
python -m pip install -U execweave
```

Для разработки:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Быстрый старт за 60 секунд

Live OS-runtime telemetry работает с **любой локальной command**. Названия Agent/runtime ниже — примеры, а не whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Разрешите Hook, когда появится запрос.** При первом provider-integrated run Agent/IDE может спросить, разрешено ли ExecWeave включить локальную Hook integration. Выберите **Allow / Yes**. Без разрешения OS-runtime telemetry всё ещё может работать, но provider-level observability для tools, models, conversations и supplied content может быть ограничена или недоступна.

Google Antigravity сейчас использует CLI command `agy`. ExecWeave также принимает `antigravity` как friendly alias и разрешает его в `agy`. Для Cursor команда `execweave live --open -- cursor` сначала ищет обычный PATH launcher, а затем при необходимости использует стандартный binary desktop-приложения Cursor на macOS и Windows.

Чтобы создать finalized run artifacts:

```bash
execweave record --open -- python my_agent.py
```

Чтобы Agent оставался интерактивным в стартовом terminal, а overview была открыта отдельно:

```bash
execweave top -- codex
```

## Dashboard

ExecWeave не переключается на другой viewer после завершения run. Live, finished и standalone viewing используют одну dashboard model.

- **Execution graph:** показывает agents, processes, files, network endpoints, tools, model/runtime entities и поддерживаемые semantic relations.
- **Conversation rounds:** самый новый round сразу доступен для чтения; старые rounds остаются доступны по отдельности и не перезаписываются новыми replies.
- **Node details:** process nodes показывают command / PID context, file nodes — path / history context, network nodes — endpoint / process context.
- **Large-run readability:** если тип превышает свой бюджет, новые members остаются видимыми, а старые сворачиваются в inspectable aggregate. Порог задаётся через `--fold-budget N`.
- **Selection clarity:** multi-agent layout сохраняет стабильную root / child hierarchy и приглушает несвязанные edges при выборе Agent.

### Изменения Dashboard в v0.8.3

v0.8.3 улучшает читаемость плотных и multi-round runs без изменения raw evidence:

- conversation panels стали round-based и больше не связывают старый prompt с новой reply;
- явно выбранный пользователем open / closed state сохраняется после 800-ms Live refresh;
- subagent responses остаются приписаны Agent, который действительно их создал;
- выбор process, file или network больше не открывает пустой detail panel;
- node types с высокой cardinality сворачиваются по настраиваемому бюджету, а не заполняют graph сотнями или тысячами nodes;
- lifecycle return edges больше не искажают root / child rank, а shared tool/model traffic использует более понятную routed geometry.

Это изменения только presentation layer. Raw graph evidence не меняется, а Live, finished и `viewer.html` по-прежнему используют один renderer.

## Поддерживаемые integrations

| Integration | OS-runtime observation при запуске под ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content + exact subagent results, когда provider их раскрывает |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + conversation/subagent routing, когда его можно валидировать |
| Cursor | Yes | native hooks + exact subagent task/summary routing, когда он доступен |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | Только когда локальный process запущен под ExecWeave | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes, когда настроенный proxy запущен под ExecWeave | metadata-oriented gateway callback/event integration |
| OpenRouter | Наблюдает локальный client, а не remote service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

Stable provider identifiers вроде Cursor `tool_use_id`, Codex rollout thread identity или OpenCode `sessionID + callID` доказывают logical provider identity, но не являются OS PID. Cross-agent content показывается только тогда, когда provider раскрывает явную route, delegation или result. Gateways и local runtimes, которые предоставляют только root request/response traffic, остаются root-only; ExecWeave не выдумывает subagents или hidden routing.

OpenRouter `exchange` — caller-supplied request+response evidence, а не transparent wire interception. LiteLLM Proxy остаётся более узкой metadata-oriented integration в текущем baseline. Для новых сценариев Google CLI следует использовать Antigravity (`agy`).

## Evidence model

ExecWeave сохраняет evidence layers раздельными, а не сплющивает все сигналы в одну trace:

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Relationship считается causal только тогда, когда underlying telemetry действительно поддерживает этот claim. Консервативные Tool → Process bridges остаются помеченными как derived evidence:

```text
inferred: true
causal: false
```

Exact shared request identity между Gateway и Model Runtime — это identity evidence, а не causal evidence:

```text
identity_exact: true
inferred: false
causal: false
```

При неоднозначности edge не создаётся.

### Full-fidelity supplied content

Начиная с **v0.6.9**, поддерживаемые integration points могут сохранять полное значение, явно предоставленное provider / hook / API, в локальном SHA-256 content-addressed store, тогда как semantic event stream хранит только reference:

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

В зависимости от integration могут сохраняться prompt/message, request/response objects, tool input/result, assistant response, явно раскрытый reasoning/thinking text, shell/MCP output и file content, предоставленный provider hooks.

`complete_from_source: true` означает только то, что ExecWeave сохранил полное значение, переданное этим integration point. Это **не означает**, что ExecWeave видел hidden model state, никогда не раскрытые provider-side stages, ненаблюдаемую final wire request или bytes, которые он не interceptировал.

## Часто используемые команды

### Agent / IDE recorders

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateways и model runtimes

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl

execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` — response-only evidence. `exchange` сохраняет caller-supplied request+response object и не утверждает наличие transparent interception. Runtime catalog relations сохраняют source-specific смысл: `LOADED_MODEL`, `SERVES_MODEL` и `ADVERTISES_MODEL` не взаимозаменяемы. LM Studio catalog visibility остаётся `ADVERTISES_MODEL` и не доказывает, что weights были resident in memory.

### Runtime, graph, security и integrity

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

Evidence grade security finding независим от severity. Текущие grades: `A`, `B`, `C`, `D` и `U`; это evidence-strength categories, а не probabilities или trust scores. Rule packs — bounded, explainable single-edge observation policies; они не выполняют third-party code и не доказывают byte-level exfiltration.

## Run artifacts

Provider-integrated run может содержать:

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

Derived correlation никогда не переписывает raw runtime или provider sidecar evidence.

## Ограничения и конфиденциальность

- Portable collector работает в Linux, macOS и Windows. Portable filesystem observation является session-correlated, а не process-causal, и polling может пропускать достаточно короткоживущую activity.
- В Linux также есть syscall-backed reference backend `strace`, который даёт более сильную process-attributed syscall evidence для поддерживаемых executions.
- Native collectors для Linux eBPF, Windows ETW и macOS Endpoint Security остаются planned work, а не текущей заявленной возможностью.
- Full-fidelity provider content может сохранять secrets, встроенные в prompts, tool values, model responses, shell output или supplied files. ExecWeave **не является** универсальным secret scanner или content redactor.
- Conversation isolation — это attribution/display rule, а не redaction boundary. Если provider явно route-ит content между agents, этот content может законно появляться у участвующих endpoints.
- Commands, paths, endpoints, identifiers, model metadata, prompts, tool values и content blobs могут быть чувствительными. Перед публикацией проверьте весь run directory.
- Local integrity seal обнаруживает изменения файлов относительно своего manifest, но не является adversary-resistant, если evidence и manifest остаются внутри одной writable trust boundary.

## Производительность

ExecWeave включает bounded filesystem/viewer protections, incremental Live JSONL tailing, large-graph safety guards, detached Top и provisional live sidecars для настроенных provider integrations.

Воспроизводимый reference result инкрементального `GraphAccumulator` достигает **164,273 ev/s** на 1M synthetic events в документированном GitHub Actions workload. Это graph-accumulation benchmark, а не end-to-end collector/browser throughput.

Запускайте package-level benchmarks на репрезентативном host/workload:

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data и methodology находятся в [`docs/benchmarks/`](docs/benchmarks/).

## Документация

| Область | Документы |
| --- | --- |
| Runtime и graph | [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md) · [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md) · [`Live Graph`](docs/live-graph.md) · [`Semantic Telemetry`](docs/semantic-telemetry.md) |
| Agent / IDE integrations | [`Claude Code`](docs/claude-code-hooks.md) · [`OpenAI Codex`](docs/codex-hooks.md) · [`Google Antigravity`](docs/antigravity-hooks.md) · [`Cursor`](docs/cursor-hooks.md) · [`OpenCode`](docs/opencode-plugin.md) |
| Gateways и runtimes | [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md) · [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md) |
| Trust и analysis | [`Runtime Threat Model`](docs/runtime-threat-model.md) · [`Evidence Grades`](docs/evidence-grades.md) · [`Rule Packs`](docs/rule-packs.md) · [`Run Integrity`](docs/run-integrity.md) · [`Security Analysis`](docs/security-analysis.md) |
| Performance | [`Benchmarks`](docs/benchmarks/README.md) |

## Вклад

Приветствуются contributions, особенно в native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, evidence/correlation methods, privacy/redaction, graph UX, multi-agent conversation attribution и performance evaluation.

## Лицензия

Начиная с v0.6.8, ExecWeave распространяется по **PolyForm Noncommercial License 1.0.0**. Некоммерческое использование, изменение и распространение разрешены на её условиях. Коммерческое использование требует отдельной письменной commercial license от licensor. См. [`LICENSE`](LICENSE).
