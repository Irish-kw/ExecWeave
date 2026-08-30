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

**Узнайте, что AI Agent действительно делает на вашей машине.**

ExecWeave — source-available, local-first проект наблюдаемости, который превращает активность AI Agent в интерактивный execution graph и явно разделяет observed evidence, provider content и derived inference.

> **Event — это ground truth. Graph — materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## Установка

Установите последний опубликованный wheel/sdist из PyPI:

```bash
python -m pip install -U execweave
```

Текущая версия — **v0.7.4**.

Для разработки:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Быстрый старт

Live OS-runtime telemetry работает с **любой локальной командой**. Названия Agent/runtime ниже — лишь примеры, а не whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Разрешите Hook, когда появится запрос.** При первом provider-integrated запуске Agent/IDE может спросить, можно ли ExecWeave включить локальную Hook-интеграцию. Выберите **Allow / Yes**. Без разрешения OS-runtime telemetry может продолжать работать, но provider-level observability для tools, models и supplied content будет ограничена или недоступна.

Google Antigravity сейчас использует CLI-команду `agy`. ExecWeave также принимает `antigravity` как удобный alias и преобразует его в `agy`. Для Cursor команда `execweave live --open -- cursor` сначала ищет обычный PATH launcher, а затем при необходимости использует стандартный binary десктопного приложения Cursor на macOS/Windows.

Для создания finalized artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` оставляет Agent интерактивным в стартовом terminal и одновременно открывает либо подключает detached Top dashboard в зависимости от host environment.

**v0.7.4 — фокус на conversation отдельного agent в dashboard.** Опираясь на provider-neutral, agent-local multi-agent conversations, материализованные в v0.7.3, выбор agent node теперь ограничивает conversation panel только этим agent, показывая число видимых элементов и control для возврата к полному дереву. Клик сопоставляется с thread по identity graph agent node, а не по совпадению label, поэтому agents с одинаковым provider nickname остаются различимыми. Секции conversation в Markdown теперь начинаются с agent path, а не с provider nickname, так что каждая секция называет свой agent. Покрыты и standalone viewer, и live dashboard; сама материализация conversation не изменена.

Единый dashboard объединяет execution graph, logs и conversation records в одном inspection flow. Finalized runs создают `conversations.md` и `conversations.json`, а проверенные provider transcripts копируются в run-local SHA-256 content store. Claude Code, OpenAI Codex, Cursor, OpenCode и Google Antigravity используют наиболее сильную multi-agent evidence, которую реально раскрывает соответствующая integration. Если gateway или local runtime показывает только root request/response, ExecWeave отображает только root conversation и не выдумывает subagents или hidden routing.

## v0.6.9: full-fidelity observability с явными evidence boundaries

v0.6.9 расширяет provider/runtime observability за пределы компактной metadata. Когда поддерживаемая integration point явно предоставляет content, ExecWeave может сохранить **полное предоставленное значение** в локальном SHA-256 content-addressed store, оставив в semantic event stream только reference.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

В зависимости от adapter и upstream hook/API surface сохраняемый content может включать prompts/messages, model request/response objects, tool inputs/results, assistant responses, reasoning/thinking text, если он явно раскрыт, shell/MCP output и file content, предоставленный provider hooks.

`complete_from_source: true` означает лишь, что ExecWeave сохранил полное значение, переданное этой integration point. Это **не означает**, что ExecWeave видел hidden model state, provider-side stages, которые не были раскрыты, не наблюдавшийся final wire request или bytes, которые не были перехвачены.

Full fidelity также меняет privacy boundary: application-level secrets внутри content сохраняются. Известные transport credentials фильтруются только в выбранных provider-metadata projections, где adapter явно определяет такое поведение. ExecWeave **не является** универсальным secret scanner или content redactor.

### Поддерживаемые semantic / inference surfaces

| Integration | OS-runtime observation при запуске под ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity hook content + subagent result, если его раскрывает provider |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + conversation/subagent routing, когда его можно валидировать |
| Cursor | Yes | native hooks + exact subagent task/summary routing, когда доступно |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | Только если локальный process запущен под ExecWeave | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes, если настроенный proxy запущен под ExecWeave | metadata-oriented gateway callback/event integration |
| OpenRouter | Наблюдается локальный client, а не process удалённого сервиса | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` — caller-supplied request+response evidence, а не transparent wire interception. LiteLLM Proxy остаётся более узкой metadata-oriented integration в текущем baseline. Provider-neutral conversation projection никогда не превращает отсутствующую provider evidence в выдуманную agent relationship.

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

Relationship считается causal только тогда, когда underlying telemetry действительно поддерживает такой claim. Tool → Process bridges остаются консервативной derived evidence:

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

Provider-integrated recorders сохраняют raw runtime, semantic, correlated и conversation artifacts отдельно. Stable provider identifiers, например Cursor `tool_use_id`, Codex rollout thread identity или OpenCode `sessionID + callID`, подтверждают logical provider identity, но не являются OS PIDs. Cross-agent content показывается только если provider явно раскрывает route, delegation или result. Legacy Gemini CLI hook entry points остаются в пакете ради совместимости существующих установок, но для нового Google CLI следует использовать Antigravity (`agy`).

