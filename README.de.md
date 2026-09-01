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

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**Sehen Sie, was KI-Agenten auf Ihrem Rechner tatsächlich tun.**

ExecWeave ist ein source-available, local-first Observability-Projekt, das Aktivitäten von KI-Agenten in einen interaktiven execution graph überführt und observed evidence, ausdrücklich vom Provider bereitgestellten Content sowie derived inference klar voneinander trennt.

> **Das Event ist ground truth. Der Graph ist eine materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

Dieses README dokumentiert **v0.8.4**.

## Warum ExecWeave

- **Eine lokale Inspection-Oberfläche.** Live runs, abgeschlossene runs und das standalone `viewer.html` verwenden denselben dashboard renderer für graph, logs, conversations und node details.
- **Evidence-aware by design.** Direct observations, identity links, konservative inference und causal claims bleiben unterscheidbar, statt zu einer einzigen Beziehungsart abgeflacht zu werden.
- **Provider-aware, ohne verborgenes Verhalten zu erfinden.** ExecWeave verwendet nur routing / identity evidence, die ein Provider tatsächlich offenlegt; fehlende Evidence bleibt fehlend.
- **Nicht auf einen einzelnen Agent beschränkt.** OS-runtime telemetry kann jeden lokalen command umschließen; Provider adapters ergänzen reichere semantic evidence, wenn sie unterstützt werden.

## Installation

Installieren Sie das neueste veröffentlichte Package von PyPI:

```bash
python -m pip install -U execweave
```

Für die Entwicklung:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Schnellstart in 60 Sekunden

Live OS-runtime telemetry funktioniert mit **jedem lokalen command**. Die folgenden Agent/runtime-Namen sind Beispiele und keine whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Bestätigen Sie den Hook, wenn Sie dazu aufgefordert werden.** Beim ersten provider-integrated run kann Agent/IDE fragen, ob ExecWeave seine lokale Hook integration aktivieren darf. Wählen Sie **Allow / Yes**. Ohne Freigabe kann OS-runtime telemetry weiterhin funktionieren, aber provider-level tool-, model-, conversation- und supplied-content-observability kann eingeschränkt oder nicht verfügbar sein.

Google Antigravity verwendet derzeit den CLI command `agy`. ExecWeave akzeptiert `antigravity` außerdem als friendly alias und löst ihn zu `agy` auf. Für Cursor versucht `execweave live --open -- cursor` zunächst einen normalen PATH launcher und fällt bei Bedarf unter macOS und Windows auf das Standard-Binary der Cursor-Desktopanwendung zurück.

Finalized run artifacts erzeugen Sie mit:

```bash
execweave record --open -- python my_agent.py
```

Für eine detached overview, während der Agent im Start-Terminal interaktiv bleibt:

```bash
execweave top -- codex
```

## Dashboard

ExecWeave wechselt am Ende eines runs nicht zu einem anderen Viewer. Live, finished und standalone viewing beruhen auf demselben dashboard model.

- **Execution graph:** zeigt agents, processes, files, network endpoints, tools, model/runtime entities und unterstützte semantic relations.
- **Conversation rounds:** der neueste round ist sofort lesbar; ältere rounds bleiben einzeln erreichbar und werden nicht von neueren Antworten überschrieben.
- **Node details:** process nodes zeigen command / PID context, file nodes path / history context und network nodes endpoint / process context.
- **Large-run readability:** überschreitet ein Typ sein Budget, bleiben die neuesten Mitglieder sichtbar und ältere werden in einem inspizierbaren Aggregate zusammengefasst. Der Grenzwert wird mit `--fold-budget N` gesetzt.
- **Selection clarity:** das multi-agent layout behält eine stabile root / child hierarchy und blendet bei Auswahl eines Agents nicht zugehörige edges ab.

### Dashboard-Änderungen in v0.8.3

v0.8.3 verbessert die Lesbarkeit dichter und multi-round runs, ohne raw evidence zu verändern:

