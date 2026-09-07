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

ExecWeave ist ein local-first Observability-Projekt für KI-Agenten und KI-gestützte Entwicklungswerkzeuge. Es verbindet Provider-Semantik mit Betriebssystem-Runtime-Evidence in einem interaktiven Execution Graph und hält die unterschiedlichen Evidenzebenen ausdrücklich getrennt.

> **Events sind Evidence. Der Graph ist eine daraus materialisierte View.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave Live-Dashboard" width="100%">
</p>

## Warum ExecWeave

Ein Agent kann melden, dass er ein Tool verwendet, eine Datei geändert oder einen Dienst kontaktiert hat. Solche Provider-Semantik ist wertvoll, aber nicht dasselbe wie tatsächlich auf Betriebssystemebene beobachtetes Verhalten. ExecWeave zeigt beide Ebenen gemeinsam, ohne ihre Beweiskraft zu vermischen.

- **Ein Dashboard für Live und Finished.** Laufende Ansicht, abgeschlossener Run und standalone `viewer.html` verwenden dasselbe Graph- und Conversation-Modell.
- **Provider-aware Semantik.** Hooks, rollout transcripts, Plugins und Runtime APIs werden genutzt, wenn ein Provider sie tatsächlich bereitstellt.
- **OS Runtime Evidence.** Process, File und Network endpoint können unabhängig von Provider-Aussagen beobachtet werden.
- **Evidence-aware Attribution.** Direct observation, exact identity, konservative inference und causal claim bleiben getrennt.
- **Local-first Storage.** Run artifacts bleiben lokal, solange Sie sie nicht selbst weitergeben.
- **Nicht auf einen Agent beschränkt.** Auch normale lokale Commands lassen sich ohne spezialisierten Adapter beobachten.

## Installation

Installation von PyPI:

```bash
python -m pip install -U execweave
```

Für die Entwicklung:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Schnellstart

Beliebige lokale Commands können mit `execweave live` gestartet werden:

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- python my_agent.py
```

Wenn vor allem finalisierte Artifacts benötigt werden:

```bash
execweave record --open -- python my_agent.py
```

Für eine separate Übersicht, während das gestartete Programm im aktuellen Terminal interaktiv bleibt:

```bash
execweave top -- codex
```

### Provider-Integration freigeben

Einige Agents und IDEs fragen vor dem Aktivieren eines lokalen Hooks oder Plugins nach einer Freigabe. Erlauben Sie die ExecWeave-Integration, wenn Sie Provider-level Evidence zu Prompt, Response, Tool, Model und Conversation sehen möchten. Ohne Freigabe kann OS Runtime Observation weiterhin funktionieren, die semantische Abdeckung ist jedoch möglicherweise geringer.

Google Antigravity verwendet aktuell den CLI-Command `agy`. ExecWeave akzeptiert zusätzlich `antigravity` als besser lesbaren Alias.

Unter Windows folgt ein einfacher `cursor`-Aufruf der Cursor-Installation im PATH des Benutzers. Explizite Launcher-Pfade werden unverändert respektiert.

## Ollama

ExecWeave unterstützt zwei typische lokale Ollama-Workflows.

### Managed server capture

Ollama Server über ExecWeave starten:

```bash
execweave live --open -- ollama serve
```

Danach Ollama in einem anderen Terminal normal verwenden:

```bash
ollama run deepseek-r1:1.5b
```

SDK-Aufrufe, lokale OpenAI-compatible Requests und `curl`-Requests an den managed local endpoint können demselben ExecWeave-Run zugeordnet werden. Das zweite Terminal benötigt keinen weiteren ExecWeave-Wrapper.

Der managed relay ist absichtlich auf lokale Loopback-Endpoints beschränkt und schreibt keine wildcard oder extern exponierten Listener um.

### Direct client capture

Wenn bereits ein Ollama Server läuft, kann der Client direkt gewrappt werden:

```bash
execweave live --open -- ollama run deepseek-r1:1.5b
```

Dieser Modus startet keinen Ollama Server; ein erreichbarer upstream server wird weiterhin benötigt.

## Dashboard

Das Dashboard soll auch große Multi-Agent-Runs lesbar halten, ohne die zugrunde liegende Evidence zu verändern.

- **Execution graph:** Agent, Process, File, Network endpoint, Tool, Model/runtime entity und unterstützte Relations.
- **Conversation rounds:** aktuelle und ältere Runden bleiben dem richtigen Agent zugeordnet und werden nicht durch spätere Messages überschrieben.
- **Node details:** Process identity, File history, Network endpoints, Tools und Provider conversation content lassen sich untersuchen.
- **Stable live updates:** Änderungen erscheinen im selben Document statt durch einen vollständigen Seitenwechsel.
- **Large-run folding:** ältere Mitglieder großer Node-Gruppen können eingeklappt werden und bleiben dennoch inspizierbar.
- **Selection-focused layout:** Graph traffic außerhalb der aktuellen Auswahl wird visuell zurückgenommen.

Für große Runs stehen folgende Grenzen zur Verfügung:

```text
--fold-budget N
--viewer-max-nodes N
--viewer-max-edges N
--viewer-max-dom-elements N
```

## Unterstützte Integrationen

| Integration | OS Runtime Observation | Specialized Evidence |
| --- | --- | --- |
| Claude Code | Ja, wenn unter ExecWeave gestartet | native hooks und vom Provider gelieferter conversation/tool content |
| OpenAI Codex | Ja | lifecycle hooks, validated rollout transcripts, agent/subagent routing wenn exponiert |
| Google Antigravity | Ja | passive hooks und conversation/subagent routing wenn exponiert |
| Cursor | Ja | native hooks und task/subagent routing wenn exponiert |
| OpenCode | Ja | project plugin, session/task routing, supplied plugin content |
| Ollama | Ja | managed local relay und model-runtime evidence |
| llama.cpp | Ja | model-runtime event/exchange/probe |
| vLLM | Ja | model-runtime event/exchange/probe |
| LM Studio | Wenn der lokale Process beobachtbar ist | model-runtime catalog/runtime evidence |
| LiteLLM Proxy | Wenn der lokale Proxy beobachtbar ist | gateway metadata und event integration |
| OpenRouter | Nur lokaler Client | caller-supplied gateway event/exchange evidence |

Provider-Identifier wie tool-call ID, session ID, rollout thread ID oder subagent route sind logische Identitäten und nicht automatisch OS PIDs. ExecWeave verbindet Ebenen nur dann, wenn die verfügbare Evidence den Link unterstützt.

## Evidence Model

ExecWeave trennt mehrere zentrale Ebenen:

```text
Agent / IDE semantics und supplied content
                ↓
