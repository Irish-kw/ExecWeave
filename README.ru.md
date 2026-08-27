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

**Посмотрите, что ИИ-агенты действительно делают на вашей машине.**

ExecWeave — source-available, local-first проект observability, который преобразует активность ИИ-агентов в интерактивный execution graph и при этом явно разделяет observed evidence, provider content и derived inference. Начиная с v0.6.8 проект распространяется по PolyForm Noncommercial 1.0.0; коммерческое использование не разрешено.

> **Event — это ground truth. Graph — materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## Установка

Установите последний опубликованный wheel/sdist из PyPI:

```bash
python -m pip install -U execweave
```

Версия package в `main` сейчас **v0.6.9**. Опубликованный release может отставать от main; чтобы протестировать текущий mainline напрямую:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

Для разработки:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Быстрый старт

Live OS-runtime telemetry работает с **любой локальной командой**. Имена Agent/runtime ниже — лишь примеры, а не whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Разрешите Hook, когда появится запрос.** При первом provider-integrated run Agent/IDE может спросить, разрешено ли ExecWeave включить локальную Hook integration. Выберите **Allow / Yes**. Без разрешения OS-runtime telemetry может продолжить работать, но provider-level observability tools, models и supplied content будет ограничена или недоступна.

Google Antigravity сейчас использует CLI `agy`; ExecWeave также принимает `antigravity` как friendly alias и разрешает его в `agy`. Для Cursor команда `execweave live --open -- cursor` сначала использует PATH launcher, а при его отсутствии на macOS/Windows переходит к стандартному binary Cursor desktop application.

Или создайте finalized artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` оставляет Agent интерактивным в терминале запуска и открывает либо подключает detached Top dashboard в зависимости от среды хоста.

## v0.6.9: full-fidelity observability с явными evidence boundaries

v0.6.9 расширяет observability за пределы компактных metadata. Если поддерживаемая integration point явно предоставляет content, ExecWeave может сохранить **полное значение, предоставленное этим источником**, в локальном SHA-256 content-addressed store, оставляя в semantic event stream только reference.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

В зависимости от adapter и upstream hook/API surface могут сохраняться prompts/messages, model request/response objects, tool input/results, явно раскрытый reasoning/thinking text, shell/MCP output и file content, предоставленный provider hooks.

`complete_from_source: true` означает только то, что ExecWeave сохранил полное значение, переданное этой integration point. Это **не означает**, что ExecWeave наблюдал hidden model state, нераскрытые provider stages, невидимый финальный wire request или байты, которые не были перехвачены.

Full fidelity также меняет privacy boundary: application-level secrets, встроенные в content, сохраняются. Известные transport credentials фильтруются только в отдельных provider-metadata projections, где adapter явно задаёт такое поведение. ExecWeave **не является** универсальным secret scanner или content redactor.

### Поддерживаемые semantic / inference surfaces

| Integration | OS-runtime observation при запуске под ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity content, предоставленный hook |
| OpenAI Codex | Yes | lifecycle hooks + full-fidelity content, предоставленный hook |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks for invocation/tool evidence + full-fidelity values explicitly supplied to those hooks |
| Cursor | Yes | native hooks + full-fidelity content, предоставленный hook |
| OpenCode | Yes | project plugin + full-fidelity content, предоставленный plugin |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | только если локальный process запущен ExecWeave | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes, если настроенный proxy запущен под ExecWeave | текущая metadata-oriented gateway callback/event integration |
| OpenRouter | наблюдается локальный client, а не process удалённого сервиса | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` — это caller-supplied request+response evidence, а не transparent wire interception. LiteLLM Proxy в текущей baseline остаётся более узкой metadata-oriented integration.

## Evidence layers

ExecWeave сохраняет evidence layers раздельно, а не сводит все сигналы в одну trace:

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Relationship считается causal только если underlying telemetry действительно поддерживает такой claim. Tool → Process bridges остаются консервативными derived evidence:

```text
inferred: true
causal: false
```

При неоднозначности edge не создаётся. Exact shared request identity между Gateway и Model Runtime остаётся identity evidence, а не causal evidence:

```text
identity_exact: true
inferred: false
causal: false
```

## Интеграции Agent / IDE

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

Provider-integrated recorders сохраняют raw runtime, semantic и correlated artifacts отдельно. Stable provider identifiers вроде Cursor `tool_use_id` или OpenCode `sessionID + callID` подтверждают logical identity внутри provider, но не являются OS PID. Legacy Gemini CLI hook entry points остаются для совместимости существующих установок; новое использование Google CLI должно переходить на Antigravity (`agy`).

## Inference gateways и model runtimes