- conversation panels sind round-basiert und koppeln keinen alten prompt mehr an eine neue reply;
- ein vom Leser explizit gewählter open / closed state bleibt über den 800-ms-Live-refresh erhalten;
- subagent responses bleiben dem Agent zugeordnet, der sie tatsächlich erzeugt hat;
- die Auswahl von process, file oder network öffnet kein leeres detail panel mehr;
- node types mit hoher Kardinalität werden anhand eines konfigurierbaren Budgets gefaltet, statt den graph mit Hunderten oder Tausenden nodes zu überfüllen;
- lifecycle return edges verzerren den root / child rank nicht mehr, und shared tool/model traffic nutzt klarere routed geometry.

Diese Änderungen betreffen nur die presentation layer. Raw graph evidence bleibt unverändert, und Live, finished sowie `viewer.html` teilen weiterhin denselben renderer.

## Unterstützte Integrationen

| Integration | OS-runtime observation beim Start unter ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content + exact subagent results, wenn der Provider sie offenlegt |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + conversation/subagent routing, wenn es validiert werden kann |
| Cursor | Yes | native hooks + exact subagent task/summary routing, wenn verfügbar |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | Nur wenn der lokale process unter ExecWeave gestartet wird | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes, wenn der konfigurierte Proxy unter ExecWeave gestartet wird | metadata-oriented gateway callback/event integration |
| OpenRouter | Beobachtet den lokalen client, nicht den remote service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

Stable provider identifiers wie Cursor `tool_use_id`, Codex rollout thread identity oder OpenCode `sessionID + callID` belegen logical provider identity; sie sind keine OS PIDs. Cross-agent content wird nur gezeigt, wenn der Provider eine explizite route, delegation oder result offenlegt. Gateways oder local runtimes, die nur root request/response traffic liefern, bleiben root-only; ExecWeave erfindet keine subagents oder hidden routing.

OpenRouter `exchange` ist caller-supplied request+response evidence und keine transparent wire interception. LiteLLM Proxy bleibt im aktuellen Baseline eine engere metadata-oriented integration. Legacy Gemini CLI entry points bleiben aus Kompatibilitätsgründen paketiert, neue Google-CLI-Nutzung sollte jedoch Antigravity (`agy`) verwenden.

## Evidence model

ExecWeave hält evidence layers getrennt, statt alle Signale in eine einzelne Trace abzuflachen:

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Eine relationship ist nur causal, wenn die zugrunde liegende Telemetrie diesen claim tatsächlich stützt. Konservative Tool → Process bridges bleiben als derived evidence markiert:

```text
inferred: true
causal: false
```

Eine exact shared request identity zwischen Gateway und Model Runtime ist identity evidence und keine causal evidence:

```text
identity_exact: true
inferred: false
causal: false
```

Bei Mehrdeutigkeit wird kein edge erzeugt.

### Full-fidelity supplied content

Seit **v0.6.9** können unterstützte integration points den vollständigen Wert, den Provider / Hook / API ausdrücklich bereitstellen, in einem lokalen SHA-256 content-addressed store bewahren, während der semantic event stream nur eine reference enthält:

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Je nach Integration können gespeicherte Werte prompt/message, request/response objects, tool input/result, assistant response, ausdrücklich offengelegten reasoning/thinking text, shell/MCP output und von provider hooks bereitgestellten file content enthalten.

`complete_from_source: true` bedeutet nur, dass ExecWeave den vollständigen Wert gespeichert hat, den dieser integration point geliefert hat. Es bedeutet **nicht**, dass ExecWeave hidden model state, nie offengelegte provider-side stages, eine unbeobachtete final wire request oder nicht interceptete bytes gesehen hat.

## Häufige Befehle

### Agent / IDE recorders

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateways und model runtimes

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl

execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` ist response-only evidence. `exchange` speichert ein caller-supplied request+response object und behauptet keine transparent interception. Runtime catalog relations behalten ihre source-specific Bedeutung: `LOADED_MODEL`, `SERVES_MODEL` und `ADVERTISES_MODEL` sind nicht austauschbar. LM Studio catalog visibility bleibt `ADVERTISES_MODEL` und ist kein Beweis dafür, dass weights resident in memory waren.

### Runtime, graph, security und integrity

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

Der evidence grade eines security findings ist unabhängig von seiner severity. Aktuelle grades sind `A`, `B`, `C`, `D` und `U`; sie sind evidence-strength categories und keine probabilities oder trust scores. Rule packs sind bounded, explainable single-edge observation policies; sie führen keinen third-party code aus und beweisen keine byte-level exfiltration.

## Run artifacts

Ein provider-integrated run kann enthalten:

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

Derived correlation schreibt raw runtime oder provider sidecar evidence niemals um.

## Grenzen und Datenschutz

- Der portable collector läuft unter Linux, macOS und Windows. Portable filesystem observation ist session-correlated statt process-causal, und Polling kann ausreichend kurzlebige Aktivität verpassen.
- Linux besitzt zusätzlich ein syscall-backed `strace` reference backend mit stärkerer process-attributed syscall evidence für unterstützte executions.
- Native Linux eBPF-, Windows ETW- und macOS Endpoint Security collectors bleiben planned work und sind keine derzeit beanspruchten Fähigkeiten.
- Full-fidelity provider content kann Secrets bewahren, die in prompts, tool values, model responses, shell output oder supplied files eingebettet sind. ExecWeave ist **kein** allgemeiner secret scanner oder content redactor.
- Conversation isolation ist eine attribution/display rule und keine redaction boundary. Routet ein Provider Content ausdrücklich zwischen Agents, kann dieser Content an den beteiligten endpoints berechtigterweise erscheinen.
- Commands, paths, endpoints, identifiers, model metadata, prompts, tool values und content blobs können alle sensibel sein. Prüfen Sie das gesamte run directory vor dem Teilen.
- Ein local integrity seal erkennt Dateiänderungen relativ zu seinem manifest, ist aber nicht adversary-resistant, wenn Evidence und Manifest innerhalb derselben writable trust boundary bleiben.

## Performance

ExecWeave enthält bounded filesystem/viewer protections, incremental Live JSONL tailing, large-graph safety guards, detached Top und provisional live sidecars für konfigurierte provider integrations.

Das reproduzierbare Referenzergebnis des inkrementellen `GraphAccumulator` erreicht **164,273 ev/s** bei 1M synthetic events auf dem dokumentierten GitHub-Actions-workload. Dies ist ein graph-accumulation benchmark und kein end-to-end collector/browser throughput.

Führen Sie die package-level benchmarks auf einem repräsentativen host/workload aus:

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data und methodology finden Sie unter [`docs/benchmarks/`](docs/benchmarks/).

## Dokumentation

| Bereich | Dokumente |
| --- | --- |
| Runtime und graph | [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md) · [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md) · [`Live Graph`](docs/live-graph.md) · [`Semantic Telemetry`](docs/semantic-telemetry.md) |
| Agent / IDE integrations | [`Claude Code`](docs/claude-code-hooks.md) · [`OpenAI Codex`](docs/codex-hooks.md) · [`Google Antigravity`](docs/antigravity-hooks.md) · [`Cursor`](docs/cursor-hooks.md) · [`OpenCode`](docs/opencode-plugin.md) |
| Gateways und runtimes | [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md) · [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md) |
| Trust und analysis | [`Runtime Threat Model`](docs/runtime-threat-model.md) · [`Evidence Grades`](docs/evidence-grades.md) · [`Rule Packs`](docs/rule-packs.md) · [`Run Integrity`](docs/run-integrity.md) · [`Security Analysis`](docs/security-analysis.md) |
| Performance | [`Benchmarks`](docs/benchmarks/README.md) |

## Mitwirken

Beiträge sind willkommen, insbesondere zu native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, evidence/correlation methods, privacy/redaction, graph UX, multi-agent conversation attribution und performance evaluation.

## Lizenz

Seit v0.6.8 steht ExecWeave unter der **PolyForm Noncommercial License 1.0.0**. Nichtkommerzielle Nutzung, Änderung und Weiterverteilung sind gemäß ihren Bedingungen erlaubt. Kommerzielle Nutzung erfordert eine separate schriftliche commercial license des Licensors. Siehe [`LICENSE`](LICENSE).
