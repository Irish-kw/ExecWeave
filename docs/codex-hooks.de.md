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

ExecWeave zeichnet Evidenz aus Codex-Lifecycle-Hooks neben unabhängig erfasster OS-Laufzeit-Telemetrie auf. Provider-Hooks beschreiben logische Agent-/Tool-Aktivität; sie liefern nicht die OS-Kind-PID, die für direkte Tool → Process-Kausalität nötig wäre.

## Aktuelle Hook-Oberfläche

`execweave-codex-hook --print-config` registriert derzeit:

- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `PreCompact`
- `PostCompact`
- `SessionStart`
- `SessionEnd`
- `UserPromptSubmit`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `Interrupt`

Unbekannte oder upstream nicht verfügbare Ereignisse werden nicht erfunden. Hook-Schemata und Dispatch-Abdeckung können sich zwischen Codex-Versionen ändern.

Hook konfigurieren und Run aufzeichnen:

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

Der Recorder bindet einen run-spezifischen semantischen Sidecar und hält Runtime-, Semantic- und Correlated-Artefakte getrennt.

## Full-Fidelity-Inhalt

v0.6.5 speichert vollständige Inhaltswerte, die der Codex-Hook tatsächlich liefert, in einem lokalen content-addressed Store. Der JSONL-Sidecar enthält Referenzen statt großer Inline-Kopien.

Beobachteter Inhalt kann den vollständigen `UserPromptSubmit.prompt`, vollständiges `tool_input`, vollständiges `PostToolUse.tool_response`, Tool-Eingaben aus Permission Requests und finale Assistant-/Subagent-Nachrichten umfassen, sofern diese Felder vom Hook geliefert werden. Anwendungsbezogene Werte in diesen Payloads werden beibehalten; gehen Sie nicht davon aus, dass sie redigiert wurden.

Erkannte Transport-Credentials werden aus der separaten Provider-Metadatenprojektion entfernt, wenn der Adapter sie erkennt. Dieses Filtern verändert oder bereinigt den Content-Payload selbst nicht.

`content_complete_from_source: true` bedeutet, dass der vollständige Wert gespeichert wurde, den der Codex-Integrationspunkt geliefert hat. Es bedeutet nicht, dass ExecWeave eine nicht gelieferte Transcript-Datei gelesen, einen unsichtbaren Provider-Request abgefangen oder verborgenen Modellzustand beobachtet hat.

## Tool-Identität und Korrelation

Wenn Codex `tool_use_id` liefert, verwendet ExecWeave ihn als logische Tool-Call-Identität. Deklarierte Commands bleiben semantische Provider-Evidenz. Der Hook liefert weiterhin keine OS-Kind-PID; eine Tool → Process-Brücke wird daher nur dann von der konservativen Korrelationsstufe erzeugt, wenn genau ein Runtime-Kandidat eindeutig unterstützt wird.

```text
inferred: true
causal: false
```

Mehrdeutige, nicht gematchte, Shell-Builtin-, Compound- oder nicht unterstützte Commands erzeugen keine Brücke. Ähnliche Zeitpunkte oder Command-Strings reichen niemals aus, um Provider-Evidenz in OS-Attribution umzuwandeln.

## Datenschutz und Evidenzgrenze

Codex-Semantic-/Content-Artefakte können Prompts, Commands, Tool-Argumente/-Ergebnisse, finale Antworten, Pfade, Identifikatoren und sensible anwendungsbezogene Werte enthalten. Behandeln Sie das gesamte Run-Verzeichnis als sensibel und prüfen Sie es vor dem Teilen.

Der Adapter behauptet nicht, dass jeder Codex-Ausführungsmodus vollständige Lifecycle-Abdeckung bietet. Fehlende Hooks reduzieren die semantische Sichtbarkeit, deaktivieren aber nicht den unabhängigen OS-Runtime-Collector. Ein Provider-Hook beweist außerdem nicht, dass ein deklarierter Command ausgeführt wurde, dass eine Dateiaktion stattfand oder dass Bytes zwischen Ressourcen flossen.
