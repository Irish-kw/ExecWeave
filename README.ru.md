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

**Смотрите, что AI-агенты действительно делают на вашей машине.**

ExecWeave — это local-first проект наблюдаемости для AI-агентов и инструментов разработки с ИИ. Он объединяет семантику, предоставляемую Provider, с runtime-evidence на уровне операционной системы и отображает их в одном интерактивном Execution Graph, не смешивая разные уровни доказательности.

> **Events — это evidence. Graph — материализованное представление этих evidence.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="Демонстрация live dashboard ExecWeave" width="100%">
</p>

## Зачем нужен ExecWeave

Agent может сообщить, что использовал инструмент, изменил файл или подключился к сервису. Такая Provider-семантика полезна, но это не то же самое, что фактически наблюдаемое поведение на уровне ОС. ExecWeave позволяет проверять оба слоя вместе, сохраняя различия в силе evidence.

- **Один Dashboard для Live и Finished.** Страница текущего run, завершённый run и standalone `viewer.html` используют одну и ту же модель Graph и Conversation.
- **Provider-aware semantics.** Hooks, rollout transcripts, plugins и runtime APIs используются только там, где Provider действительно их предоставляет.
- **OS runtime evidence.** Process, File и Network endpoint можно наблюдать независимо от того, что сообщает Agent.
- **Evidence-aware attribution.** Direct observation, exact identity, консервативная inference и causal claim остаются раздельными.
- **Local-first storage.** Run artifacts остаются локально, пока вы сами не решите их передать.
- **Не привязан к одному Agent.** Обычные локальные команды можно наблюдать даже без специализированного adapter.

## Установка

Из PyPI:

```bash
python -m pip install -U execweave
```

Для разработки:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Быстрый старт

Оберните любую локальную команду в `execweave live`:

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- python my_agent.py
```

Если нужны в основном финализированные artifacts:

```bash
execweave record --open -- python my_agent.py
```

Если программа должна остаться интерактивной в текущем terminal, а обзор — открыться отдельно:

```bash
execweave top -- codex
```

### Разрешение Provider integration

Некоторые Agents и IDE запрашивают разрешение перед включением локального hook или plugin. Разрешите интеграцию ExecWeave, если нужны Provider-level evidence для Prompt, Response, Tool, Model и Conversation. Без разрешения OS runtime observation всё ещё может работать, но semantic coverage может быть меньше.

Google Antigravity сейчас использует CLI-команду `agy`. ExecWeave также принимает `antigravity` как более понятный alias.

В Windows простой вызов `cursor` следует установке Cursor, указанной в PATH пользователя. Явно заданный launcher path сохраняется без изменений.

## Ollama

ExecWeave поддерживает два типичных локальных workflow для Ollama.

### Managed server capture

Запустите Ollama Server через ExecWeave:

```bash
execweave live --open -- ollama serve
```

После этого используйте Ollama как обычно в другом terminal:

```bash
ollama run deepseek-r1:1.5b
```

SDK-вызовы, локальные OpenAI-compatible requests и `curl`-requests к managed local endpoint могут быть связаны с тем же ExecWeave run. Второй terminal не нужно дополнительно оборачивать в ExecWeave.

Managed relay намеренно ограничен локальными loopback endpoints и не переписывает wildcard или внешне доступные listeners.

### Direct client capture

Если Ollama Server уже запущен, можно обернуть непосредственно client:

```bash
execweave live --open -- ollama run deepseek-r1:1.5b
```

Этот режим не запускает Ollama Server, поэтому требуется доступный upstream server.

## Dashboard

Dashboard предназначен для того, чтобы большие multi-agent runs оставались читаемыми без изменения исходной evidence.

- **Execution graph:** Agent, Process, File, Network endpoint, Tool, Model/runtime entity и поддерживаемые relations.
- **Conversation rounds:** новые и старые раунды остаются у правильного Agent и не перезаписываются последующими messages.
- **Node details:** можно проверять Process identity, File history, Network endpoints, Tools и Provider conversation content.
- **Stable live updates:** изменения run отображаются в том же document без полной замены страницы.
- **Large-run folding:** старые элементы многочисленных node types можно сворачивать, сохраняя возможность инспекции.
- **Selection-focused layout:** Graph traffic, не относящийся к выбранному Agent или runtime object, визуально приглушается.

Для больших runs доступны параметры:

```text
--fold-budget N
--viewer-max-nodes N
--viewer-max-edges N
--viewer-max-dom-elements N
```

## Поддерживаемые интеграции

| Integration | OS runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Да, если запущен под ExecWeave | native hooks и предоставленный Provider conversation/tool content |
| OpenAI Codex | Да | lifecycle hooks, validated rollout transcripts, agent/subagent routing где он доступен |
| Google Antigravity | Да | passive hooks и conversation/subagent routing где он доступен |
| Cursor | Да | native hooks и task/subagent routing где он доступен |
| OpenCode | Да | project plugin, session/task routing, supplied plugin content |
| Ollama | Да | managed local relay и model-runtime evidence |
| llama.cpp | Да | model-runtime event/exchange/probe |
| vLLM | Да | model-runtime event/exchange/probe |
| LM Studio | Когда локальный Process наблюдаем | model-runtime catalog/runtime evidence |
| LiteLLM Proxy | Когда локальный proxy наблюдаем | gateway metadata и event integration |
| OpenRouter | Только локальный client | caller-supplied gateway event/exchange evidence |

Provider identifiers, такие как tool-call ID, session ID, rollout thread ID или subagent route, являются логическими идентификаторами, а не OS PID. ExecWeave связывает слои только тогда, когда доступная evidence действительно поддерживает такую связь.

## Evidence model

ExecWeave разделяет несколько основных слоёв:

```text
Agent / IDE semantics и supplied content
                ↓
