# ExecWeave

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

ExecWeave ist ein source-available, local-first Observability-Projekt, das Aktivitäten von AI Agents in einen interaktiven execution graph umwandelt und observed evidence, provider content sowie derived inference ausdrücklich getrennt hält.

> **Das Event ist die Ground Truth. Der Graph ist eine materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## Installation

Installieren Sie das neueste veröffentlichte wheel/sdist von PyPI:

```bash
python -m pip install -U execweave
```

Die aktuelle stabile Version ist **v0.6.9**.

Für die Entwicklung:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Schnellstart

Live OS-runtime telemetry funktioniert mit **jedem lokalen Befehl**. Die unten genannten Agent-/Runtime-Namen sind Beispiele, keine Whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Bestätigen Sie den Hook, wenn Sie dazu aufgefordert werden.** Beim ersten provider-integrierten Lauf kann der Agent/die IDE fragen, ob ExecWeave die lokale Hook-Integration aktivieren darf. Wählen Sie **Allow / Yes**. Ohne Zustimmung kann OS-runtime telemetry weiterhin funktionieren, aber provider-level Tool-, Model- und supplied-content observability wird eingeschränkt oder nicht verfügbar sein.

Google Antigravity verwendet aktuell den `agy`-CLI-Befehl; ExecWeave akzeptiert auch `antigravity` als Alias und löst ihn zu `agy` auf. Für Cursor verwendet `execweave live --open -- cursor` zuerst einen PATH-Launcher und fällt unter macOS/Windows bei Bedarf auf das standardmäßige Cursor-Desktop-Binary zurück.

Oder erstellen Sie die finalisierte Artifact-Pipeline:

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` hält den Agent im Startterminal interaktiv und öffnet beziehungsweise verbindet das detached Top dashboard entsprechend der Host-Umgebung.

## v0.6.9: Full-fidelity observability mit expliziten Evidence Boundaries

v0.6.9 erweitert die Observability über kompakte Metadaten hinaus. Wenn ein unterstützter Integration Point Inhalte ausdrücklich liefert, kann ExecWeave **den vollständigen von dieser Quelle gelieferten Wert** in einem lokalen SHA-256 content-addressed store bewahren und im semantic event stream nur eine Referenz ablegen.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Je nach Adapter und Upstream-Hook/API-Surface können unter anderem Prompts/messages, Model-request/response-Objekte, Tool-input/result, explizit exponierter reasoning/thinking text, Shell/MCP-output sowie durch Provider-Hooks gelieferter File Content erhalten bleiben.

`complete_from_source: true` bedeutet nur, dass ExecWeave den vollständigen Wert gespeichert hat, den dieser Integration Point geliefert hat. Es bedeutet **nicht**, dass ExecWeave hidden model state, nie exponierte Provider-Stufen, einen ungesehenen finalen Wire Request oder Bytes beobachtet hat, die nicht interceptet wurden.

Full fidelity verändert auch die Privacy Boundary: Application-level secrets, die im Content eingebettet sind, werden mitgespeichert. Bekannte transport credentials werden nur aus ausgewählten provider-metadata projections gefiltert, wenn der jeweilige Adapter dieses Verhalten definiert. ExecWeave ist **kein** allgemeiner Secret Scanner oder Content Redactor.

### Unterstützte Semantic-/Inference-Surfaces

| Integration | OS-runtime observation bei Start unter ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + vom Hook gelieferter full-fidelity content |
| OpenAI Codex | Yes | lifecycle hooks + vom Hook gelieferter full-fidelity content |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks for invocation/tool evidence + full-fidelity values explicitly supplied to those hooks |
| Cursor | Yes | native hooks + vom Hook gelieferter full-fidelity content |
| OpenCode | Yes | project plugin + vom Plugin gelieferter full-fidelity content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | nur wenn der lokale Process durch ExecWeave gestartet wird | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes, wenn der konfigurierte Proxy unter ExecWeave läuft | derzeit metadata-oriented gateway callback/event integration |
| OpenRouter | beobachtet den lokalen Client, nicht den Remote-Service-Process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` ist caller-supplied request+response evidence und keine transparente Wire Interception. LiteLLM Proxy bleibt in der aktuellen Baseline eine schmalere, metadata-orientierte Integration.