## Inference gateways и model runtimes

Сбор evidence OpenRouter или LiteLLM gateway:

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Сбор model-runtime evidence для Ollama, llama.cpp, vLLM или LM Studio:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` — response-only evidence. `exchange` сохраняет caller-supplied request+response object и не утверждает transparent interception. Runtime catalog relations сохраняют source-specific смысл: `LOADED_MODEL`, `SERVES_MODEL` и `ADVERTISES_MODEL` не взаимозаменяемы. Catalog visibility LM Studio остаётся `ADVERTISES_MODEL` и не доказывает, что weights находились resident in memory.

## Security analysis, evidence grades и bounded rule packs

Запустите встроенный analysis:

```bash
execweave analyze run.graph.json --output analysis.json
```

Findings показывают evidence grade независимо от severity. Текущие grades: `A`, `B`, `C`, `D`, `U` — от direct syscall attribution до inferred/unknown provenance. Это категории силы evidence, **не probabilities и не trust scores**.

Local rule packs позволяют добавлять bounded, объяснимые **single-edge observation** policies без выполнения third-party code:

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule packs не могут выполнять code, определять regex/path programs или утверждать byte-level data flow/exfiltration. Rule-pack findings остаются observation-only.

Security findings явно сохраняют и более сильные non-claims:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

Можно seal завершённый run и позже проверить, не изменился ли его regular-file inventory относительно seal:

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Deterministic manifest записывает file size/SHA-256 и отклоняет symbolic links. Он выявляет пропавшие, изменённые, заменённые или новые regular files после seal.

Этот local seal намеренно **не** описывается как adversary-resistant tamper evidence, когда evidence и manifest остаются в одной writable trust boundary. Manifest фиксирует `malicious_writer_resistance: false` и `external_trust_anchor: false`. Если требуется более сильный trust anchor, скопируйте или защитите digest manifest за пределами этой boundary.

## Runtime evidence и graph operations

Portable collector работает в Linux, macOS и Windows. Для Linux также есть syscall-backed reference backend `strace`.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation является session-correlated, а не process-causal; polling может пропускать очень короткую активность. Linux `strace` даёт более сильную process-attributed syscall evidence для поддерживаемых executions. В будущем по-прежнему планируются native collectors для Linux eBPF, Windows ETW и macOS Endpoint Security.

## Performance и безопасность больших runs

ExecWeave включает bounded filesystem/viewer protections, incremental Live JSONL tailing, large-graph safety guards, detached Top и provisional live sidecars для настроенных provider integrations.

Воспроизводимый reference result incremental `GraphAccumulator` достигает **164,273 ev/s** на 1M synthetic events в документированном GitHub Actions workload. Это benchmark graph accumulation, а не end-to-end collector/browser throughput.

Запустите package-level overhead benchmark на репрезентативном host/workload:

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data и methodology находятся в [`docs/benchmarks/`](docs/benchmarks/).

## Layered artifacts

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
└── integrity.json            # после явного seal
```

Derived correlation никогда не переписывает raw runtime или provider sidecar evidence.

## Privacy

ExecWeave — local-first: captures, content blobs, graphs, reports и viewers по умолчанию остаются локальными. **OS runtime collector** намеренно не захватывает file contents или raw read/write byte buffers. Эту boundary нельзя путать с **provider full-fidelity content store, введённым в v0.6.9**: поддерживаемые hooks/APIs могут явно передавать prompts, tool arguments/results, model responses, reasoning/thinking text, shell output, file content и другие чувствительные значения, и ExecWeave может сохранить их полностью.

Conversation isolation — это правило attribution/display, а не redaction boundary. Если provider явно отправляет содержимое Agent 1 в Agent 2, такая routed evidence законно может появиться у участвующих endpoints. Не предполагайте, что content был secret-redacted. Commands, paths, endpoint metadata, identifiers, model metadata, prompts, tool values и content blobs могут быть чувствительными. Перед публикацией проверьте весь run directory.

## Текущий статус

v0.7.4 объединяет cross-platform runtime collection, materialized execution graphs, standalone/live dashboards, conservative provider↔runtime correlation, full-fidelity content-addressed provider evidence, attributable multi-agent execution traces, прямой run-local conversation access agent-local conversation isolation в provider-neutral projections и per-agent conversation focus в standalone и live dashboards. Каждая integration сохраняет только наиболее сильную identity/routing evidence, реально раскрытую provider, и abstain-ит при её отсутствии. Observed evidence и inference по-прежнему разделены архитектурно.

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

## Участие в разработке

Приветствуются contributions, особенно для native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, evidence/correlation methods, privacy/redaction, graph UX, multi-agent conversation attribution и performance evaluation.

## License

Начиная с v0.6.8 ExecWeave распространяется по **PolyForm Noncommercial License 1.0.0**. Некоммерческое использование, изменение и распространение разрешены на условиях лицензии. Коммерческое использование требует отдельной письменной commercial license от licensor. См. [`LICENSE`](LICENSE).
