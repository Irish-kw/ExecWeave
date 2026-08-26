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
  <strong>Deutsch</strong> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

**Sehen Sie, was KI-Agenten auf Ihrem Rechner tatsächlich tun.**

ExecWeave ist ein Open-Source-, local-first Observability-Projekt, das die Aktivität von KI-Agenten in einen interaktiven execution graph überführt und observed evidence klar von inference trennt.

> **Das Event ist die ground truth; der Graph ist eine materialized view.**

<p align="center">
  <img src="docs/assets/execweave-launch-demo-v5-x.gif" alt="ExecWeave Live execution graph" width="100%">
</p>

<!-- execweave-demo:start -->
## Diese Demo reproduzieren

Der Screenshot oben stammt aus einer echten ExecWeave-v0.6.3-Live-Session. Dieser Workload erzeugt absichtlich genügend Aktivität für einen aussagekräftigen execution graph: mehrere Python modules, JSON/CSV files, tests, file inspection und ausgehende HTTP requests.

Starte eine lokale Agent CLI unter ExecWeave, zum Beispiel:

```bash
execweave live --open -- claude
```

Füge danach diesen workload prompt in den Agent ein:

```text
Create a small Python project in ./execweave-demo with 8 modules,
generate sample JSON and CSV data, run the program and tests,
inspect the generated files, and fetch example.com plus the GitHub API.
```

Derselbe workload funktioniert auch mit `codex`, `gemini`, `cursor` oder `opencode`. Die genaue Anzahl von nodes, edges, events, processes und endpoints hängt von OS, Agent version und environment ab. ExecWeave zeichnet tatsächlich beobachtetes runtime evidence auf; der Screenshot zeigt einen konkreten Lauf und keinen fest erwarteten graph.
<!-- execweave-demo:end -->

## Installation

ExecWeave wird auf PyPI als normales Python wheel/sdist veröffentlicht. Installieren Sie die neueste Release-Version mit:

```bash
python -m pip install -U execweave
```

Der `main`-Branch kann einen neueren Patch als die aktuelle PyPI-Release enthalten. Um den neuesten mainline build direkt zu testen:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

Für die Entwicklung:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Live-OS-Runtime-Telemetrie funktioniert mit **jedem lokalen Befehl**. Die folgenden Namen sind Beispiele, keine Whitelist:

```bash
# Agent / IDE CLIs
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- cursor
execweave live --open -- opencode

# Any local program
execweave live --open -- python my_agent.py

# A local model runtime launched under ExecWeave
execweave live --open -- ollama serve
```

`execweave live` streamt Process-, File- und Network-Evidence für den gestarteten Command Tree. Seit v0.6.4 speisen konfigurierte Claude/Codex/Gemini/Cursor-Hooks und das OpenCode-Plugin automatisch den run-spezifischen Live-Sidecar; unter ExecWeave gestartete Ollama-, llama.cpp- und vLLM-Server erhalten zusätzlich einen automatischen lokalen Model-Catalog-Probe.

#### Live-Capability-Matrix

| Integration | Direct OS-runtime live | Specialized metadata | Automatisch im Live Viewer |
| --- | --- | --- | --- |
| Claude Code | Ja | `execweave-claude-record` / hooks | Ja (konfigurierter Hook/Plugin) |
| OpenAI Codex | Ja | `execweave-codex-record` / hooks | Ja (konfigurierter Hook/Plugin) |
| Gemini CLI | Ja | `execweave-gemini-record` / hooks | Ja (konfigurierter Hook/Plugin) |
| Cursor | Ja | `execweave-cursor-record` / hooks | Ja (konfigurierter Hook/Plugin) |
| OpenCode | Ja | `execweave-opencode-record` / plugin | Ja (konfigurierter Hook/Plugin) |
| Ollama | Ja, wenn es unter ExecWeave gestartet wird, z. B. `ollama serve` | `execweave-model-runtime event/probe --runtime ollama` | Ja (automatischer lokaler Probe) |
| llama.cpp | Ja, wenn der lokale Server unter ExecWeave gestartet wird | `execweave-model-runtime event/probe --runtime llamacpp` | Ja (automatischer lokaler Probe) |
| vLLM | Ja, wenn der lokale Server unter ExecWeave gestartet wird | `execweave-model-runtime event/probe --runtime vllm` | Ja (automatischer lokaler Probe) |
| LM Studio | Nur für einen lokalen Prozess, der unter ExecWeave gestartet wurde; ein bereits laufender Server wird nicht attached | `execweave-model-runtime event/probe --runtime lmstudio` | Nein |
| LiteLLM Proxy | Ja, wenn der lokale Proxy unter ExecWeave gestartet wird | `execweave-inference-gateway event --gateway litellm` | Nein |
| OpenRouter | Kein direkt startbarer Remote-Service-Prozess; stattdessen den lokalen Client/Agent unter `live` ausführen | `execweave-inference-gateway event/generation --gateway openrouter` | Nein |

