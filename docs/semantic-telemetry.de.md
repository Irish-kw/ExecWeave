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

ExecWeave kann semantische Ereignisse von Providern/Frameworks mit OS-Laufzeitbelegen kombinieren, ohne die ursprüngliche Laufzeiterfassung umzuschreiben.

Das Ziel ist, logische Agent-/Tool-/MCP-Belege und maschinennahe Prozess-/Datei-/Netzwerkbelege im selben Graphen darzustellen und zugleich festzuhalten, welche Quelle jede Beziehung belegt.

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     |
                                                     +--DECLARED_COMMAND--> command

process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Ein Provider-Hook kann erklären, *welche logische Aktion angefordert wurde*. Der Laufzeit-Collector erklärt, *was die Maschine tatsächlich getan hat*. ExecWeave wandelt zeitliche Nähe zwischen beiden nicht stillschweigend in einen Kausalitätsbeweis um.

## Workflow

Erfassen Sie zunächst einen normalen ExecWeave-Lauf:

```bash
execweave run --output run.jsonl -- claude
```

Ein Provider-Adapter oder Hook schreibt einen separaten semantischen Sidecar, beispielsweise `semantic.jsonl`.

Führen Sie den Sidecar in einen **neuen** validierten Ereignisstrom zusammen:

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl \
  --output run.semantic.graph.json
execweave view run.semantic.graph.json \
  --output run.semantic.html \
  --open
```

`run.jsonl` wird von `semantic-merge` niemals verändert.

## Vertrag für Sidecar-Datensätze

Ein semantischer Sidecar-Datensatz ist ein JSON-Objekt pro Zeile. Der Adapter liefert nur die semantische Beobachtung:

```json
{
  "timestamp": "2026-08-25T10:00:02.123Z",
  "event_type": "semantic.tool.called",
  "relation": "REQUESTED_TOOL_CALL",
  "source": {
    "type": "agent",
    "id": "agent:Claude Code",
    "name": "Claude Code",
    "attributes": {}
  },
  "target": {
    "type": "tool_call",
    "id": "tool-call:provider:session:call-id",
    "name": "Bash",
    "attributes": {}
  },
  "attributes": {
    "attribution": "provider_hook",
    "evidence_source": "provider_hook",
    "causal": false
  }
}
```

Der Sidecar muss **nicht** bereitstellen:

- ExecWeave-`session_id`
- ExecWeave-`schema_version`
- lückenlose `sequence`
- `event_id` (optional; ExecWeave erzeugt eine, wenn sie fehlt)

`semantic-merge` injiziert die Laufzeit-Sitzungs-ID, verwendet das aktuelle ExecWeave-Ereignisschema, sortiert semantische und Laufzeit-Body-Ereignisse nach Zeitstempel, vergibt eine lückenlose Sequenz neu, hält `session.started` an erster und `session.finished` an letzter Stelle und validiert das zusammengeführte Ergebnis, bevor die Ausgabedatei geschrieben wird.

## Empfohlene semantische Entitäten

Das generische Entitätsschema von ExecWeave unterstützt bereits zusätzliche Knotentypen.

| Typ | Beispiel-ID | Bedeutung |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | Logischer Agent/Client |
| `tool_call` | `tool-call:claude:session:tool-use-id` | Ein konkreter logischer Tool-Aufruf |
| `tool` | `tool:claude:Bash` | Für den Agent sichtbares Tool |
| `mcp_server` | `mcp-server:claude:github` | MCP-Server/-Integration |
| `model` | `model:claude:claude-sonnet` | Modellidentität, sofern der Provider sie bereitstellt |
| `command` | `command:sha256:...` | Deklarierte Befehlsmetadaten aus einem semantischen Hook |
| `process_reference` | `process-pid:1234` | Optionaler Verweis, wenn eine Upstream-Quelle tatsächlich eine PID bereitstellt |

Entitäts-IDs sollten stabil genug sein, um wiederholte semantische Beobachtungen innerhalb eines Laufs zu deduplizieren.

## Optionaler Prozessreferenz-Verweis

Einige Provider-/Framework-Adapter kennen möglicherweise eine Kind-PID, aber nicht die vollständige ExecWeave-Prozessentitäts-ID. In diesem Fall können sie eine `process_reference` mit der beobachteten PID ausgeben.

Beim Zusammenführen löst ExecWeave solche Referenzen gegen Prozessentitäten auf, die tatsächlich im Laufzeitstrom beobachtet wurden. Die Auflösung ist konservativ:

1. Eine explizite `create_time` kann den Prozess eindeutig identifizieren.
2. Eine PID mit genau einem Laufzeitkandidaten wird direkt aufgelöst.
3. Bei PID-Wiederverwendung kann ExecWeave die eindeutig letzte Prozess-Erstellungszeit wählen, die nicht nach dem semantischen Zeitstempel liegt.
4. Andernfalls bleibt der Knoten `process_reference` mit `unresolved: true`, statt zu raten.

Ein aufgelöstes Ereignis speichert die ursprüngliche Zuordnung zum Laufzeitprozess in `attributes.resolved_process_references`.

**Geben Sie keine `process_reference` aus, wenn der Provider keine PID bereitgestellt hat.** Eine Befehlszeichenfolge und ein zeitlich naher Prozess reichen nicht aus, um eine exakte Tool → Process-Beziehung zu behaupten.

Der aktuelle native Claude-Code-Adapter folgt dieser Regel: Claudes Hook-Eingabe identifiziert Tool-Aufrufe, stellt aber keine PID des Kindprozesses bereit. Daher erfindet der Adapter keine Kanten `tool_call --SPAWNED_PROCESS--> process`.

## Beleg- und Kausalitätsgrenze

Aktuelle Provider-Adapter markieren semantische Kanten als `causal: false`, selbst wenn ein Provider-Hook zuverlässig meldet, dass ein logisches Tool-Ereignis stattgefunden hat. In ExecWeave ist `causal: true` einer stärkeren Zuordnung auf Ausführungsebene vorbehalten und bedeutet nicht lediglich, dass zwei logische Objekte miteinander verbunden sind.

Damit bleiben Aussagen wie diese getrennt:

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call       semantischer Provider-Beleg
process     --OPENED_READ---------> ~/.ssh/id_ed25519 OS-Laufzeitbeleg
```

