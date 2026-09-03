<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantische Telemetrie

ExecWeave kombiniert semantische Beobachtungen von Providern/Frameworks mit unabhängig erfasster OS-Laufzeit-Evidenz, ohne die ursprüngliche Laufzeitaufzeichnung umzuschreiben. Provider-Evidenz beschreibt, was ein Agent, Tool, Gateway oder eine Model-Runtime-Integration offengelegt hat; OS-Evidenz beschreibt, was der Maschinen-Collector beobachtet hat. Korrelation bleibt eine separate abgeleitete Ebene und wird nie stillschweigend zu kausalem Beweis hochgestuft.

## Workflow

Ein Provider-Adapter schreibt einen run-gebundenen semantischen Sidecar; anschließend validiert ExecWeave einen neuen zusammengeführten Stream:

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`run.jsonl` wird durch `semantic-merge` niemals verändert. Run-gebundene Recorder halten Runtime-, Semantic- und Correlated-Artefakte in getrennten Dateien.

## Full-Fidelity-Inhalt in v0.6.5

Semantische Telemetrie ist nicht mehr auf kleine Metadaten-Zusammenfassungen beschränkt. Wenn ein unterstützter Integrationspunkt Inhalte ausdrücklich liefert, kann v0.6.5 den vollständigen gelieferten Wert in einem lokalen content-addressed Store speichern und im JSONL-Ereignis nur eine Referenz ablegen.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Eine Content-Referenz enthält SHA-256, relativen Pfad, Medientyp, Byte-Größe, Content-Art, Darstellung und ob der gespeicherte Wert aus Sicht dieses Integrationspunkts vollständig ist. `complete_from_source: true` bedeutet, dass ExecWeave den vollständigen empfangenen Wert gespeichert hat; es bedeutet **nicht**, dass ein Provider verborgenen Modellzustand, einen unbeobachteten finalen Wire-Request oder ein nicht geliefertes Feld offengelegt hat.

Unterstützte native Adapter verwenden diesen Mechanismus für Inhalte, die ihre Hook/API-Oberfläche tatsächlich liefert, darunter Prompts, Tool-Eingaben/-Ergebnisse, Assistant-/Modellantworten, Reasoning/Thinking-Text wenn ausdrücklich bereitgestellt, von Provider-Hooks gelieferte Dateiinhalte sowie Request/Response-Objekte, wenn der jeweilige Adaptervertrag dies unterstützt.

Die kompakte semantische Zusammenfassung bleibt für die Graph-Materialisierung nutzbar, selbst wenn der Content Store ausfällt. Native Hook-Adapter sind standardmäßig fail-open, damit ein Speicherfehler die Agent-Operation nicht absichtlich blockiert.

## Evidenzgrenze

Semantischer Inhalt ist beobachtete Provider-/Integrations-Evidenz, keine OS-Kausalität. Eine gespeicherte Tool-Eingabe beweist nicht, dass ein Prozess sie ausgeführt hat; ein von einem Hook gelieferter Dateikörper beweist keinen abgeschlossenen OS-Lesevorgang; ein einer CLI übergebenes Request/Response-Paar bedeutet keine transparente Netzwerkinterzeption.

Tool → Process-Brücken werden nur durch die separat definierte konservative Korrelationsschicht erzeugt und bleiben:

```text
inferred: true
causal: false
```

Unbekannte oder mehrdeutige Attribution erzeugt keine Brücke. Byte-genauer Datenfluss oder Exfiltration werden nicht allein daraus abgeleitet, dass Datei- und Netzwerkbeobachtungen gleichzeitig existieren.

## Datenschutz

Full-Fidelity-Inhalt ist absichtlich sensibel. Gehen Sie **nicht** davon aus, dass Prompt-Text, Tool-Argumente, Tool-Ausgaben, Modellantworten, Dateiinhalte oder sensible anwendungsbezogene Werte redigiert wurden. Der Content Store bewahrt den vollständigen Wert auf, den der unterstützte Integrationspunkt geliefert hat.

ExecWeave filtert bekannte Transport-Credentials aus ausgewählten Provider-Metadatenprojektionen, wenn der Adaptervertrag dies vorsieht. Das ist jedoch weder ein allgemeiner Secret-Scanner noch entfernt es sensible Werte, die im Content selbst enthalten sind. Content-Blobs bleiben standardmäßig lokal und werden nicht inline in Graph-Ereignisse geschrieben, gehören aber weiterhin zur Evidenz des Runs und sollten vor dem Teilen geprüft werden.

Provider-spezifische Dokumente definieren genau, welche Felder jede Integration beobachten kann. Siehe die Dokumentation zu Claude Code, Codex, Antigravity, Cursor, OpenCode, Inference Gateway und Model Runtime.