Für einen bereits laufenden Ollama-Server kann `execweave-model-runtime probe --runtime ollama` den geladenen Modellzustand snapshotten. Bei OpenRouter kann `live` den lokalen Client und dessen Network-Aktivität beobachten; Gateway-Routing-/Usage-Metadaten bleiben eine separate Evidence-Layer.

<!-- v0.6.4-live -->
### v0.6.4 Live-Observability

`top` lässt den Agent im ursprünglichen Terminal interaktiv und öffnet das Dashboard in einem separaten Terminalfenster:

```bash
execweave top -- codex
execweave top --open -- codex
```

Live-Updates verwenden inkrementelle Snapshots/Deltas mit begrenzter History. Live- und Standalone-Viewer behalten die Dark/Light-Auswahl. Unter Linux werden sehr große rekursive Filesystem-Scopes vorab geprüft und bei Bedarf automatisch von inotify auf Polling zurückgestuft.

v0.6.4 erstellt für jeden Live-Run einen gemeinsamen Specialized-Evidence-Sidecar. Konfigurierte Claude/Codex/Gemini/Cursor-Hooks und das OpenCode-Plugin erscheinen automatisch im selben Live Graph; unter ExecWeave gestartete Ollama-, llama.cpp- und vLLM-Server werden automatisch über ihre Loopback-API nach dem Model Catalog abgefragt. Diese spezialisierten Live-Events sind provisional; nach Ende des Befehls wird der finale Graph aus dem canonical Runtime+Semantic-Merge neu aufgebaut. Fehlende Evidence wird nicht erfunden.

Mit `execweave-scalability` lässt sich der Graph-Scalability-Benchmark reproduzieren; CI deckt 10k, 100k und 1M synthetische Events ab.

#### Scalability-Benchmark

Referenzergebnis aus GitHub Actions für den inkrementellen `GraphAccumulator`-Synthetic-Workload (`retain_event_ids=False`):

| Events | Apply time | Throughput | Nodes | Edges | Apply RSS Δ | Snapshot |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10k | 0.114 s | 87,681 ev/s | 10,001 | 10,000 | 35.9 MiB | 8.5 MiB |
| 100k | 0.654 s | 152,816 ev/s | 10,001 | 10,000 | 25.8 MiB | 8.6 MiB |
| **1M** | **6.087 s** | **164,273 ev/s** | **10,001** | **10,000** | **23.5 MiB** | **8.6 MiB** |

Bei **1.000.000 Events** duplizierte der inkrementelle In-Memory-Graph keine Raw Event IDs; Raw Evidence bleibt vom materialized graph getrennt. Dieser Benchmark misst Graph-Akkumulation und Snapshot-Materialisierung, nicht den End-to-End-Durchsatz des Collectors oder Browsers.

Oder die vollständige Artifact-Pipeline erzeugen:

```bash
execweave record --open -- python my_agent.py
```

## Leistung und Footprint

ExecWeave enthält einen reproduzierbaren package-level overhead benchmark, der aus einem tatsächlich installierten wheel ausgeführt wird. Der Referenzplot verwendet dieselbe Art von Trade-off-Darstellung, die häufig für Quality/Cost-Vergleiche genutzt wird:

- **X-Achse:** zusätzlicher Peak-Process-Tree-RSS, niedrig → hoch.
- **Y-Achse:** Runtime-Overhead, niedrig → hoch.
- **Bubble-Fläche:** mediane Artifact-Größe pro Run.
- **Bevorzugter Bereich:** unten links.

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Referenzumgebung: GitHub Actions Ubuntu runner, Intel Xeon Platinum 8573C, 4 logische CPUs, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

Derselbe Build erzeugte ein wheel von ungefähr **113 KB** und ein sdist von ungefähr **198 KB**. Die installierte ExecWeave-Distribution selbst belegte ungefähr **849 KB**, ohne Python und Dependency-Footprints.