Diese beiden Beobachtungen beweisen für sich genommen **nicht**:

```text
Bash call --caused--> that exact process
file bytes --flowed to--> a network endpoint
```

Jede zukünftige semantische/Laufzeit-Korrelationsschicht muss Methode und Konfidenz ausdrücklich offenlegen und von beobachteter OS-Zuordnung unterscheidbar bleiben.

## Sitzungsgrenze

Jeder semantische Zeitstempel muss innerhalb des Intervalls der erfassten Laufzeitsitzung liegen. Ereignisse außerhalb dieses Intervalls werden abgelehnt. Dadurch wird verhindert, dass fremde Provider-Telemetrie stillschweigend an den falschen Lauf angehängt wird.

## Datenschutz

Semantische Sidecars können sensible Metadaten enthalten, selbst wenn ExecWeave selbst keine Dateiinhalte erfasst. Adapter-Autoren sollten Identifikatoren und begrenzte Metadaten vollständigen Prompts, Tool-Argumenten, Tool-Ausgaben, Zugangsdaten oder Geheimwerten vorziehen.

Der Claude-Code-Adapter speichert absichtlich weder `Write`-Inhalte noch `tool_response`. Deklarierte Shell-Befehle bleiben erhalten, weil sie zentral für die Erklärung der Ausführung sind; ihre Länge ist jedoch begrenzt und sie sollten weiterhin als potenziell sensible Metadaten behandelt werden.

Die generische semantische Merge-Schicht ist providerunabhängig. Provider-spezifische Adapter sind separate Integrationen und müssen genau dokumentieren, welche Upstream-Felder sie verwenden und welche Aussagen diese Felder stützen.

Siehe [`Claude Code Hooks`](claude-code-hooks.de.md) für den ersten nativen Provider-Adapter.
