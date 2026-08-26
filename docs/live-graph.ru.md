<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <a href="live-graph.ko.md">한국어</a> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

# Граф в реальном времени

ExecWeave может транслировать локальный граф выполнения, пока ИИ-агент или произвольная команда ещё работает.

```bash
execweave live --open -- claude
```

## Текущий контракт

Live runtime-collector намеренно использует кроссплатформенный backend `portable`. Начиная с v0.6.4 каждый live-запуск также может принимать второй append-only поток специализированных доказательств через sidecar, отдельный для данного запуска.

ExecWeave экспортирует путь sidecar в окружение запускаемой команды как:

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Специализированные доказательства могут автоматически поступать через несколько attribution-safe путей:

- заранее настроенные hooks Claude Code, OpenAI Codex, Gemini CLI и Cursor;
- установленный плагин OpenCode;
- loopback model-catalog probes, когда ExecWeave запускает распознанные локальные серверы Ollama, llama.cpp или vLLM;
- success-gated post-launch probe LM Studio для `lms server start --port <port>`, только если до запуска совместимого endpoint ещё не существовало;
- пользовательский callback ExecWeave для LiteLLM Proxy после однократной настройки, если proxy запускается внутри текущего окружения `execweave live`.

Это **не** означает, что `live` скрытно изменяет настройки provider, gateway или runtime. Интеграции hook/plugin/callback нужно один раз настроить там, где это требуется. Автоматический model-runtime probing ограничен распознанными локальными командами запуска и loopback-endpoints. Метаданные маршрутизации OpenRouter остаются неавтоматическими, потому что удалённое HTTPS/сетевое наблюдение не раскрывает authoritative provider routing details.

Linux-backend `strace` сейчас разбирает trace-файлы после завершения команды. Он даёт более сильную атрибуцию на основе системных вызовов, но в текущей реализации не является источником live-событий. ExecWeave не маркирует постобработанные доказательства как live-телеметрию.

Для более сильной Linux-атрибуции после запуска используйте:

```bash
execweave record --backend strace --open -- claude
```

## Поток данных v0.6.4

```text
specialized producers ─┐
  Agent hooks/plugin   │
  model-runtime probe  ├─→ semantic.jsonl ────────────────┐
  LiteLLM callback     │                                  │
                      ─┘                                  │
                                                         ↓
команда ─→ portable ─→ events.jsonl ─────→ incremental live normalizer
                                                         ↓
                                                  GraphAccumulator
                                                         ↓
                                              localhost HTTP server
                                                         ↓
                                                 /live.json deltas
                                                         ↓
                                                   browser / Top
```

OS runtime-доказательства остаются независимым потоком ground truth. Специализированные доказательства нормализуются в live-граф только предварительно; они не могут переписывать сырой runtime-поток или создавать отсутствующие доказательства.

Браузер и отделённая панель `execweave top` потребляют нумерованные snapshots/deltas из `/live.json`. `/graph.json` остаётся доступным как endpoint текущего snapshot. Инкрементальное чтение обрабатывает только новые добавленные JSONL-байты и буферизует незавершённую последнюю строку до появления перевода строки.

Когда команда завершается, ExecWeave:

1. валидирует завершённый runtime-поток событий;
2. завершает подготовленное до запуска attribution-safe специализированное наблюдение после команды;
3. если специализированные доказательства существуют, выполняет каноническое слияние runtime + specialized в `events.semantic.jsonl`;
4. заново строит финальный граф из этого канонического потока, а не доверяет предварительному live-состоянию;
5. записывает `graph.json` и автономный `viewer.html`;
6. помечает live-граф как завершённый и ненадолго обслуживает финальный viewer перед остановкой локального сервера.

Если специализированные события не поступили, финальная материализация остаётся runtime-only.

## Автоматически видимые специализированные интеграции

| Интеграция | Автоматическая доставка в Live Viewer v0.6.4 |
| --- | --- |
| Claude Code | **Да**, после настройки hooks ExecWeave |
| OpenAI Codex | **Да**, после настройки hooks ExecWeave |
| Gemini CLI | **Да**, после настройки hooks ExecWeave |
| Cursor | **Да**, после настройки hooks ExecWeave |
| OpenCode | **Да**, после установки плагина ExecWeave |
| Ollama | **Да**, для распознанных локальных запусков `ollama serve` |
| llama.cpp | **Да**, для распознанных локальных запусков `llama-server` |
| vLLM | **Да**, для распознанных локальных запусков сервера vLLM |
| LM Studio | **Да**, после успешного `lms server start --port <port>`, если endpoint отсутствовал до запуска |
| LiteLLM Proxy | **Да**, после настройки callback и наследования live-sidecar процессом proxy |
| OpenRouter | **Нет** автоматических routing metadata; OS/сетевую активность локального клиента всё ещё можно наблюдать |

Эти интеграции разделяют один и тот же контракт специализированного sidecar на запуск, но сохраняют собственные слои и семантику доказательств. Model catalog не доказывает, что Agent инициировал request; gateway response не доказывает, какой OS process вызвал request; отсутствующая identity никогда не придумывается.

## Terminal Top