Dies ist bewusst ein kurzer, file/process-lastiger **reference microbenchmark** und keine universelle Aussage über alle Workloads. Da die nicht instrumentierte Baseline nur wenige hundert Millisekunden dauert, wird der prozentuale Overhead verstärkt dargestellt. Führen Sie `execweave-overhead` auf dem Zielhost mit einem repräsentativen Workload erneut aus, bevor Sie Kapazitätsentscheidungen treffen.

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Rohe Referenzdaten und Methodik: [`docs/benchmarks/`](docs/benchmarks/).

## Evidence layers

ExecWeave modelliert absichtlich vier unterschiedliche Evidence-Layer, statt sie in eine einzige Trace zu glätten:

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Eine Beziehung wird nur dann als causal markiert, wenn die zugrunde liegende Telemetrie diese Aussage unterstützt.

## Agent-/IDE-Integrationen

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

Cursor liefert eine stabile `tool_use_id`, wodurch eine exakte logical tool-call identity zwischen den pre/post hooks möglich ist.

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Das projektlokale OpenCode-Plugin verwendet die exakte Identität `sessionID + callID` und leitet Tool-Output absichtlich nicht weiter.

Provider-integrierte Runs bewahren Runtime-, Semantic- und Correlated-Artefakte getrennt auf. Tool → Process-Bridges bleiben konservative abgeleitete Evidence:

```text
inferred: true
causal: false
```

Mehrdeutigkeit erzeugt keine Edge.

## Inference-Gateway-Integrationen

OpenRouter und LiteLLM Proxy werden als `inference_gateway` modelliert, nicht als lokale Model Runtimes.

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave hält requested model, resolved model, routed provider und deployment identity getrennt. Provider-/Deployment-Edges werden nur ausgegeben, wenn authoritative metadata vorliegen; sie werden niemals aus einem Modellnamen-Präfix abgeleitet.

Wenn der Caller eine explizite shared identity zwischen Gateway- und Model-Runtime-Beobachtungen besitzt, können die beiden Request-Nodes verknüpft werden, ohne die Layer zusammenzuführen:

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

`SAME_INFERENCE_REQUEST` ist exakte Identity-Evidence, keine kausale Evidence:

```text
identity_exact: true
inferred: false
causal: false
```

Die rohe shared request ID wird nicht gespeichert; nur ein SHA-256-abgeleiteter Identity-Hash wird persistiert.

## Model-Runtime-Integrationen

Aktuell unterstützt ExecWeave **Ollama**, **llama.cpp**, **vLLM** und **LM Studio**.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

OpenAI-kompatible Runtimes teilen sich Response/Usage- und Model-Catalog-Parsing, behalten aber ihre runtime-spezifischen Evidence-Semantiken. Prompt-, Generated- und Reasoning-Inhalte werden nicht gespeichert. Sensible lokale Modellpfade werden redigiert; llama.cpp verwendet strengere Redaction für GGUF-Pfade.

Die Sichtbarkeit eines Modells im LM-Studio-Katalog wird als `ADVERTISES_MODEL` dargestellt und nicht als Beweis dafür behandelt, dass Model Weights im Speicher geladen sind.

## Runtime evidence

Der portable Collector läuft unter Linux, macOS und Windows. Linux verfügt zusätzlich über einen syscall-basierten `strace`-Referenzbackend.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Seit v0.6.1 werden Child Commands vor der Ausführung durch einen gemeinsamen Cross-Platform-Launcher-Resolver aufgelöst. Linux und macOS behalten normales PATH-Verhalten. Windows löst `.exe`, `.cmd` und `.bat` über PATH/PATHEXT auf; ein expliziter `.ps1`-Launcher wird über PowerShell gestartet. Dedizierte Windows-CI führt Codex- und Cursor-Recorder sowohl aus `cmd.exe` als auch aus Windows PowerShell aus; die vollständige Cursor-Semantic/Correlation-Integration bleibt außerdem durch die normale Windows-, macOS- und Ubuntu-Matrix abgedeckt.

Portables Filesystem-Watching ist session-correlated und nicht process-causal; sehr kurzlebige Prozesse können zwischen Polling-Intervallen verpasst werden. Der Linux-`strace`-Pfad liefert nach Beendigung des Commands process-attributed syscall evidence.

Geplante native Collector umfassen Linux eBPF, Windows ETW und macOS Endpoint Security.

## v0.6.2 safety patch

v0.6.2 stärkt die Ressourcensicherheit für lang laufende und high-cardinality Sessions, ohne Evidence-Semantik oder Graph-Schema 0.1 zu ändern:

- Zu breite rekursive Filesystem-Scopes wie Filesystem Root, User Home oder der Parent der User-Homes werden nicht mehr unverändert rekursiv beobachtet; Process-, Network- und Semantic-Collection kann weiterlaufen.
- Standalone- und Live-Viewer stoppen SVG materialization oberhalb des Safety-Budgets (1.500 Nodes, 4.000 Edges oder geschätzt 5.000 SVG-Elemente), um Browser-Memory-Exhaustion zu verhindern. Das kanonische `graph.json`-Evidence-Artefakt bleibt vollständig.
- Viewer layout/fit verteilt keine beliebig großen Arrays mehr an `Math.min` / `Math.max`; Edge-Redraw während Node-Dragging wird auf Animation Frames gedrosselt.
- Der Live-Server tailt nur neu angehängte `events.jsonl`-Bytes ab einem Byte-Offset und aktualisiert einen In-Memory-`GraphAccumulator` inkrementell. `/graph.json`-Polling spielt nicht mehr die gesamte Event-History erneut ab; eine unvollständige letzte JSONL-Zeile wird bis zum Newline gepuffert.
- Reine Event-Count- oder Aggregate-Count-Änderungen aktualisieren Live-Stats/Edge-Labels ohne vollständigen Topology-Redraw. Nach Überschreiten des Viewer-Budgets wechselt live `/graph.json` auf einen kompakten counts-only Payload, während Collection und finale kanonische Validation/full `graph.json` unverändert weiterlaufen.

Dies ist ein Polling + Incremental-Ingestion-Safety-Patch, keine Architektur-Migration zu SSE, SQLite, Rust oder Canvas.

## Geschichtete Artefakte

Ein provider-integrierter Run kann Folgendes erzeugen:

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

Die abgeleitete Correlation-Layer schreibt Raw Evidence niemals um.

## Interactive Viewer

Der Standalone Viewer ist lokal und self-contained. Der aktuelle Baseline umfasst Pan/Zoom, verschiebbare Nodes, Node-/Edge-Inspektion, Node-Type-/Relation-/Causal-Filter, **observed only**, Search, Evidence-Sequence-Replay, progressive Cluster-Expansion, fokussierte Neighborhoods, Saved Views, explizite Edge-Semantik und Correlation Summary.

## Graph-Operationen

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave graph-condense run.graph.json --output compact.graph.json --threshold 8 --keep-expansion
```

## Sicherheitsanalyse

```bash
execweave analyze run.graph.json --output analysis.json
```

Security Findings bleiben hinsichtlich ihrer Evidence-Grenzen explizit. Ein möglicher sensitive-file → network-Pfad beweist keine Byte-Level-Exfiltration:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Aktueller Stand

ExecWeave `main` ist derzeit **v0.6.4** und wird aktiv weiterentwickelt.

Der Baseline umfasst Runtime Collection, Graph-Materialisierung und -Abfragen, Standalone/Live Viewer, Claude/Codex/Gemini/Cursor/OpenCode Semantic Integrations, konservative Tool → Process Correlation, OpenRouter/LiteLLM Gateway Metadata, Ollama/llama.cpp/vLLM/LM Studio Runtime Metadata, exakte Gateway ↔ Model Runtime Request Identity, veröffentlichte PyPI wheel/sdist-Pakete, reproduzierbares Overhead Benchmarking, Cross-Platform Command-Launcher-Kompatibilität, Large-Graph Browser Safety Guards, inkrementelles Live JSONL Tail/Cache und Cross-Platform CI unter Python 3.10/3.12.

## Datenschutz

ExecWeave ist local-first. Runtime Events, Semantic Sidecars, Graphs, Reports und Viewer bleiben standardmäßig lokal. File Contents und rohe Read/Write-Byte-Buffer werden nicht absichtlich erfasst. Native Adapter vermeiden standardmäßig ebenfalls Prompts/Transcripts/Tool Output, aber Commands, Paths, Endpoint Metadata, Identifiers und Model Metadata können weiterhin sensibel sein.

Prüfen Sie Artefakte vor dem Teilen.

## Dokumentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.de.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.de.md)
- [`Live Graph`](docs/live-graph.de.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.de.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.de.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.de.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.de.md)
- [`Cursor Hooks`](docs/cursor-hooks.de.md)
- [`OpenCode Plugin`](docs/opencode-plugin.de.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.de.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.de.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.de.md)

## Mitwirken

Beiträge sind willkommen, insbesondere zu native OS collectors, zusätzlichen Agent/IDE adapters, inference gateways, model runtimes, Entity-/Correlation-Methoden, Privacy/Redaction, Graph UX und Performance Evaluation.

## Lizenz

Siehe [`LICENSE`](LICENSE).