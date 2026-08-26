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

ExecWeave enthält einen nativen Claude-Code-Command-Hook-Adapter, der semantische Provider-Telemetrie in einem separaten lokalen JSONL-Sidecar aufzeichnet.

Der Adapter ergänzt die OS-Laufzeiterfassung. Er ersetzt **weder** den portablen noch den Linux-`strace`-Collector.

## Was aufgezeichnet wird

Der aktuelle Adapter verarbeitet folgende Claude-Code-Hook-Ereignisse:

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

Er kann semantische Entitäten wie diese materialisieren:

```text
Claude Code
  |
  +--REQUESTED_TOOL_CALL--> tool_call
  |                           |
  |                           +--USES_TOOL-------> Bash / Read / Edit / Write / ...
  |                           +--DECLARED_COMMAND-> command
  |                           +--DECLARED_TARGET--> file metadata
  |                           +--VIA_MCP----------> MCP server
  |
  +--SPAWNED_SUBAGENT-------> subagent
  +--USED_MODEL-------------> model        when SessionStart exposes one
```

MCP-Toolnamen nach Claudes Konvention `mcp__<server>__<tool>` werden in getrennte `mcp_server`- und `tool`-Knoten normalisiert.

## Hook-Konfiguration installieren

Installieren Sie zunächst ExecWeave, damit die Konsolenskripte verfügbar sind:

```bash
python -m pip install -e ".[dev]"
```

Erzeugen Sie das Konfigurationsfragment:

```bash
execweave-claude-hook --print-config
```

Fügen Sie das erzeugte `hooks`-Objekt in eine der von Claude Code unterstützten JSON-Einstellungsdateien ein:

- `~/.claude/settings.json` für benutzerweite Hooks
- `.claude/settings.json` für eine teilbare Projektkonfiguration
- `.claude/settings.local.json` für eine lokale Projektkonfiguration, die nicht committed werden sollte

Überschreiben Sie beim Hinzufügen des Fragments keine anderen Claude-Code-Einstellungen.

Mit Claudes `/hooks`-Menü können Sie prüfen, welche Hooks aktuell konfiguriert sind.

Der Adapter verwendet Command Hooks und ist standardmäßig fail-open: Fehler beim Parsen der Telemetrie oder im Dateisystem werden auf stderr geschrieben, liefern aber Erfolg zurück, damit ExecWeave-Observability keinen Agent-Tool-Aufruf blockiert. `--strict` dient dem Debugging des Hooks selbst, nicht als Laufzeit-Sicherheitsrichtlinie.

## Empfohlen: Laufzeit + Semantik + Korrelation mit einem Befehl

Nachdem die Hooks installiert sind, verwenden Sie den laufgebundenen Workflow:

```bash
execweave-claude-record --open -- claude
```

Unter Linux bevorzugt `--backend auto` weiterhin das stärkere `strace`-Backend, sofern verfügbar. Unter macOS und Windows wird das portable Backend verwendet.

`execweave-claude-record` bindet **innerhalb des dedizierten CLI-Prozesses** einen für diesen ExecWeave-Lauf eindeutigen Sidecar-Pfad. Claude und seine Hook-Befehle erben diesen Pfad. Zwei unabhängig gestartete ExecWeave-Claude-Record-Prozesse müssen daher nicht erraten, welcher semantische Sidecar zu welcher Laufzeiterfassung gehört.

Wenn Claude semantische Hook-Ereignisse ausgibt, führt der Recorder drei explizite Belegstufen aus:

```text
Laufzeitbelege
    ↓ semantisches Merge
Laufzeit- + semantische Belege
    ↓ konservative Korrelation
Laufzeit + Semantik + inferierte Korrelation
```

Das Laufverzeichnis hält jede Stufe getrennt:

```text
.execweave/runs/<run-id>/
├── events.jsonl              # nur Laufzeitbelege
├── graph.json                # nur Laufzeitgraph
├── viewer.html               # nur Laufzeit-Viewer
├── semantic.jsonl            # nur semantische Claude-Hook-Belege
├── events.semantic.jsonl     # validierter Laufzeit- + Semantikstrom
├── graph.semantic.json       # Laufzeit- + Semantikgraph
├── viewer.semantic.html      # Laufzeit- + Semantik-Viewer
├── events.correlated.jsonl   # Laufzeit + Semantik + inferierte Brücken
├── graph.correlated.json     # Graph einschließlich inferierter Brücken
└── viewer.correlated.html    # Viewer mit separat dargestellten inferierten Kanten
```

`--open` öffnet `viewer.correlated.html`, wenn semantische Belege beobachtet wurden. Wenn die Hooks nicht installiert sind oder kein unterstütztes Hook-Ereignis ausgelöst wird, meldet ExecWeave `semantic_status: "no_events"`, `correlation_status: "not_run_no_semantic_events"` und fällt auf den reinen Laufzeit-Viewer zurück.

Wenn semantische Belege vorhanden sind, aber kein eindeutiger sicherer Tool → Process-Kandidat übrig bleibt, erzeugt ExecWeave trotzdem die korrelierten Artefakte mit `correlation_status: "completed_no_matches"`. Es wird keine inferierte Kante erfunden.

Das standardmäßige maximale Korrelationsfenster beträgt 3000 ms. Es kann explizit geändert werden:

```bash
execweave-claude-record \
  --correlation-window-ms 1500 \
  --open \
  -- claude
```

Bei Bedarf ein Verzeichnis explizit wählen:

```bash
execweave-claude-record \
  --output-dir my-claude-run \
  --open \
  -- claude
```

Der laufgebundene Workflow bewahrt `events.jsonl`, `semantic.jsonl` und `events.semantic.jsonl`. Korrelation wird ausschließlich in den separaten Strom `events.correlated.jsonl` geschrieben.

## Sidecar-Pfad für eigenständige Hooks

Wenn `execweave-claude-hook` außerhalb des laufgebundenen Recorders verwendet wird, schreibt jede Claude-Sitzung standardmäßig nach:

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

Die Sitzungs-ID wird bereinigt, bevor sie als Dateiname verwendet wird.

Sie können dies überschreiben mit:

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

oder einem expliziten Hook-Befehl wie:

```bash
execweave-claude-hook --sidecar /path/to/semantic.jsonl
```

Für parallele eigenständige Sitzungen sollte der automatische sitzungsgebundene Pfad bevorzugt werden, statt mehrere Claude-Sitzungen auf denselben festen Sidecar zeigen zu lassen.

## Fortgeschritten: manuelles Merge und Korrelation

Die generische Semantik- und Korrelationspipeline bleibt verfügbar, wenn bereits eine Laufzeiterfassung und ein semantischer Sidecar vorliegen:

```bash
execweave semantic-merge \
  run.jsonl \
  semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl

execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl

execweave validate run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html \
  --open
```

Der ursprüngliche Laufzeitstrom und der semantische Sidecar bleiben unverändert.

## Tool → Process-Grenze und Korrelation v0.1

Claudes Command-Hook-Eingabe identifiziert den logischen Tool-Aufruf (`tool_name`, `tool_use_id` und Tool-Eingabe), liefert jedoch nicht die tatsächliche Kindprozess-PID, die ein Bash-Aufruf erzeugt.

Daher gibt der native Adapter absichtlich **keine** beobachtete Beziehung wie diese aus:

```text
Bash tool_call --SPAWNED_PROCESS--> process:1234
```

ohne zusätzliche Belege.

Im selben zusammengeführten Graphen können dennoch sowohl semantische als auch OS-Belege erscheinen:

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call --DECLARED_COMMAND--> "npm test"