Соберите OpenRouter или LiteLLM gateway evidence:

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Соберите model-runtime evidence для Ollama, llama.cpp, vLLM или LM Studio:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` — response-only evidence. `exchange` сохраняет caller-supplied request+response object и не заявляет transparent interception. Runtime catalog relations сохраняют source-specific semantics: `LOADED_MODEL`, `SERVES_MODEL` и `ADVERTISES_MODEL` не взаимозаменяемы. Catalog visibility LM Studio остаётся `ADVERTISES_MODEL` и не доказывает, что weights находятся resident in memory.

## Security analysis, evidence grades и bounded rule packs

Запустите встроенный analysis:

```bash
execweave analyze run.graph.json --output analysis.json
```

Findings показывают evidence grade независимо от severity. Текущие grades — `A`, `B`, `C`, `D`, `U`, от direct syscall attribution до inferred/unknown provenance. Это категории силы evidence, **а не probabilities или trust scores**.

Локальные rule packs добавляют bounded, объяснимые **single-edge observation** policies без выполнения third-party code:

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule pack не может выполнять code, задавать regex/path programs или утверждать byte-level data flow/exfiltration. Findings rule pack остаются observation-only.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

Seal завершённый run и затем проверьте, что его regular-file inventory не изменился относительно seal:

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Детерминированный manifest записывает file size/SHA-256 и отвергает symbolic links. Missing, modified, replaced или newly added regular files после seal приводят к failure verification.

Этот локальный seal намеренно **не** описывается как adversary-resistant tamper evidence, если evidence и manifest находятся внутри одной writable trust boundary. Manifest содержит `malicious_writer_resistance: false` и `external_trust_anchor: false`. Для более сильной гарантии скопируйте/защитите manifest digest за пределами этой boundary.

## Runtime evidence и graph operations

Portable collector работает на Linux, macOS и Windows. Linux также имеет syscall-backed `strace` reference backend.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation является session-correlated, а не process-causal; polling может пропускать достаточно короткую activity. Linux `strace` даёт более сильную process-attributed syscall evidence для поддерживаемых executions. Native collectors для Linux eBPF, Windows ETW и macOS Endpoint Security остаются в планах.

## Performance и large-run safety

v0.6.3 добавил bounded filesystem/viewer protections, incremental Live JSONL tailing и large-graph safety guards. v0.6.4 добавил detached Top и общий provisional live sidecar для настроенных provider integrations. Эти возможности остаются в v0.6.9. Ради этой release проект **не** мигрировал Live на SSE, artifact storage на SQLite, renderer на Canvas/WebGL или collectors на Rust только ради смены архитектуры.

Воспроизводимый reference result incremental `GraphAccumulator` достигает **164,273 ev/s** на 1M synthetic events в документированном GitHub Actions workload. Это benchmark накопления graph, а не end-to-end collector/browser throughput.

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data и methodology: [`docs/benchmarks/`](docs/benchmarks/).

## Layered artifacts

Provider-integrated run может содержать:

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
├── viewer.correlated.html
└── integrity.json            # после explicit seal
```

Derived correlation никогда не переписывает raw runtime или provider sidecar evidence.

## Privacy

ExecWeave — local-first: captures, content blobs, graphs, reports и viewers по умолчанию остаются локальными. **OS runtime collector** намеренно не захватывает file content или raw read/write byte buffers. Эту boundary нельзя путать с **provider full-fidelity content store** v0.6.9: если поддерживаемый hook/API явно предоставляет prompt, tool argument/result, model response, reasoning/thinking text, shell output, file content или другую sensitive value, ExecWeave может сохранить её полностью.

Не предполагайте, что content уже secret-redacted. Commands, paths, endpoint metadata, identifiers, model metadata, prompts, tool values и content blobs могут быть sensitive. Проверяйте весь run directory перед публикацией.

## Текущий статус

ExecWeave `main` сейчас **v0.6.9** и проходит release hardening. Последний публичный package/release может отставать от main до явной публикации GitHub Release; publish workflow проверяет точное совпадение release tag и package version до загрузки в PyPI.

v0.6.9 объединяет cross-platform runtime collection, materialized execution graphs, standalone/live viewing, консервативную provider↔runtime correlation, content-addressed full-fidelity provider evidence, evidence grades, bounded rule packs, явный runtime threat/fidelity contract и честный local run-integrity seal. Observed evidence и inference остаются разделёнными по дизайну.

## Документация

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ru.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ru.md)
- [`Live Graph`](docs/live-graph.ru.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ru.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ru.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ru.md)
- [`Google Antigravity Hooks`](docs/antigravity-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.ru.md)
- [`OpenCode Plugin`](docs/opencode-plugin.ru.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.ru.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.ru.md)
- [`Runtime Threat Model`](docs/runtime-threat-model.ru.md)
- [`Evidence Grades`](docs/evidence-grades.ru.md)
- [`Rule Packs`](docs/rule-packs.ru.md)
- [`Run Integrity`](docs/run-integrity.ru.md)
- [`Security Analysis`](docs/security-analysis.ru.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## Участие

Приветствуются contributions, особенно по native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, evidence/correlation methods, privacy/redaction, graph UX и performance evaluation.

## License

ExecWeave v0.6.8 и более поздние версии распространяются по **PolyForm Noncommercial License 1.0.0**. Некоммерческие использование, изменение и распространение разрешены в соответствии с этими условиями; любое коммерческое использование требует отдельной письменной коммерческой лицензии. Ранее выпущенные под MIT версии сохраняют условия лицензии, сопровождавшие их на момент выпуска. См. [`LICENSE`](LICENSE).
