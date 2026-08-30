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

ExecWeave ist ein source-available, local-first Observability-Projekt, das Aktivitäten von KI-Agenten in einen interaktiven execution graph überführt und observed evidence, provider content sowie derived inference ausdrücklich getrennt hält.

> **Das Event ist ground truth. Der Graph ist eine materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## Installation

Installieren Sie das neueste veröffentlichte wheel/sdist von PyPI:

```bash
python -m pip install -U execweave
```

Die aktuelle Version ist **v0.7.6**.

Für die Entwicklung:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Schnellstart

Live OS-runtime telemetry funktioniert mit **jedem lokalen Befehl**. Die folgenden Agent/runtime-Namen sind Beispiele und keine whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Bestätigen Sie den Hook, wenn Sie dazu aufgefordert werden.** Beim ersten provider-integrierten Lauf kann der Agent/die IDE fragen, ob ExecWeave die lokale Hook-Integration aktivieren darf. Wählen Sie **Allow / Yes**. Ohne Freigabe kann OS-runtime telemetry weiterhin funktionieren, provider-level tool-, model- und supplied-content observability ist dann jedoch eingeschränkt oder nicht verfügbar.

Google Antigravity verwendet aktuell den CLI-Befehl `agy`. ExecWeave akzeptiert `antigravity` zusätzlich als freundlichen Alias und löst ihn zu `agy` auf. Bei Cursor versucht `execweave live --open -- cursor` zunächst einen normalen PATH launcher und fällt auf macOS/Windows auf das Standard-Binary der Cursor Desktop-Anwendung zurück.

Für die finalisierte Artifact-Pipeline:

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` hält den Agent im Startterminal interaktiv und öffnet bzw. verbindet gleichzeitig das detached Top dashboard entsprechend der Host-Umgebung.

**v0.7.6 — ein Agent-Panel, das beantwortet, was der Agent gesagt hat, und gestreamte Antworten, die zu einem Datensatz zusammengesetzt werden.** Die Auswahl eines Agents öffnet nun mit dessen eigenen Turns, gelesen als wer was gesagt hat, und behält die provider-neutralen, agent-lokalen Multi-Agent-Conversations bei, die jeder Agent bereits besaß. Aufeinanderfolgende Turns, die ein Provider nicht offengelegt hat, klappen zu einer Zeile zusammen, die weiterhin die adressierten Agents nennt, und die mehrere Kilobyte lange Präambel, die ein Provider jedem Subagent voranstellt, wird gefaltet statt an den Anfang gestellt; Node-Evidence und Trace bleiben eine Offenlegung entfernt. Graph-Labels lösen den deklarierten Path jedes Agents auf, sodass in derselben Millisekunde erzeugte Geschwister nicht mehr als dasselbe Fragment einer zeitgeordneten Id erscheinen. Darunter wird eine gestreamte Antwort zu demselben kanonischen Datensatz zusammengesetzt, den ihr nicht gestreamtes Gegenstück erzeugen würde: über Frames verteilte Texte, Reasoning und Tool Calls werden vor der Materialisierung wieder verbunden, und ein früh beendeter Stream wird als unterbrochen festgehalten.

Das vereinheitlichte Dashboard bringt execution graph, logs und conversation records in denselben Inspection-Flow. Finalisierte Runs erzeugen `conversations.md` und `conversations.json`; validierte Provider-Transcripts werden in den run-local SHA-256 content store kopiert. Claude Code, OpenAI Codex, Cursor, OpenCode und Google Antigravity verwenden jeweils die stärkste Multi-Agent-Evidence, die ihre Integration tatsächlich offenlegt. Wenn ein Gateway oder lokaler Runtime nur root request/response sichtbar macht, zeigt ExecWeave nur diese Root-Conversation und erfindet weder Subagents noch hidden routing.

## v0.6.9: Full-Fidelity Observability mit expliziten Evidence Boundaries

v0.6.9 erweitert Provider-/Runtime-Observability über kompakte Metadata hinaus. Wenn ein unterstützter Integration Point Inhalte ausdrücklich liefert, kann ExecWeave den **vollständig gelieferten Wert** in einem lokalen SHA-256 content-addressed store speichern und im semantic event stream nur eine Reference behalten.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Abhängig vom Adapter und der upstream Hook/API surface können unter anderem prompts/messages, model request/response objects, tool inputs/results, assistant responses, ausdrücklich offengelegter reasoning/thinking text, shell/MCP output und durch Provider-Hooks gelieferter file content gespeichert werden.

`complete_from_source: true` bedeutet lediglich, dass ExecWeave den vollständigen Wert gespeichert hat, den dieser Integration Point geliefert hat. Es bedeutet **nicht**, dass ExecWeave hidden model state, nie offengelegte provider-side stages, einen nicht beobachteten finalen wire request oder nicht abgefangene bytes gesehen hat.

Full fidelity verändert auch die Privacy Boundary: application-level secrets innerhalb des Contents werden mitgespeichert. Bekannte transport credentials werden nur in ausgewählten provider-metadata projections gefiltert, wenn der Adapter dieses Verhalten ausdrücklich definiert. ExecWeave ist **kein** allgemeiner secret scanner oder content redactor.

### Unterstützte Semantic-/Inference-Surfaces

| Integration | OS-runtime observation bei Start unter ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity hook content + vom Provider offengelegte subagent results |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + validierbares conversation/subagent routing |
| Cursor | Yes | native hooks + exact subagent task/summary routing, wenn verfügbar |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | Nur wenn der lokale Process unter ExecWeave gestartet wird | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes, wenn der konfigurierte Proxy unter ExecWeave gestartet wird | metadata-oriented gateway callback/event integration |
| OpenRouter | Beobachtet den lokalen Client, nicht den entfernten Service-Process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` ist caller-supplied request+response evidence und keine transparent wire interception. LiteLLM Proxy bleibt im aktuellen Baseline eine engere metadata-oriented integration. Die provider-neutrale Conversation-Projektion erhebt fehlende Provider-Evidence niemals zu einer erfundenen agent relationship.

