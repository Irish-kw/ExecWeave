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

# Gemini-CLI-Hooks

ExecWeave übernimmt Gemini-CLI-Hooks als semantische Provider-/Content-Evidenz und hält diese Ebene von unabhängig erfasster OS-Laufzeit-Evidenz getrennt. Gemini-Hooks beschreiben, was der Provider offengelegt hat; sie beweisen nicht für sich allein, welcher OS-Prozess eine Aktion ausgeführt hat.

## Aktuelle Hook-Oberfläche

`execweave-gemini-hook --print-config` registriert derzeit:

- `SessionStart`
- `SessionEnd`
- `BeforeAgent`
- `AfterAgent`
- `BeforeModel`
- `AfterModel`
- `BeforeToolSelection`
- `BeforeTool`
- `AfterTool`
- `PreCompress`
- `Notification`

Tool-Hooks verwenden die Matcher-Oberfläche des Providers, und der erzeugte Command-Hook ist standardmäßig fail-open. Konfigurieren und aufzeichnen:

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

## Full-Fidelity-Inhalt

v0.6.5 speichert vollständige Werte, die der Gemini-Hook ausdrücklich liefert, in einem lokalen content-addressed Store. Je nach Ereignis kann dies den User-Prompt, das vollständige Model-Request-Objekt, Model-Response-/Chunk-Objekte, Tool-Eingaben, Tool-Antworten einschließlich `llmContent` / `returnDisplay` / Provider-Fehlerfeldern, die finale Agent-Antwort und weitere Provider-Payload-Werte umfassen.

Der semantische JSONL-Sidecar speichert Referenzen statt großer Inline-Kopien. Identische Werte werden per SHA-256 dedupliziert.

Provider-Metadatenprojektionen schließen erkannte Transport-Credential-Felder wie Authorization-Header aus. Dieses Filtern bereinigt nicht die anwendungsbezogenen Werte im vollständigen Content. Ein sensibler Wert in einer Tool-Eingabe oder Model-Request bleibt Teil des gespeicherten Inhalts.

`content_complete_from_source: true` bedeutet, dass ExecWeave das vollständige empfangene Feld/den vollständigen Wert gespeichert hat. Es behauptet nicht, dass Gemini einen verborgenen finalen Wire-Request, internen Modellzustand oder eine im Hook-Payload fehlende Stufe offengelegt hat.

## Tool-Identität und Korrelation

Gemini liefert keine eindeutige Tool-Call-ID, die zwischen `BeforeTool` und `AfterTool` geteilt wird. ExecWeave erzeugt daher keine direkte Before/After-Identity-Edge. Ein deterministischer Tool-Fingerprint kann als diagnostischer Hinweis erhalten bleiben, aber wiederholte identische Calls bleiben getrennte Beobachtungen.

Gemini-Hooks liefern auch keine OS-Kind-PID. Tool → Process-Brücken werden daher nur abgeleitet, wenn unabhängige Runtime-Evidenz genau einen Kandidaten unterstützt:

```text
inferred: true
causal: false
```

Mehrdeutige, nicht gematchte, Compound-, Shell-Builtin- oder nicht unterstützte Commands erzeugen keine Brücke.

## Datenschutz und Evidenzgrenze

Gemini-Content-Artefakte können Prompts, vollständige Model-Requests/-Responses, Tool-Eingaben/-Ergebnisse, von Tools gelieferten Dateicontent, MCP-/Anwendungsfelder, finale Antworten, Identifikatoren, Commands, Pfade und eingebettete sensible Werte enthalten. Prüfen Sie das Run-Verzeichnis vor dem Teilen.

ExecWeave liest `transcript_path` nicht automatisch, nur weil der Hook ihn meldet. Ein gespeicherter Provider-Wert beweist außerdem weder OS-Ausführung noch abgeschlossenen Dateizugriff oder Byte-genauen Datenfluss. Unabhängige Runtime-Evidenz und ausdrücklich markierte Korrelation bleiben getrennte Ebenen.
