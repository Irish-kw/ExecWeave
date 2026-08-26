# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <a href="opencode-plugin.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave integriert sich über ein projektlokales Plugin in OpenCode. OpenCode stellt auf `tool.execute.before` und `tool.execute.after` exakte Werte `sessionID + callID` bereit, sodass ein logischer Tool-Aufruf ohne heuristische Paarung von Lifecycle-Ereignissen identifiziert werden kann.

## Installation

Installieren Sie das erzeugte Plugin im aktuellen Projekt:

```bash
execweave-opencode-plugin --install
```

Es erzeugt:

```text
.opencode/plugins/execweave.ts
```

OpenCode lädt Projekt-Plugins automatisch aus diesem Verzeichnis. ExecWeave verweigert das Überschreiben eines bestehenden Plugins, sofern nicht `--force` angegeben wird.

Anschließend einen Lauf aufzeichnen:

```bash
execweave-opencode-record --open -- opencode
```

## Erfasste semantische Belege

Das Basis-Plugin gibt minimale Metadaten aus für:

- `chat.message`
- `tool.execute.before`
- `tool.execute.after`

Typische Graphbeziehungen sind:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

Die OpenCode-`callID` wird direkt in der `tool_call`-Identität verwendet.

## Datenschutzgrenze

OpenCodes After-Hook kann Tool-Ausgabe sehen, aber das erzeugte ExecWeave-Plugin leitet `output.output` oder `output.metadata` absichtlich nicht weiter.

Argumente werden reduziert, bevor sie das Plugin verlassen:

- `bash`: deklarierter `command`
- dateiorientierte Tools: pfadartige Felder wie `filePath`, `file_path` oder `path`
- optionale Working-Directory-Metadaten

Roher Schreibinhalt, Chat-Message-Parts und Tool-Ausgabe werden nicht an den ExecWeave-Hook gesendet.

## Tool-zu-Prozess-Korrelation

`callID` beweist die logische Aufrufidentität innerhalb von OpenCode; sie ist keine OS-PID. Tool → Process bleibt eine abgeleitete konservative Brücke und wird nur erzeugt, wenn Laufzeitbelege genau einen eindeutig gestützten Prozess liefern.

Abgeleitete Brücken bleiben `inferred: true` und `causal: false`.

## Beleggrenze

Das Plugin meldet OpenCodes semantische Absicht. Laufzeit-Collector stellen Prozess-/Datei-/Netzwerkbeobachtungen unabhängig fest. ExecWeave behandelt das Provider-Plugin niemals als Beweis, dass ein deklarierter Befehl oder eine Dateiaktion tatsächlich ausgeführt wurde.