## Evidence layers

ExecWeave hält Evidence Layers getrennt, anstatt alle Signale in eine einzige Trace zu flatten:

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Eine Relationship ist nur dann causal, wenn die zugrunde liegende Telemetrie diesen Claim unterstützt. Tool → Process bridges bleiben konservative derived evidence:

```text
inferred: true
causal: false
```

Bei Ambiguität wird kein Edge erzeugt. Eine exact shared request identity zwischen Gateway und Model Runtime bleibt identity evidence statt causal evidence:

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

Provider-integrierte Recorder speichern raw runtime, semantic, correlated und conversation artifacts getrennt. Stabile Provider-Identifier wie Cursor `tool_use_id`, Codex rollout thread identity oder OpenCode `sessionID + callID` belegen logische Provider-Identität; sie sind keine OS PIDs. Cross-agent content wird nur angezeigt, wenn der Provider eine Route, Delegation oder ein Result explizit offenlegt. Legacy Gemini CLI Hook Entry Points bleiben für bestehende Installationen paketiert, neue Google-CLI-Nutzung sollte jedoch Antigravity (`agy`) verwenden.

## Inference gateways und model runtimes

OpenRouter- oder LiteLLM-Gateway-Evidence erfassen:

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Model-runtime evidence für Ollama, llama.cpp, vLLM oder LM Studio erfassen:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` ist response-only evidence. `exchange` speichert ein caller-supplied request+response object und behauptet keine transparente Interception. Runtime catalog relations behalten ihre quellenspezifische Bedeutung: `LOADED_MODEL`, `SERVES_MODEL` und `ADVERTISES_MODEL` sind nicht austauschbar. Die Catalog Visibility von LM Studio bleibt `ADVERTISES_MODEL` und ist kein Beweis dafür, dass Weights resident in memory waren.

## Security analysis, evidence grades und bounded rule packs

Die integrierte Analyse ausführen:

```bash
execweave analyze run.graph.json --output analysis.json
```

Findings enthalten einen von der Severity unabhängigen evidence grade. Aktuelle Grades sind `A`, `B`, `C`, `D` und `U`, von direkter syscall attribution bis inferred/unknown provenance. Diese Grades sind Kategorien der Evidence-Stärke, **keine Wahrscheinlichkeiten oder Trust Scores**.

Lokale Rule Packs fügen begrenzte, erklärbare **single-edge observation** policies hinzu, ohne Third-Party-Code auszuführen:

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule Packs können keinen Code ausführen, keine Regex-/Path-Programme definieren und keinen byte-level data flow oder Exfiltration behaupten. Rule-Pack-Findings bleiben observation-only.

Security Findings machen stärkere Non-Claims weiterhin explizit:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

Einen abgeschlossenen Run seal-en und später prüfen, ob sich sein regular-file inventory gegenüber dem Seal verändert hat:

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Das deterministische Manifest speichert file size/SHA-256 und verweigert symbolic links. Es erkennt fehlende, geänderte, ersetzte oder neu hinzugefügte regular files nach dem Seal.

Dieser local seal wird bewusst **nicht** als adversary-resistant tamper evidence bezeichnet, wenn Evidence und Manifest innerhalb derselben writable trust boundary liegen. Das Manifest vermerkt `malicious_writer_resistance: false` und `external_trust_anchor: false`. Für einen stärkeren Trust Anchor sollte der Manifest-Digest außerhalb dieser Boundary kopiert oder geschützt werden.

## Runtime evidence und graph operations

Der portable Collector läuft unter Linux, macOS und Windows. Linux besitzt zusätzlich einen syscall-backed `strace` reference backend.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation ist session-correlated statt process-causal; Polling kann ausreichend kurzlebige Aktivität verpassen. Linux `strace` liefert für unterstützte Executions stärker process-attributed syscall evidence. Zukünftige native Collectors sind weiterhin für Linux eBPF, Windows ETW und macOS Endpoint Security geplant.

## Performance und Large-Run-Sicherheit

ExecWeave enthält begrenzte filesystem/viewer protections, inkrementelles Live JSONL tailing, large-graph safety guards, detached Top und provisional live sidecars für konfigurierte Provider-Integrationen.

Das reproduzierbare inkrementelle `GraphAccumulator`-Referenzergebnis erreicht **164,273 ev/s** bei 1M synthetic events auf dem dokumentierten GitHub-Actions-Workload. Dies ist ein Graph-Accumulation-Benchmark und kein end-to-end collector/browser throughput.

Führen Sie den package-level overhead benchmark auf einem repräsentativen Host/Workload aus:

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Referenzdaten und Methodik finden Sie unter [`docs/benchmarks/`](docs/benchmarks/).

## Layered artifacts

Ein provider-integrierter Run kann enthalten:

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
└── integrity.json            # nach explizitem Seal
```

