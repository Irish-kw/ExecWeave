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

ExecWeave integriert OpenCode über ein projektlokales Plugin. OpenCode liefert auf Tool-Before/After-Hooks exakte `sessionID + callID`-Werte, sodass ein logischer Tool-Call ohne heuristisches Pairing identifiziert werden kann. Diese Identität bleibt Provider-Evidenz und ist keine OS-PID.

## Installation und Aufzeichnung

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Das generierte Plugin wird unter `.opencode/plugins/execweave.ts` installiert. ExecWeave überschreibt ein vorhandenes Plugin nicht, außer `--force` wird ausdrücklich angegeben.

## Vollständige Beobachtungsoberfläche

v0.6.5 ist nicht auf den alten Drei-Ereignis-Minimal-Metadatenvertrag beschränkt. Der erzeugte Plugin-/Hook-Pfad kann von OpenCode bereitgestellte Inhalte über Chat-Nachrichten, Tool-Ausführung Before/After, Model-Context-/System-Transformationen, abgeschlossenen Assistant-Text, Provider-Bus-Ereignisse, Request-Header nach Credential-Filterung, Tool-Definitionen, Commands, Permission Requests und Compaction-Kontext bewahren, sofern diese Hooks ausgelöst werden.

Typische logische Graph-Beziehungen bleiben Agent → Tool Call, Tool Call → Tool, deklarierter Command/Target und Returned-Result-Beobachtungen. Content Storage ändert ihre Evidenzsemantik nicht.

## Full-Fidelity-Inhalt

Vollständige Werte, die das OpenCode-Plugin liefert, werden im lokalen content-addressed Store gespeichert und vom semantischen JSONL-Sidecar referenziert. Die Regressionen decken vollständige Chat Messages/Parts, Tool Args/Results, Model Context, System-Prompts, Assistant-Text, Provider-Ereignisse, Tool-Definitionen, Command-Argumente/-Parts, Permission-Daten und Compaction-Prompts/-Kontext ab.

Bekannte Transport-Credentials wie Authorization/Cookie werden aus den relevanten Header-/Provider-Metadatenprojektionen gefiltert. Sensible anwendungsbezogene Werte in Tool Args, Messages, Results oder anderen Content-Werten bleiben erhalten. Gehen Sie nicht davon aus, dass Full-Fidelity-Inhalte redigiert wurden.

## Tool-to-Process-Korrelation

`sessionID + callID` beweist die exakte logische Call-Identität innerhalb OpenCode. Es beweist nicht, welcher OS-Prozess den Call ausgeführt hat. Tool → Process bleibt eine separat abgeleitete konservative Brücke und wird nur erzeugt, wenn unabhängige Runtime-Evidenz genau einen Prozess unterstützt.

```text
inferred: true
causal: false
```

Mehrdeutige oder nicht unterstützte Calls erzeugen keine Brücke.

## Datenschutz und Evidenzgrenze

OpenCode-Run-Evidenz kann Prompts/Messages, System-/Context-Daten, Tool-Argumente/-Ausgaben, Commands, Permission-Patterns, Provider-Event-Content, Pfade, Identifikatoren und sensible Anwendungswerte enthalten. Prüfen Sie das Run-Verzeichnis vor dem Teilen.

Das Plugin beweist, was OpenCode auf Semantic-/Provider-Ebene offengelegt hat. Runtime-Collector etablieren Process-/File-/Network-Beobachtungen unabhängig. Full-Fidelity-Provider-Content beweist für sich allein weder Command-Ausführung noch abgeschlossenen Dateizugriff oder Byte-genauen Datenfluss.