session --LAUNCHED--> Claude process --SPAWNED--> shell/process ...
```

ExecWeave behauptet nicht, dass diese Pfade dieselbe Kausalkette sind, nur weil Zeitstempel oder Befehlszeichenfolgen ähnlich aussehen.

Die Korrelationsstufe v0.1 ist bewusst konservativ:

- Das Suchfenster ist begrenzt und wird, wenn verfügbar, durch das Tool-Ergebnis oder den nächsten deklarierten Tool-Aufruf beschnitten.
- Die Identität des Executables kann durch exakte Executable-/Prozess-/Cmdline-Belege gestützt werden.
- Kanonische Executable-Pfade können äquivalente Pfade ohne unscharfen Namensabgleich auflösen.
- Launcher-Prozesse dürfen als Fallback einen exakten, nicht leeren und längenerhaltenden `argv[1:]`-Abgleich verwenden.
- Eine Brücke wird nur erzeugt, wenn genau ein Prozesskandidat übrig bleibt.
- Mehrdeutige Kandidaten erzeugen keine Brücke.
- Nicht unterstützte zusammengesetzte Shell-Befehle und Shell-Builtins erzeugen keine Brücke.
- Es wird kein unscharfer Versions-/Namensabgleich verwendet.
- Zeitliche Nähe allein reicht niemals aus.

Eine abgeleitete Brücke wird dargestellt als:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

und trägt immer eine Semantik entsprechend:

```json
{
  "backend": "inference",
  "causal": false,
  "inferred": true,
  "inference_method": "...",
  "confidence": 0.8,
  "confidence_semantics": "heuristic_score_not_probability",
  "supporting_event_ids": ["..."]
}
```

Die genaue Methode und der Score hängen von den unterstützenden Belegen ab. Das Konfidenzfeld ist ein heuristischer Score zur Darstellung der Belegstärke und ausdrücklich **keine kalibrierte Wahrscheinlichkeit**.

Der eigenständige Viewer rendert inferierte Beziehungen getrennt von kausal beobachteten und nicht kausal beobachteten Kanten, markiert sie mit `· inferred` und zeigt ihre Belegmetadaten bei Auswahl. Eine inferierte Brücke wird niemals zu beobachteter Prozesszuordnung aufgewertet.

## Datenschutzverhalten

Der native Adapter vermeidet absichtlich mehrere risikoreiche Payloads:

- `Write`-/`Edit`-Dateiinhalte werden vom Adapter nicht gespeichert.
- `PostToolUse.tool_response` wird nicht gespeichert.
- Für generische Tool-Aufrufmetadaten werden nur Eingabeschlüsselnamen behalten.
- Dateiwerkzeuge speichern den deklarierten Dateipfad, nicht den Inhalt.
- Bash-/PowerShell-Befehle werden gespeichert, weil sie für die Erklärung der Ausführung nötig sind; der Befehlstext ist jedoch auf 4096 Zeichen begrenzt.
- Fehlertext ist auf eine kurze Fehlerzusammenfassung begrenzt.

Pfade und Befehle können trotzdem Zugangsdaten, Tokens, Kundennamen, interne Hostnamen oder andere sensible Informationen enthalten. Behandeln Sie semantische Sidecars als sensible Laufzeitmetadaten und prüfen Sie sie vor der Weitergabe.

## Belegsemantik

Direkt vom Claude-Adapter erzeugte Kanten enthalten:

```json
{
  "backend": "semantic",
  "attribution": "claude_hook",
  "evidence_source": "provider_hook",
  "provider": "claude",
  "causal": false
}
```

`causal: false` bedeutet nicht, dass der Claude-Hook erfunden wurde. Es bedeutet, dass eine logische Beziehung auf Provider-Ebene nicht zur stärkeren ExecWeave-Behauptung einer OS-Ausführungszuordnung aufgewertet wird.

Korrelationsereignisse sind separate abgeleitete Belege mit `backend: "inference"`, `inferred: true` und `causal: false`. Sie verändern weder die rohen Laufzeitbelege noch die Claude-Hook-Belege.

Siehe [`Semantische Telemetrie`](semantic-telemetry.de.md) für den generischen Merge-Vertrag und die Regeln für Prozessreferenzen.