Derived correlation schreibt raw runtime oder provider sidecar evidence niemals um.

## Privacy

ExecWeave ist local-first: Captures, content blobs, Graphs, Reports und Viewer bleiben standardmäßig lokal. Der **OS runtime collector** erfasst file contents oder raw read/write byte buffers nicht absichtlich. Diese Boundary darf nicht mit dem in v0.6.9 eingeführten **provider full-fidelity content store** verwechselt werden: Unterstützte Hooks/APIs können prompts, tool arguments/results, model responses, reasoning/thinking text, shell output, file content oder andere sensible Werte ausdrücklich liefern, die ExecWeave vollständig speichern kann.

Conversation isolation ist eine Attribution-/Display-Regel, keine Redaction Boundary. Wenn ein Provider Inhalt von Agent 1 ausdrücklich an Agent 2 sendet, kann diese routed evidence legitimerweise an den beteiligten Endpoints erscheinen. Gehen Sie nicht davon aus, dass Content secret-redacted wurde. Commands, Paths, endpoint metadata, identifiers, model metadata, prompts, tool values und content blobs können sensibel sein. Prüfen Sie das gesamte Run-Verzeichnis vor dem Teilen.

## Aktueller Stand

v0.7.6 kombiniert cross-platform runtime collection, materialized execution graphs, standalone/live dashboards, konservative provider↔runtime correlation, full-fidelity content-addressed provider evidence, attributable multi-agent execution traces, direkten run-local conversation access agent-local conversation isolation in provider-neutralen Projektionen und per-agent conversation focus in den Standalone- und Live-Dashboards. Jede Integration bewahrt nur die stärkste identity/routing evidence, die der Provider tatsächlich offenlegt, und enthält sich, wenn diese Evidence fehlt. Observed evidence und inference bleiben konstruktiv getrennt.

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

Beiträge sind willkommen, insbesondere zu native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, evidence/correlation methods, privacy/redaction, graph UX, multi-agent conversation attribution und performance evaluation.

## License

Seit v0.6.8 steht ExecWeave unter der **PolyForm Noncommercial License 1.0.0**. Nichtkommerzielle Nutzung, Änderung und Weitergabe sind gemäß ihren Bedingungen zulässig. Kommerzielle Nutzung erfordert eine separate schriftliche commercial license vom Licensor. Siehe [`LICENSE`](LICENSE).
