<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <a href="gemini-hooks.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Gemini CLI Hooks

ExecWeave kann Lifecycle-/Tool-Hooks der Gemini CLI als semantische Provider-Belege aufnehmen und mit unabhängig gesammelten OS-Laufzeitbelegen kombinieren.

Der Adapter ist bewusst konservativ: Gemini-Hook-Belege beschreiben, was der Provider auf Agent-/Tool-Ebene meldet. Sie beweisen nicht für sich, welcher OS-Prozess die Arbeit ausgeführt hat.

## Unterstützte Hook-Ereignisse

Der aktuelle Adapter verarbeitet:

- `SessionStart`
- `BeforeTool`
- `AfterTool`

Gemini CLI sendet die Hook-Eingabe als JSON über `stdin`. Ein erfolgreicher Command Hook muss gültiges JSON auf `stdout` zurückgeben; ExecWeave gibt deshalb bei Erfolg exakt `{}` zurück und schreibt Warnungen nur auf `stderr`.

Erzeugen Sie ein Einstellungsfragment mit:

```bash
execweave-gemini-hook --print-config
```

Fügen Sie das erzeugte `hooks`-Objekt in die `settings.json` der Gemini CLI ein.

Die erzeugte Konfiguration beobachtet alle Tools mit `BeforeTool`-/`AfterTool`-Matchern und blockiert oder verändert den Tool-Aufruf nicht.

## Aufzeichnung mit einem Befehl

Nach der Hook-Konfiguration:

```bash
execweave-gemini-record --open -- gemini
```

Der Recorder bindet den Gemini-Kindprozess über `EXECWEAVE_SEMANTIC_SIDECAR` an einen laufbezogenen semantischen Sidecar und verwendet anschließend die gemeinsame Provider-Record-Pipeline:

```text
Laufzeitbelege
      +
Gemini-Hook-Belege
      ↓
validiertes semantisches Merge
      ↓
konservative Korrelation
      ↓
Graph + Viewer
```

Ein providerintegrierter Lauf kann erzeugen:

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

Rohe Laufzeitbelege und Provider-Sidecar-Belege bleiben getrennt. Korrelation erzeugt einen abgeleiteten Strom, statt beobachtete Eingabebelege umzuschreiben.

## Ereigniszuordnung

### Sitzungsstart

`SessionStart` wird zu einem Provider-Sitzungsbeleg:

```text
Gemini CLI --STARTED_PROVIDER_SESSION--> provider_session
```

ExecWeave behält die für die Zuordnung nötigen Sitzungsmetadaten, liest oder kopiert aber nicht das von `transcript_path` referenzierte Transcript.

### BeforeTool

Ein `BeforeTool`-Hook erzeugt semantische Beziehungen wie:

```text
Gemini CLI --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Für das eingebaute Tool `run_shell_command` wird `tool_input.command` dargestellt als:

```text
tool_call --DECLARED_COMMAND--> command
```

Dieser Befehlsbeleg kann an derselben konservativen Tool → Process-Korrelation teilnehmen wie bei den anderen Provider-Adaptern.

Für ausgewählte Datei-Tools wie `read_file`, `write_file` und `replace` kann ExecWeave den deklarierten Zielpfad als semantische Metadaten speichern. Dateiinhalte werden nicht erfasst.

### MCP-Tools

Wenn Gemini CLI `mcp_context` bereitstellt, verwendet ExecWeave die explizit vom Provider gemeldete Server-/Tool-Identität:

```text
tool_call --VIA_MCP--> mcp_server
mcp_server --EXPOSES_TOOL--> tool
```

Der Adapter speichert MCP-Startbefehl, Argumente oder URL aus `mcp_context` nicht, da diese Felder sensible Verbindungsmetadaten oder Zugangsdaten enthalten können.

### AfterTool

`AfterTool` wird als separate `tool_result`-Beobachtung aufgezeichnet.

Wenn `tool_response.error` nicht leer ist, zeichnet der Adapter ein vom Provider gemeldetes Fehlersignal auf. Andernfalls zeichnet er ein neutrales Rückgabesignal auf.

ExecWeave speichert **weder** rohes `llmContent`, `returnDisplay` noch den Provider-Fehlertext.

## Keine eindeutige Gemini-Tool-Aufruf-ID

Das aktuelle Gemini-CLI-Hook-Eingabeschema liefert `tool_name`, `tool_input` und optionalen MCP-Kontext, stellt aber keine eindeutige Tool-Aufruf-ID bereit, die zwischen `BeforeTool` und `AfterTool` geteilt wird.

ExecWeave behauptet daher **keine** direkte BeforeTool → AfterTool-Identitätskante.

Jede `BeforeTool`-Anfrage erhält eine zeitstempelgebundene lokale Identität. `AfterTool` erzeugt einen unabhängigen Ergebnisknoten. Beide können einen deterministischen `tool_fingerprint` tragen, der aus Toolname + normalisierter Eingabe abgeleitet wird und als Diagnosehinweis dient. Dieser Fingerprint wird jedoch **nicht als Aufrufidentität behandelt**. Wiederholte identische Befehle müssen unterscheidbar bleiben.

## Tool → Process-Korrelation

Gemini-Hooks liefern nicht die OS-Kindprozess-PID, die nötig wäre, um Tool → Process-Zuordnung zu beweisen.

Ein korrelierter Graph darf enthalten:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

nur wenn der bestehende begrenzte Matcher anhand unabhängiger Laufzeitbelege genau einen eindeutig gestützten Prozesskandidaten findet.

Jede solche Brücke bleibt:

```text
inferred: true
causal: false
```

Mehrdeutige, nicht passende, zusammengesetzte, Shell-Builtin- oder nicht unterstützte Befehle erzeugen keine Brücke.

Der korrelierte Viewer zeigt Anzahlen für matched / ambiguous / no-match / unsupported, damit eine fehlende Kante nicht stillschweigend als „nichts ist passiert“ interpretiert wird.

## Datenschutzgrenze

Der native Gemini-Adapter vermeidet absichtlich:

- Prompt-Inhalte
- Transcript-Inhalte
- rohe Tool-Ergebnisinhalte
- rohe Provider-Fehlertexte
- MCP-Befehls-/Argument-/URL-Details
- Dateiinhalte

Er kann weiterhin Metadaten wie Befehlstext, deklarierte Dateipfade, Toolnamen, Sitzungsidentifikatoren und MCP-Server-/Toolnamen speichern. Prüfen Sie Artefakte vor der Weitergabe.

## Fehlerverhalten

`execweave-gemini-hook` ist standardmäßig fail-open. Telemetriefehler werden auf `stderr` geschrieben und blockieren den Gemini-Tool-Aufruf nicht absichtlich.

Verwenden Sie `--strict` nur, wenn ein von null verschiedener Telemetrie-Exit-Code gewünscht ist.

## Aktueller Upstream-Vertrag

Dieser Adapter folgt der aktuellen Gemini-CLI-Hook-Referenz:

- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md

Provider-Hook-Schemata können sich weiterentwickeln. ExecWeave zeichnet nur Felder auf, die der Provider tatsächlich liefert, und hält die unabhängige OS-Laufzeiterfassung auch dann nützlich, wenn semantische Hooks nicht verfügbar sind.

Siehe auch [`Semantische Telemetrie`](semantic-telemetry.de.md).