`top` не рисуется поверх терминала Agent. Исходный terminal остаётся интерактивным, а панель подключается к той же localhost live-сессии в отдельном окне terminal:

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open` дополнительно открывает browser Viewer. Отделённая панель является только attach-client и никогда не запускает второй Agent. Её внутренний attach URL ограничен HTTP на localhost.

## Сетевая доступность

Live-сервер привязывается только к:

```text
127.0.0.1
```

Он не выставляется на `0.0.0.0` и не предназначен для доступа с других хостов LAN.

Чтобы явно выбрать порт:

```bash
execweave live --port 8765 --open -- claude
```

Порт `0` используется по умолчанию и просит операционную систему выбрать свободный локальный порт.

## Артефакты

Каталог запуска по умолчанию:

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── semantic.jsonl
├── events.semantic.jsonl      # материализуется только при наличии специализированных доказательств
├── graph.json
└── viewer.html
```

`events.jsonl` всегда остаётся runtime-only. `semantic.jsonl` — сырой специализированный sidecar и может содержать Agent/IDE-, model-runtime- или inference-gateway-доказательства. Финальный `graph.json` строится из `events.semantic.jsonl`, если специализированные доказательства существуют; иначе непосредственно из `events.jsonl`.

Выбрать другой каталог:

```bash
execweave live --output-dir my-live-run --open -- claude
```

Существующие непустые артефакты отклоняются, а не перезаписываются.

## Предварительная live-нормализация

Во время live-запуска оба JSONL-потока могут быть неполными, поскольку сессия ещё не завершена.

Поэтому live-normalizer работает инкрементально и консервативно. Уже наблюдаемая runtime-идентичность процесса может использоваться для разрешения специализированных ссылок на процессы, но отсутствующая identity никогда не угадывается. Специализированное событие, которое ещё нельзя нормализовать, не становится более сильным доказательством только потому, что было замечено live.

Усечение sidecar сбрасывает предварительную материализацию и повторно проигрывает текущие файлы. Незавершённые последние JSONL-записи буферизуются вместо обработки как завершённых событий. Финальный граф всё равно заново строится из канонического слияния после успешной runtime-валидации.

## Граница автоматических model-runtime probes

Автоматическое model-runtime наблюдение намеренно ограничено. ExecWeave пробует только распознанные локальные команды запуска серверов и local/loopback endpoints. Ошибки probe являются fail-open и никогда не меняют результат запускаемой команды.

Для Ollama, llama.cpp и vLLM локальное состояние/каталог моделей может сниматься во время работы сервера. LM Studio отличается: `lms server start` — короткоживущий launcher для постоянного сервера. ExecWeave готовит наблюдение до запуска, не приписывает текущей сессии уже существующий совместимый endpoint и материализует post-launch каталог только после успешного завершения launcher.

Отношения каталога сохраняют runtime-specific semantics. Например, видимость каталога LM Studio представляется как `ADVERTISES_MODEL`, а не как доказательство того, что веса модели в этот момент находились в памяти.

## Граница callback LiteLLM

LiteLLM Proxy может один раз загрузить `execweave.litellm_callback.execweave_litellm_callback` через custom-callback configuration. Когда proxy работает внутри `execweave live`, он наследует `EXECWEAVE_SEMANTIC_SIDECAR` и пишет только whitelisted routing/usage metadata в данный запуск.

Callback не сохраняет messages, response content, model parameters, arbitrary metadata, API-key metadata или provider `api_base`. Provider identity не выводится из model string или URL. Без run-specific sidecar environment variable callback является no-op.

Вывести фрагмент конфигурации LiteLLM:

```bash
execweave-litellm-callback --print-config
```

## Ограничения portable-backend

Текущий live runtime-слой наследует ограничения переносного collector:

- обнаружение процессов основано на polling;
- очень короткоживущие процессы могут быть пропущены;
- изменения файловой системы коррелируются с сессией, а не атрибутируются процессам;
- инспекция сети по процессам зависит от visibility и permissions операционной системы.

Эти ограничения остаются видимыми в метаданных атрибуции событий. Live Viewer не повышает некаузальное наблюдение до каузального ребра.

## Безопасность больших сессий

Live-обновления используют ограниченную историю deltas вместо повторного чтения всего потока событий при каждом poll. Если graph превышает safety budget Viewer, live-endpoint переключается на компактный counts-only payload, чтобы collection и генерация финального канонического артефакта продолжались без принудительной материализации небезопасного большого SVG-графа в браузере.

## Будущие нативные live-backend

Планируемые collector:

- Linux eBPF;
- Windows ETW;
- macOS Endpoint Security.

Цель — сохранить ту же семантику событий ExecWeave, одновременно улучшая полноту, атрибуцию процессов и runtime overhead.

## Покрытие CI

Конфигурация CI репозитория покрывает:

- запуск localhost live-сессии и генерацию финальных артефактов;
- нумерованные snapshot/delta и resynchronization;
- незавершённые последние JSONL-записи;
- поступление sidecar до готовности runtime identity;
- усечение и replay sidecar;
- каноническую финальную перестройку runtime + specialized;
- автоматическую доставку через общий sidecar для Claude, Codex, Gemini, Cursor и OpenCode;
- автоматические локальные model-runtime probes для Ollama, llama.cpp, vLLM и attribution-safe обработку запуска LM Studio;
- privacy, fail-open behavior и финальную live-graph materialization callback LiteLLM;
- отделённое поведение Top без запуска второго Agent;
- ограничение Top attach URL только localhost;
- clean-wheel установку команды настройки callback LiteLLM.