## Evidence Layers

ExecWeave hält Evidence Layers getrennt, statt alle Signale in eine einzelne Trace zu glätten:

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Eine Relationship ist nur dann causal, wenn die zugrunde liegende Telemetrie diesen Claim unterstützt. Tool → Process Bridges bleiben konservative derived evidence:

```text
inferred: true
causal: false
```

Bei Ambiguität wird kein Edge erzeugt. Exakte shared request identity zwischen Gateway und Model Runtime bleibt Identity Evidence und keine causal evidence:

```text
identity_exact: true
inferred: false
causal: false
```

## Agent-/IDE-Integrationen

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

Provider-integrierte Recorder halten raw runtime, semantic und correlated artifacts getrennt. Stabile Provider-Identifier wie Cursor `tool_use_id` oder OpenCode `sessionID + callID` belegen logische Identität innerhalb des Providers, sind aber keine OS-PIDs. Legacy Gemini CLI Hook Entry Points bleiben für bestehende Installationen erhalten; neue Google-CLI-Nutzung sollte Antigravity (`agy`) verwenden.

## Inference Gateways und Model Runtimes

Erfassen Sie OpenRouter- oder LiteLLM-Gateway-Evidence:

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Erfassen Sie Model-runtime Evidence für Ollama, llama.cpp, vLLM oder LM Studio:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` ist response-only evidence. `exchange` speichert ein caller-supplied request+response object und behauptet keine transparente Interception. Runtime-Catalog-Relations behalten ihre source-spezifische Bedeutung: `LOADED_MODEL`, `SERVES_MODEL` und `ADVERTISES_MODEL` sind nicht austauschbar. LM-Studio-Catalog-Visibility bleibt `ADVERTISES_MODEL` und beweist nicht, dass Weights resident im Speicher sind.

## Security Analysis, Evidence Grades und begrenzte Rule Packs

Führen Sie die eingebaute Analyse aus:

```bash
execweave analyze run.graph.json --output analysis.json
```

Findings zeigen einen Evidence Grade unabhängig von der Severity. Die aktuellen Grade sind `A`, `B`, `C`, `D` und `U`, von direkter Syscall-Attribution bis zu inferred/unknown provenance. Diese Grade sind Kategorien der Evidenzstärke, **keine Wahrscheinlichkeiten oder Trust Scores**.

Lokale Rule Packs ergänzen begrenzte, erklärbare **Single-edge observation** Policies, ohne Third-party Code auszuführen:

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule Packs können keinen Code ausführen, keine Regex-/Path-Programme definieren und keinen byte-level data flow oder Exfiltration behaupten. Rule-pack Findings bleiben observation-only.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run Integrity

Versiegeln Sie einen abgeschlossenen Run und prüfen Sie später, ob sich sein Regular-file Inventory gegenüber dem Seal verändert hat:

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Das deterministische Manifest speichert File Size/SHA-256 und lehnt symbolische Links ab. Fehlende, veränderte, ersetzte oder neu hinzugekommene reguläre Dateien nach dem Seal führen zu einem Verification Failure.

Dieses lokale Seal wird bewusst **nicht** als adversary-resistant tamper evidence beschrieben, wenn Evidence und Manifest innerhalb derselben writable trust boundary liegen. Das Manifest enthält `malicious_writer_resistance: false` und `external_trust_anchor: false`. Für eine stärkere Garantie muss der Manifest-Digest außerhalb dieser Boundary kopiert oder geschützt werden.

## Runtime Evidence und Graph Operations

Der portable Collector läuft unter Linux, macOS und Windows. Linux bietet zusätzlich einen syscall-basierten `strace` reference backend.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable Filesystem Observation ist session-correlated und nicht process-causal; Polling kann ausreichend kurzlebige Aktivität verpassen. Linux `strace` liefert für unterstützte Ausführungen stärkere process-attributed syscall evidence. Native Collectors für Linux eBPF, Windows ETW und macOS Endpoint Security bleiben geplant.

## Performance und Large-run Safety

ExecWeave umfasst begrenzte filesystem/viewer protections, inkrementelles Live-JSONL-Tailing, large-graph safety guards, detached Top und provisorische Live-Sidecars für konfigurierte Provider-Integrationen.

Das reproduzierbare inkrementelle `GraphAccumulator`-Referenzergebnis erreicht bei 1M synthetischen Events auf dem dokumentierten GitHub-Actions-Workload **164,273 ev/s**. Dies ist ein Graph-Accumulation-Benchmark und kein End-to-end Collector-/Browser-Throughput.

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Referenzdaten und Methodik: [`docs/benchmarks/`](docs/benchmarks/).

## Layered Artifacts

Ein provider-integrierter Run kann enthalten:

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
└── integrity.json            # nach einem expliziten Seal
```