Inference gateway / routing evidence
                ↓
Model runtime / inference-server evidence
                ↓
OS runtime evidence: process / file / network
```

Eine Relation wird nur dann als causal markiert, wenn die zugrunde liegende Telemetrie eine Kausalbehauptung tatsächlich stützt. Konservative Bridges bleiben als derived evidence gekennzeichnet:

```text
inferred: true
causal: false
```

Eine exact shared request identity kann Identität belegen, ohne Kausalität zu beweisen:

```text
identity_exact: true
inferred: false
causal: false
```

Bleibt die Attribution unklar, erzeugt ExecWeave lieber keinen Edge als eine stärkere Beziehung zu erfinden.

### Full-fidelity supplied content

Unterstützte Hooks, Plugins und APIs können vollständige, explizit gelieferte Werte in einem lokalen SHA-256 content-addressed store ablegen:

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Je nach Integration können Prompt, Message, Request/Response object, Tool input/result, Assistant response, explizit exponierter reasoning text, Shell output und supplied file content enthalten sein.

`complete_from_source: true` bedeutet, dass ExecWeave den vollständigen Wert gespeichert hat, den dieser Integration Point geliefert hat. Es bedeutet nicht, dass nicht exponierter Model State oder interne Provider-Daten beobachtet wurden.

## Häufige Commands

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

`event` steht für einseitige Event Evidence. `exchange` speichert ein vom caller geliefertes Request/Response-Paar und behauptet keine transparente Wire-Interception.

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

## Run Artifacts

Ein Provider-integrated Run kann enthalten:

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

Raw observations bleiben von derived semantic/correlation outputs getrennt.

## Grenzen und Datenschutz

- Der portable collector läuft unter Linux, macOS und Windows. Portable filesystem observation ist session-correlated und nicht immer process-causal; Polling kann sehr kurzlebige Aktivität verpassen.
- Unter Linux gibt es zusätzlich einen `strace` reference backend mit stärkerer syscall-attributed evidence für unterstützte Executions.
- Provider semantic coverage hängt vollständig davon ab, was die jeweilige Integration tatsächlich exponiert. Nicht exponierte Prompt, hidden reasoning, remote Provider internals oder routing lassen sich nicht zuverlässig rekonstruieren.
- Full-fidelity content kann Credential, Secret, Source code, Prompt, Tool value, Model response, Shell output und File content enthalten.
- Conversation isolation ist eine Attribution Rule, keine Redaction Boundary. Explizit gerouteter Content kann legitimerweise bei mehreren Participants erscheinen.
- Ein lokales integrity manifest erkennt Änderungen relativ zum Manifest, ist aber kein adversary-resistant trusted logging system, wenn Evidence und Manifest in derselben writable trust boundary liegen.
- Prüfen Sie das vollständige Run Directory, bevor Sie es weitergeben.

## Entwicklung

Tests:

```bash
python -m pytest
```

Lint:

```bash
python -m ruff check .
```

Issues und Pull Requests sind willkommen. Neue Integrationen sollten klar zwischen direkt beobachteter, vom Provider gelieferter und abgeleiteter Evidence unterscheiden.

## Lizenz

ExecWeave wird unter der **PolyForm Noncommercial License 1.0.0** bereitgestellt. Die vollständigen Bedingungen stehen in [LICENSE](LICENSE).
