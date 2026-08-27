<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <a href="claude-code-hooks.zh-CN.md">简体中文</a> |
  <a href="claude-code-hooks.ja.md">日本語</a> |
  <a href="claude-code-hooks.ko.md">한국어</a> |
  <a href="claude-code-hooks.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="claude-code-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Claude Code Hooks

ExecWeave enthält einen nativen Claude-Code-command-hook Adapter. Er schreibt vom Provider gelieferte semantic/content evidence in einen lokalen Sidecar und hält sie von unabhängiger OS runtime evidence getrennt. Provider Hooks erklären, was Claude Code ausdrücklich exponiert hat; sie ersetzen weder den portablen noch den Linux-`strace` Collector und belegen für sich allein keine OS process causality.

**Aktuelle Hook Surface.** `execweave-claude-hook --print-config` registriert derzeit:

- `SessionStart`
- `UserPromptSubmit`
- `MessageDisplay`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PostToolBatch`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `StopFailure`

Die Hook-Konfiguration ist standardmäßig fail-open: Telemetrie-/Storage-Fehler werden gemeldet, ohne eine Agent Operation absichtlich zu blockieren. Für Debugging kann `--strict` einen non-zero Telemetrie-Exit erzwingen.

## Konfiguration und Aufzeichnung

Installieren Sie ExecWeave, erzeugen Sie das unterstützte Settings Fragment, fügen Sie es in die Claude-Code-Settings ein und verwenden Sie dann den run-bound Recorder:

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

`execweave-claude-record` bindet über die Child-Environment einen für den Run eindeutigen semantic sidecar. Runtime-, semantic- und correlated evidence bleiben separate Artifacts.

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

Wenn kein unterstütztes Claude Hook Event eintrifft, fällt der Recorder auf runtime-only Artifacts zurück. Existiert semantic evidence, aber kein eindeutig unterstützter Tool → Process Candidate, wird kein Bridge erfunden.

## Full-fidelity Content in v0.6.5

Der Claude Adapter ist nicht mehr auf begrenzte Metadata Summaries beschränkt. Wenn der Hook Content ausdrücklich liefert, speichert v0.6.5 den vollständigen von der Quelle gelieferten Wert im lokalen SHA-256 content-addressed store und legt im semantic sidecar nur eine Referenz ab.

Abgedeckte Regressions umfassen:

- vollständiges `UserPromptSubmit.prompt`, einschließlich großer Werte;
- vollständigen Tool Input einschließlich `Write`/`Edit` Content und application-level values im Input Object;
- vollständiges strukturiertes `PostToolUse.tool_response`, sofern geliefert;
- vom `PostToolBatch` gelieferte model-visible Tool-result Serialization;
- `MessageDisplay` Assistant Text/Delta mit verfügbaren Ordering Metadata;
- finale Assistant Messages des Main Agent und von Subagents aus Stop Events.

Bekannte transport credentials werden nur aus der separaten provider-metadata projection gefiltert, sofern der Adapter sie erkennt. Diese Filterung **sanitiert den Full Content selbst nicht**. Ein Secret in Prompt, Tool Input, File Body, Tool Result oder Assistant Message bleibt Bestandteil der erhaltenen full-fidelity evidence.

`content_complete_from_source: true` bedeutet, dass ExecWeave den vollständigen durch den Claude Hook gelieferten Wert gespeichert hat. Es bedeutet nicht, dass ExecWeave ein nicht geliefertes Transcript gelesen, hidden model state beobachtet oder Provider-Stufen erfasst hat, die im Hook Payload nicht vorhanden waren.

## Logische Entitäten und Tool Identity

Claude Hook Events können Provider-level Relationships wie diese materialisieren:

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL-------------> tool
tool_call --DECLARED_COMMAND------> command
tool_call --DECLARED_TARGET-------> file metadata
tool_call --VIA_MCP---------------> mcp_server
Claude Code --SPAWNED_SUBAGENT----> subagent
```

`tool_use_id` kann eine logische Tool Invocation identifizieren, ist aber kein OS PID. MCP-Namen nach der Provider-Konvention `mcp__<server>__<tool>` werden, sofern vorhanden, in separate MCP-server/tool Entities normalisiert.

## Tool → Process Correlation Boundary

Der Claude command-hook Input liefert nicht den tatsächlichen Child Process PID einer Bash-/PowerShell-Tool-Invocation. ExecWeave erzeugt daher aus Provider Hook Data allein keinen observed causal process edge.

Ein derived bridge kann nur entstehen, wenn der begrenzte Runtime Matcher genau einen unterstützten Process Candidate findet:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Jeder Bridge behält folgende Semantik:

```json
{
  "causal": false,
  "inferred": true,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

Temporal Proximity allein reicht nicht. Ambiguous Candidates, nicht unterstützte Compound Commands, Shell Builtins oder unmatched Declarations erzeugen keinen Bridge. Inference wird niemals zu observed process attribution hochgestuft.

## Layered Artifacts

Eine run-bound Claude Capture kann erzeugen:

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
└── viewer.correlated.html
```

Correlation schreibt ursprüngliche Runtime- oder Provider-Evidence nicht um.

## Standalone Sidecar

Außerhalb des run-bound Recorders ist der Standard-Claude-Sidecar session-scoped:

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

`EXECWEAVE_SEMANTIC_SIDECAR` oder `--sidecar` können diesen Pfad überschreiben. Für parallele Captures sind session-/run-spezifische Pfade empfohlen.

## Privacy und Evidence Boundary

Claude full-fidelity Artifacts können Prompts, Commands, File Paths, `Write`/`Edit` Bodies, Tool Arguments/Results, Assistant Text, Subagent Responses, Identifier und application-level secrets enthalten. Behandeln Sie das gesamte Run Directory als sensitiv und prüfen Sie es vor dem Teilen.

Provider Content bleibt Provider Evidence. Ein gespeicherter Tool Input beweist keine Tool-Ausführung; ein gespeicherter File Body beweist nicht, dass ein bestimmter OS Process ihn gelesen oder geschrieben hat; ein gespeichertes Tool Result beweist keinen byte-level data flow. Stärkere Claims benötigen OS Collectors und ausdrücklich markierte Correlation Evidence.

## Manueller Merge und Correlation

Wenn Runtime- und Semantic-Files bereits vorliegen, bleibt die generische Pipeline verfügbar:

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl --output run.correlated.jsonl
execweave validate run.correlated.jsonl
```

Siehe [`Semantic Telemetry`](semantic-telemetry.de.md) für den generischen Evidence-/Content-Contract und Process-reference Rules.