Derived correlation schreibt die rohe Runtime- oder Provider-Sidecar-Evidence niemals um.

## Privacy

ExecWeave ist local-first: Captures, Content Blobs, Graphen, Reports und Viewer bleiben standardmäßig lokal. Der **OS runtime collector** erfasst File Content oder rohe Read/write Byte Buffers nicht absichtlich. Diese Boundary darf nicht mit dem **provider full-fidelity content store** aus v0.6.9 verwechselt werden: Wenn ein unterstützter Hook/API ausdrücklich Prompt, Tool-Argumente/-Ergebnisse, Model Response, reasoning/thinking text, Shell Output, File Content oder andere sensitive Werte liefert, kann ExecWeave diese vollständig bewahren.

Gehen Sie nicht davon aus, dass Content secret-redacted ist. Commands, Paths, Endpoint Metadata, Identifier, Model Metadata, Prompts, Tool Values und Content Blobs können alle sensitiv sein. Prüfen Sie das gesamte Run Directory vor dem Teilen.

## Aktueller Status

v0.6.9 kombiniert cross-platform runtime collection, materialisierte Execution Graphs, standalone/live Viewing, konservative Provider↔Runtime-Korrelation, content-addressed full-fidelity Provider Evidence, Evidence Grades, begrenzte Rule Packs, einen expliziten Runtime Threat/Fidelity Contract und ehrliches lokales Run-integrity Sealing. Observed evidence und inference bleiben per Design getrennt.

## Dokumentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.de.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.de.md)
- [`Live Graph`](docs/live-graph.de.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.de.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.de.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.de.md)
- [`Google Antigravity Hooks`](docs/antigravity-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.de.md)
- [`OpenCode Plugin`](docs/opencode-plugin.de.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.de.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.de.md)
- [`Runtime Threat Model`](docs/runtime-threat-model.de.md)
- [`Evidence Grades`](docs/evidence-grades.de.md)
- [`Rule Packs`](docs/rule-packs.de.md)
- [`Run Integrity`](docs/run-integrity.de.md)
- [`Security Analysis`](docs/security-analysis.de.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## Mitwirken

Beiträge sind willkommen, besonders zu nativen OS Collectors, Agent-/IDE-Adaptern, Inference Gateways, Model Runtimes, Evidence-/Correlation-Methoden, Privacy/Redaction, Graph UX und Performance Evaluation.

## License

ExecWeave steht unter der **PolyForm Noncommercial License 1.0.0**. Nichtkommerzielle Nutzung, Änderung und Weiterverteilung sind gemäß den Lizenzbedingungen gestattet. Kommerzielle Nutzung erfordert eine separate schriftliche kommerzielle Lizenz des Lizenzgebers. Siehe [`LICENSE`](LICENSE).
