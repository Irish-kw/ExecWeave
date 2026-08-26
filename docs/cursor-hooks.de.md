# Cursor Hooks

<!-- i18n-nav:start -->
<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <a href="cursor-hooks.zh-TW.md">繁體中文</a> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <a href="cursor-hooks.ko.md">한국어</a> |
  <a href="cursor-hooks.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="cursor-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave nutzt Cursors native Hook-Oberfläche, um logische Agent-/Tool-/Command-Belege zum Laufzeitgraphen hinzuzufügen, ohne Provider-Metadaten als OS-Kausalität zu behandeln.

## Schnellstart

Erzeugen Sie eine Hook-Konfiguration und fügen Sie sie zu Ihren Cursor-Hook-Einstellungen hinzu:

```bash
execweave-cursor-hook --print-config
```

Zeichnen Sie anschließend einen Cursor-Lauf auf:

```bash
execweave-cursor-record --open -- cursor
```

Der laufgebundene Recorder bewahrt Laufzeit-, semantische und korrelierte Artefakte getrennt auf.

## Ereignisse

Die Basisimplementierung verarbeitet:

- `sessionStart`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`

Cursor stellt eine stabile `tool_use_id` bereit, sodass `preToolUse` und der zugehörige Post-Hook dieselbe exakte logische `tool_call`-Identität verwenden können.

Typische semantische Kanten sind:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`postToolUseFailure` wird separat als `TOOL_CALL_FAILED` dargestellt.

## Tool-zu-Prozess-Korrelation

Cursor-Hook-Belege liefern keine OS-Kindprozess-PID. Ein Shell-Aufruf wird daher nicht direkt zu einer Prozesskante.

Wenn Laufzeitbelege unabhängig genau einen eindeutig gestützten Prozess zeigen, kann ExecWeave ableiten:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Die Brücke ist immer:

```text
inferred: true
causal: false
```

Mehrdeutige oder nicht unterstützte Aufrufe erzeugen keine Brücke.

## Datenschutzgrenze

Der Adapter speichert absichtlich weder Prompt-Text noch Transcript-Pfade, Benutzer-E-Mail, Agent-Nachrichten oder Tool-Ausgaben. Er behält nur die Identifikatoren und deklarierten Metadaten, die für Observability benötigt werden, darunter Modellidentität, Conversation-/Generation-IDs, Toolname/-Use-ID, Befehl und deklarierter Dateipfad.

Befehle und Pfade können weiterhin sensibel sein. Prüfen Sie Artefakte vor der Weitergabe.

## Beleggrenze

Ein Cursor-Hook beweist, was Cursor auf der semantischen Ebene gemeldet hat. Er beweist nicht, dass ein deklarierter Befehl ausgeführt, eine deklarierte Datei tatsächlich geöffnet oder Daten zwischen Ressourcen übertragen wurden. OS-Collector bleiben die Quelle für Laufzeitbelege.