Inference gateway / routing evidence
                ↓
Model runtime / inference-server evidence
                ↓
OS runtime evidence: process / file / network
```

Relation помечается как causal только тогда, когда базовая telemetry действительно поддерживает причинное утверждение. Консервативные bridges остаются явной derived evidence:

```text
inferred: true
causal: false
```

Exact shared request identity может доказывать identity, но не causal связь:

```text
identity_exact: true
inferred: false
causal: false
```

Если attribution неоднозначна, ExecWeave предпочитает не создавать edge, а не выдумывать более сильную связь.

### Full-fidelity supplied content

Поддерживаемые hooks, plugins и APIs могут сохранять полные значения, явно переданные интеграцией, в локальном SHA-256 content-addressed store:

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

В зависимости от интеграции это могут быть Prompt, Message, Request/Response object, Tool input/result, Assistant response, явно предоставленный reasoning text, Shell output и supplied file content.

`complete_from_source: true` означает, что ExecWeave сохранил полное значение, полученное в данной integration point. Это не означает наблюдение скрытого model state или внутренних Provider-данных, которые не были предоставлены.

## Основные команды

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

`event` — это односторонняя event evidence. `exchange` сохраняет пару request/response, предоставленную caller, и не заявляет о transparent wire interception.

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
└── integrity.json
```

Raw observations остаются отделены от derived semantic/correlation outputs.

## Ограничения и конфиденциальность

- Portable collector работает в Linux, macOS и Windows. Portable filesystem observation является session-correlated и не всегда process-causal; polling может пропустить очень кратковременную активность.
- В Linux также доступен `strace` reference backend с более сильной syscall-attributed evidence для поддерживаемых executions.
- Provider semantic coverage полностью зависит от того, что конкретная integration действительно предоставляет. Неэкспонированные Prompt, hidden reasoning, remote Provider internals и routing нельзя надёжно восстановить.
- Full-fidelity content может содержать Credential, Secret, Source code, Prompt, Tool value, Model response, Shell output и File content.
- Conversation isolation — это правило attribution, а не redaction boundary. Контент, который Provider явно маршрутизирует, может законно появляться у нескольких participants.
- Local integrity manifest обнаруживает изменения относительно manifest, но не является adversary-resistant trusted logging system, если evidence и manifest находятся в одной writable trust boundary.
- Перед публикацией или передачей проверьте весь run directory.

## Разработка

Тесты:

```bash
python -m pytest
```

Lint:

```bash
python -m ruff check .
```

Issues и Pull Requests приветствуются. Для новых интеграций чётко разделяйте directly observed evidence, Provider supplied evidence и derived evidence.

## Лицензия

ExecWeave распространяется по **PolyForm Noncommercial License 1.0.0**. Полный текст условий находится в [LICENSE](LICENSE).
