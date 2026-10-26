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

ExecWeave nutzt Cursors native Hook-Oberfläche, um einem Run semantische Provider-/Content-Evidenz hinzuzufügen, ohne diese Evidenz als OS-Kausalität zu behandeln.

## Schnellstart

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Der run-gebundene Recorder hält Runtime-, Semantic- und Correlated-Artefakte getrennt.

## Beobachtungsoberfläche

Die v0.6.5-Hook-Konfiguration deckt eine breitere Cursor-Lifecycle-Oberfläche ab, sofern Cursor sie bereitstellt: Session Start/End, Tool Before/After/Failure, Subagents, Shell- und MCP-Ausführung, File Read/Edit, Prompt Submission, Compaction/Stop, Agent Response/Thought sowie Tab File Read/Edit.

Cursor liefert für seine Tool-Hooks eine stabile logische Tool-Call-Identität. Diese Identität ist keine OS-PID.

## Full-Fidelity-Inhalt

Wenn Cursor einen Inhaltswert ausdrücklich liefert, speichert v0.6.5 den vollständigen gelieferten Wert im lokalen content-addressed Store und legt im semantischen JSONL nur dessen Referenz ab.

Die Regressionen decken vollständigen Prompt-Text, Tool-Eingabe/-Ausgabe und Failure-Text, Shell-Command/-Output, MCP-Command/-Input/-Result, von Read-Hooks gelieferten Dateicontent, Edit-Strukturen, finale Agent-Antworten, vom Provider als Thought markierten Text und Subagent-Zusammenfassungen ab.

Diese Felder bleiben Provider-Beobachtungen mit ihren Evidenzgrenzen. Content aus `beforeReadFile` beweist beispielsweise keinen abgeschlossenen OS-Lesevorgang, und eine Edit-Struktur beweist keinen vollständigen Post-Edit-Snapshot, sofern der Provider diesen nicht tatsächlich geliefert hat.

Bekannte Transport-Credentials werden dort aus der Provider-Metadatenprojektion gefiltert, wo dies definiert ist. Sensible Werte innerhalb des Contents bleiben erhalten. Full-Fidelity-Content ist keine allgemeine Secret-Redaction-Schicht.

## Tool-to-Process-Korrelation

Cursor-Hook-Evidenz liefert keine OS-Kind-PID. Ein Shell-Call wird daher nur dann zu einer Process-Brücke, wenn unabhängige Runtime-Evidenz genau einen Kandidaten eindeutig unterstützt:

```text
inferred: true
causal: false
```

Mehrdeutige oder nicht unterstützte Calls erzeugen keine Brücke. Stabile Provider-Tool-Call-Identität beweist logische Identität innerhalb Cursor, nicht machine-level Prozessattribution.

## Datenschutz und Evidenzgrenze

Cursor-Run-Evidenz kann Prompts, Tool-Argumente/-Ergebnisse, Shell-Ausgabe, Dateicontent, Edit-Daten, Assistant-Antworten, Provider-labeled Thought-Text, Commands, Pfade, Identifikatoren, MCP-Werte und sensible Anwendungswerte enthalten. Prüfen Sie das vollständige Run-Verzeichnis vor dem Teilen.

Ein Cursor-Hook beweist nur, was Cursor auf Provider-Ebene gemeldet oder geliefert hat. Er beweist nicht für sich allein, dass ein deklarierter Command ausgeführt, eine Datei von einem bestimmten Prozess gelesen oder Bytes zwischen Ressourcen übertragen wurden.
