# ExecWeave

[![PyPI](https://img.shields.io/pypi/v/execweave?label=PyPI)](https://pypi.org/project/execweave/)
[![Python](https://img.shields.io/pypi/pyversions/execweave?label=Python)](https://pypi.org/project/execweave/)
[![CI](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Irish-kw/ExecWeave?style=flat&label=Stars)](https://github.com/Irish-kw/ExecWeave/stargazers)

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

**Посмотрите, что ИИ-агенты на самом деле делают на вашем компьютере.**

ExecWeave — это open-source, local-first проект наблюдаемости, который превращает активность ИИ-агентов в интерактивный execution graph, явно отделяя observed evidence от inference.

> **Event — это ground truth; Graph — materialized view.**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live execution graph" width="100%">
</p>

## Установка

ExecWeave опубликован в PyPI как стандартный Python wheel/sdist. Установите последнюю release:

```bash
python -m pip install -U execweave
```

Ветка `main` может содержать более новый патч, чем текущий релиз PyPI. Чтобы протестировать последний mainline build напрямую:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

Для разработки:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Наблюдайте за Claude Code, OpenAI Codex или Gemini CLI в реальном времени:

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

Или соберите полный artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```

## Производительность и footprint

ExecWeave включает воспроизводимый package-level overhead benchmark, который запускается из реально установленного wheel. Референсный график использует тот же тип trade-off, который часто применяется для сравнений quality/cost моделей:

- **Ось X:** дополнительный peak process-tree RSS, низкий → высокий.
- **Ось Y:** runtime overhead, низкий → высокий.
- **Площадь пузыря:** median artifact size на один run.
- **Предпочтительная область:** нижний левый угол.

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Референсная среда: GitHub Actions Ubuntu runner, Intel Xeon Platinum 8573C, 4 logical CPUs, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

Тот же build создал wheel размером около **113 KB** и sdist около **198 KB**. Установленная distribution ExecWeave занимала примерно **849 KB**, без учета Python и dependency footprint.

Это намеренно короткий, file/process-heavy **reference microbenchmark**, а не универсальное заявление о производительности для всех workload. Неинструментированный baseline длится всего несколько сотен миллисекунд, поэтому процентный overhead выглядит увеличенным. Перед планированием емкости повторно запустите `execweave-overhead` на целевой машине и репрезентативном workload.

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Необработанные референсные данные и методика: [`docs/benchmarks/`](docs/benchmarks/).

## Evidence layers

ExecWeave намеренно моделирует четыре разные evidence layer вместо объединения их в один trace:

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Relationship помечается как causal только тогда, когда это утверждение поддерживается исходной телеметрией.

## Интеграции Agent / IDE

### Claude Code

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

### OpenAI Codex

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

### Gemini CLI

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

### Cursor

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Cursor предоставляет стабильный `tool_use_id`, позволяя установить exact logical tool-call identity между pre/post hooks.

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Project-local плагин OpenCode использует точную идентичность `sessionID + callID` и намеренно не пересылает tool output.

Provider-integrated runs сохраняют runtime, semantic и correlated artifacts отдельно. Bridges Tool → Process остаются консервативными derived evidence:

```text
inferred: true
causal: false
```

При неоднозначности edge не создается.

## Интеграции Inference gateway

OpenRouter и LiteLLM Proxy моделируются как `inference_gateway`, а не как локальные model runtimes.

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave хранит requested model, resolved model, routed provider и deployment identity как отдельные факты. Provider/deployment edges создаются только при наличии authoritative metadata и никогда не выводятся из префикса имени модели.

Если caller располагает явной shared identity между наблюдениями Gateway и Model Runtime, два request node можно связать, не объединяя слои:

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

`SAME_INFERENCE_REQUEST` — это evidence точной идентичности, а не causal evidence:

```text
identity_exact: true
inferred: false
causal: false
```

Raw shared request ID не сохраняется; записывается только identity hash, производный от SHA-256.

## Интеграции Model runtime

Текущие model-runtime integrations: **Ollama**, **llama.cpp**, **vLLM** и **LM Studio**.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

OpenAI-compatible runtimes используют общий parser response/usage и model-catalog, сохраняя при этом runtime-specific evidence semantics. Prompt, generated content и reasoning content не сохраняются. Чувствительные локальные пути моделей редактируются; для GGUF-путей llama.cpp применяется более строгая redaction.

Видимость модели в каталоге LM Studio представляется как `ADVERTISES_MODEL` и не считается доказательством того, что model weights загружены в память.

## Runtime evidence

Portable collector работает в Linux, macOS и Windows. В Linux также доступен syscall-backed reference backend `strace`.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Начиная с v0.6.1, child commands разрешаются общим cross-platform launcher resolver до запуска. Linux и macOS сохраняют обычное поведение PATH. Windows разрешает `.exe`, `.cmd` и `.bat` через PATH/PATHEXT, а явно указанный `.ps1` launcher запускается через PowerShell. Отдельный Windows CI фактически запускает Codex и Cursor recorders как из `cmd.exe`, так и из Windows PowerShell; полная интеграция Cursor semantic/correlation также продолжает проверяться обычной матрицей Windows, macOS и Ubuntu.

Portable filesystem watching является session-correlated, а не process-causal, поэтому очень короткоживущие процессы могут быть пропущены между интервалами polling. Linux-путь `strace` предоставляет process-attributed syscall evidence после завершения команды.

В будущем планируются native collectors для Linux eBPF, Windows ETW и macOS Endpoint Security.

## Safety patch v0.6.2

v0.6.2 усиливает безопасность ресурсов для long-running и high-cardinality sessions без изменения evidence semantics или graph schema 0.1:

- Слишком широкие recursive filesystem scopes, например корень файловой системы, user home или родитель каталогов home, больше не наблюдаются рекурсивно как есть; process, network и semantic collection могут продолжаться.
- Standalone и Live Viewer прекращают SVG materialization после превышения safety budget (1 500 nodes, 4 000 edges или примерно 5 000 SVG elements), предотвращая исчерпание памяти браузера. Канонический evidence artifact `graph.json` остается полным.
- Viewer layout/fit больше не передает произвольно большие массивы через spread в `Math.min` / `Math.max`, а перерисовка edges при перетаскивании node ограничивается animation frame.
- Live server tail-ит только новые bytes, добавленные в `events.jsonl`, начиная с byte offset, и инкрементально обновляет in-memory `GraphAccumulator`. Polling `/graph.json` больше не проигрывает всю историю событий; неполная последняя JSONL-строка буферизуется до появления newline.
- Изменения только event-count или aggregate-count обновляют Live stats/edge labels без full topology redraw. После превышения Viewer budget live `/graph.json` переключается на compact counts-only payload, в то время как collection и финальная canonical validation/full `graph.json` продолжаются без изменений.

Это safety patch на базе polling + incremental-ingestion, а не миграция архитектуры на SSE, SQLite, Rust или Canvas.

## Многоуровневые artifacts

Provider-integrated run может создать:

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Derived correlation layer никогда не переписывает raw evidence.

## Interactive Viewer

Standalone Viewer локален и self-contained. Текущий baseline включает pan/zoom, draggable nodes, node/edge inspection, фильтры node-type/relation/causal, **observed only**, search, evidence-sequence replay, progressive cluster expansion, focused neighborhoods, Saved Views, явную edge semantics и Correlation Summary.

## Операции с графом

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave graph-condense run.graph.json --output compact.graph.json --threshold 8 --keep-expansion
```

## Анализ безопасности

```bash
execweave analyze run.graph.json --output analysis.json
```

Security findings явно сохраняют границы доказательств. Возможный путь sensitive-file → network не означает, что byte-level exfiltration доказана:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Текущее состояние

ExecWeave `main` сейчас находится на версии **v0.6.2** и активно развивается.

Baseline включает runtime collection, graph materialization/querying, standalone/live Viewer, semantic integrations Claude/Codex/Gemini/Cursor/OpenCode, консервативную Tool → Process correlation, OpenRouter/LiteLLM gateway metadata, Ollama/llama.cpp/vLLM/LM Studio runtime metadata, exact Gateway ↔ Model Runtime request identity, опубликованные PyPI wheel/sdist packages, воспроизводимый overhead benchmark, cross-platform command-launcher compatibility, large-graph browser safety guards, incremental Live JSONL tail/cache и cross-platform CI для Python 3.10/3.12.

## Конфиденциальность

ExecWeave — local-first. Runtime events, semantic sidecars, graphs, reports и Viewers по умолчанию остаются локальными. File contents и raw read/write byte buffers намеренно не собираются. Native adapters также по умолчанию избегают prompts/transcripts/tool output, однако commands, paths, endpoint metadata, identifiers и model metadata все равно могут быть чувствительными.

Проверяйте artifacts перед публикацией.

## Документация

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ru.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ru.md)
- [`Live Graph`](docs/live-graph.ru.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ru.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ru.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ru.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.ru.md)
- [`Cursor Hooks`](docs/cursor-hooks.ru.md)
- [`OpenCode Plugin`](docs/opencode-plugin.ru.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.ru.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.ru.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.ru.md)

## Вклад в проект

Приветствуются contributions, особенно в native OS collectors, дополнительные Agent/IDE adapters, inference gateways, model runtimes, entity/correlation methods, privacy/redaction, graph UX и performance evaluation.

## Лицензия

См. [`LICENSE`](LICENSE).