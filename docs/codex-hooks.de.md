<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a> |
  <a href="codex-hooks.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# OpenAI-Codex-Lifecycle-Hooks

ExecWeave bietet einen nativen Adapter für OpenAI-Codex-Lifecycle-Hooks, um semantische Belege auf Provider-Ebene derselben lokalen Ausführung hinzuzufügen wie die OS-Laufzeittelemetrie.

Diese Integration ist bewusst konservativ. Codex-Lifecycle-Hooks können ExecWeave mitteilen, welcher logische Tool-Aufruf angefordert wurde und – bei Shell-Ausführung – welcher Befehl deklariert wurde. Sie liefern **keine** OS-Kindprozess-PID. Daher stellt ExecWeave Tool → Process-Zuordnung aus dem Provider-Hook niemals als direkt beobachteten oder kausalen Beleg dar.

## Aktuelle Unterstützung

ExecWeave verarbeitet derzeit folgende Codex-Lifecycle-Ereignisse:

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

Der Adapter zeichnet nur Hooks auf, die Codex tatsächlich liefert. Unbekannte Lifecycle-Ereignisse werden ignoriert statt geraten.

### `SessionStart`

Wenn ein Modellname vorhanden ist, zeichnet ExecWeave auf:

```text
OpenAI Codex --USED_MODEL--> model
```

Der Adapter liest oder kopiert keine Transcript-Dateiinhalte.

### `PreToolUse`

ExecWeave verwendet die `tool_use_id` des Providers als stabile Identität des logischen Tool-Aufrufs:

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Für Codex' kanonisches Hook-Tool `Bash` erzeugt ein stringförmiges `tool_input.command` zusätzlich:

```text
tool_call --DECLARED_COMMAND--> command
```

Der deklarierte Befehl ist ein semantischer Provider-Beleg. Er ist für spätere konservative Korrelation nützlich, beweist aber nicht, dass ein bestimmter OS-Prozess diesen Befehl ausgeführt hat.

### `PostToolUse`

ExecWeave zeichnet derzeit eine neutrale Abschlussrelation auf:

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

`PostToolUse` wird absichtlich **nicht** in `TOOL_CALL_SUCCEEDED` oder `TOOL_CALL_FAILED` übersetzt. Das aktuelle Codex-Hook-Payload liefert keinen ausreichend verlässlichen Erfolgs-/Fehlerindikator, um diese Aussage sicher zu treffen.

ExecWeave speichert `tool_response` nicht roh in der semantischen Telemetrie. Bei String-Antworten werden nur Antworttyp und Zeichenanzahl gespeichert.

## Codex konfigurieren

Nach der Installation von ExecWeave erzeugen Sie das unterstützte Lifecycle-Hook-Konfigurationsfragment:

```bash
execweave-codex-hook --print-config
```

Fügen Sie das ausgegebene `hooks`-Objekt in Ihre Codex-`hooks.json`-Konfiguration ein.

Die erzeugte Konfiguration registriert `execweave-codex-hook` für `SessionStart`, `PreToolUse` und `PostToolUse`.

Der Hook-Adapter ist standardmäßig fail-open: Telemetrieprobleme geben eine Warnung aus, blockieren Codex aber nicht absichtlich. Zum Debuggen des Adapters selbst verwenden Sie:

```bash
execweave-codex-hook --strict
```

## Einen Codex-Lauf aufzeichnen

Nachdem Codex so konfiguriert wurde, dass der Hook aufgerufen wird:

```bash
execweave-codex-record --open -- codex
```

`execweave-codex-record` verändert die Codex-Konfiguration nicht. Es bindet lediglich den Kindprozess von Codex über eine geerbte Umgebungsvariable an einen laufbezogenen semantischen Sidecar.

Wenn Lifecycle-Hooks ausgelöst werden, enthält das Laufverzeichnis geschichtete Artefakte:

```text
.execweave/runs/<run-id>/
├── events.jsonl              # nur Laufzeitbelege
├── graph.json                # nur Laufzeitgraph
├── viewer.html               # nur Laufzeit-Viewer
├── semantic.jsonl            # nur Codex-Lifecycle-Hook-Belege
├── events.semantic.jsonl     # validierter Laufzeit- + Semantikstrom
├── graph.semantic.json       # Laufzeit- + Semantikgraph
├── viewer.semantic.html      # Laufzeit- + Semantik-Viewer
├── events.correlated.jsonl   # abgeleiteter Strom; beobachtete Belege unverändert
├── graph.correlated.json     # Graph mit inferierten Brücken + Korrelationsmetadaten
└── viewer.correlated.html    # Viewer mit Korrelationszusammenfassung
```

Wenn keine Codex-Hook-Ereignisse eintreffen, fällt der Recorder sicher auf reine Laufzeitartefakte zurück.

## Tool → Process-Korrelation

Für eine `Bash`-Deklaration wie:

```text
tool_call --DECLARED_COMMAND--> "python task.py"
```

kann ExecWeave diese semantische Deklaration mit begrenzten Laufzeit-Prozessbelegen vergleichen. Es erzeugt:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

nur dann, wenn genau ein Prozesskandidat durch den bestehenden konservativen Matcher eindeutig gestützt wird.

Jede solche Brücke bleibt:

```text
inferred: true
causal: false
```

Mehrdeutige, nicht passende, Shell-Builtin-, zusammengesetzte oder anderweitig nicht unterstützte Aufrufe erzeugen keine Brücke. Der korrelierte Graph speichert eine Korrelationszusammenfassung auf Laufebene, sodass der Viewer `matched`, `ambiguous`, `no match` und `unsupported` unterscheiden kann, statt jede fehlende Kante gleich zu behandeln.

Der Viewer bietet außerdem **observed only**, wodurch inferierte Kanten vor Fokus-Traversierung und Layout entfernt werden.

## Beleg- und Datenschutzgrenze

Der Codex-Adapter von ExecWeave speichert derzeit semantische Metadaten, die für den Graphaufbau erforderlich sind, darunter:

- Codex-Sitzungs-ID
- Turn-ID, sofern vorhanden
- Modellname
- Toolname
- Tool-Use-ID
- Namen der Eingabeschlüssel
- deklarierter `Bash`-Befehl
- Antworttyp / Antwortlänge für `PostToolUse`

Er sammelt absichtlich nicht:

- Prompt-Text
- Inhalte von Transcript-Dateien
- rohe `tool_response`-Inhalte
- Dateiinhalte
- vom Provider abgeleitete Tool → Process-PIDs

Befehle können dennoch Geheimnisse oder sensible Pfade enthalten. Prüfen Sie Artefakte vor der Weitergabe.

## Aktuelle Upstream-Einschränkungen

Codex-Lifecycle-Hooks entwickeln sich weiter. ExecWeave behandelt diese Integration daher als nativen semantischen Adapter, nicht als Beweis, dass jeder Codex-Ausführungsmodus vollständige Lifecycle-Abdeckung bietet.

Bekannte Einschränkungen:

1. `PostToolUse` liefert ExecWeave derzeit kein zuverlässiges Erfolgs-/Fehlersignal; die Relation bleibt daher neutral `TOOL_CALL_RETURNED`.
2. Bei der Dispatch-Abdeckung von Lifecycle-Hooks gab es zuletzt Lücken in einigen `codex exec`-Pfaden. Die interaktive Codex CLI ist das sicherere erste Ziel für Lifecycle-Hook-Telemetrie.
3. Bei einigen Windows-Befehlsausführungspfaden wurden Upstream-Lücken in der Hook-Abdeckung gemeldet.
4. Provider-Hooks liefern nicht die OS-Kindprozess-PID, die für direkt beobachtete Tool → Process-Zuordnung erforderlich wäre.

Diese Einschränkungen betreffen die semantische Abdeckung, nicht den unabhängigen OS-Laufzeit-Collector. Laufzeitbelege bleiben verfügbar, selbst wenn kein Provider-Hook ausgelöst wird.

## Designregel

Die Codex-Integration folgt derselben Belegregel wie der Rest von ExecWeave:

> Provider-Semantik beschreibt, was der Agent nach eigener Angabe tat; OS-Telemetrie beschreibt, was die Maschine tatsächlich beobachtete; Korrelation darf beide nur als explizite, nicht kausale Inferenz verbinden, wenn die Belege eindeutig sind.
