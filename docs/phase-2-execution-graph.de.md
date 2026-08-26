<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-2-execution-graph.md">English</a> |
  <a href="phase-2-execution-graph.zh-TW.md">繁體中文</a> |
  <a href="phase-2-execution-graph.zh-CN.md">简体中文</a> |
  <a href="phase-2-execution-graph.ja.md">日本語</a> |
  <a href="phase-2-execution-graph.ko.md">한국어</a> |
  <a href="phase-2-execution-graph.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="phase-2-execution-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Ausführungsgraph

Phase 2 verwandelt einen validierten Phase-1-JSONL-Ereignisstrom in einen persistenten Ausführungsgraphen, der abgefragt und später in der lokalen UI visualisiert werden kann.

## Aktueller Status

Der erste Graphkern von Phase 2 ist implementiert.

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

Der Graph-Builder interpretiert rohe Telemetrie nicht neu. Er verwendet die Zuordnungs- und Kausalitätssemantik, die Phase 1 erzeugt hat.

## Graphschema

Die aktuelle Graphschema-Version lautet:

```text
0.1
```

Ein Graph-JSON-Dokument enthält:

```json
{
  "graph_schema_version": "0.1",
  "session_id": "...",
  "event_count": 100,
  "node_count": 24,
  "edge_count": 31,
  "nodes": [],
  "edges": []
}
```

## Knoten

Jede unterschiedliche Phase-1-Entitäts-ID wird zu einem Graphknoten.

Beispiele:

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

Die Knotenidentität basiert auf der Entitäts-ID des Ereignisstroms, nicht auf Anzeigenamen.

Jeder Knoten sammelt:

- `type`
- `name`
- Entitätsattribute
- ersten beobachteten Zeitstempel
- letzten beobachteten Zeitstempel
- Anzahl beobachteter Ereignisse
- Ereignistypen, in denen die Entität vorkam

Phase 2 verwendet derzeit konservatives Attribute-Merging: Ein vorhandenes Knotenattribut wird nicht stillschweigend durch einen späteren widersprüchlichen Wert überschrieben.

## Kanten

Ein Ereignis mit Quelle und Ziel kann eine gerichtete Graphkante erzeugen:

```text
source --RELATION--> target
```

Zum Beispiel:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Die Kantenidentität ist das Tupel:

```text
(source, relation, target)
```

Wiederholte Ereignisse für dasselbe Tupel werden zu einer Kante aggregiert, statt als doppelte Linien gerendert zu werden.

Eine aggregierte Kante speichert:

- exakten Auftretens-`count`
- ersten/letzten Zeitstempel
- erste/letzte Sequenznummer
- unterstützende Ereignis-IDs
- beitragende Ereignistypen
- Backend(s)
- Zuordnungsmethode(n)
- Kausalitätszustand

Beispiel:

```text
process:p1 --OPENED_READ--> file:a.txt
count = 17
```

bedeutet, dass 17 Phase-1-Ereignisse dieselbe Graphbeziehung stützen.

## Kausalitätsaggregation

Wenn alle unterstützenden Ereignisse kausal sind:

```json
{"causal": true}
```

Wenn alle ausdrücklich nicht kausal sind:

```json
{"causal": false}
```

Wenn die Belege gemischt sind oder keine einheitliche Kausalitätsangabe liefern:

```json
{"causal": null}
```

Die Graphschicht darf nicht kausale Telemetrie nicht zu einer kausalen Beziehung aufwerten.

## Lifecycle-Ereignisse

Einige Phase-1-Ereignisse besitzen eine Quelle, aber kein Ziel, beispielsweise:

```text
process EXITED
session FINISHED_SESSION
```

Phase 2 erzeugt dafür **keinen** künstlichen Zielknoten und keine Selbstkante.

Stattdessen tragen sie zu den beobachteten Ereignismetadaten des Quellknotens bei. Dadurch bleibt der Graph relational, anstatt jedes Logereignis in einen künstlichen Knoten umzuwandeln.

## Validierungsgrenze des Graphen

Standardmäßig benötigt der Graphaufbau einen gültigen, vollständigen Phase-1-Ereignisstrom:

```bash
execweave graph run.jsonl
```

Für Incident-Recovery oder eine abgebrochene Agent-Sitzung:

```bash
execweave graph --allow-incomplete interrupted.jsonl
```

Der Strom muss strukturell weiterhin gültig sein; nur die Anforderung einer abgeschlossenen Sitzung wird gelockert.

## Graphzusammenfassung

```bash
execweave graph-summary run.graph.json
```

Die Zusammenfassung meldet:

- Ereignisanzahl
- Knotenanzahl
- Kantenanzahl
- Anzahl nach Knotentyp
- Anzahl nach Relation
- Anzahl kausaler Kanten
- Anzahl nicht kausaler Kanten
- Anzahl gemischter/unbekannter Kausalität

## Filterung

Erstellen Sie einen kleineren Graphen, ohne den Quellgraphen zu verändern:

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

Nach Relation filtern:

```bash
execweave graph-filter run.graph.json \
  --output network.graph.json \
  --relation CONNECTED_TO \
  --relation CONNECT_ATTEMPTED
```

Nach Knotentyp filtern:

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

Nach Backend filtern:

```bash
execweave graph-filter run.graph.json \
  --output syscall.graph.json \
  --backend strace
```

Filter können kombiniert werden.

## Gerichtete Pfadabfragen

Phase 2 kann gerichtete Laufzeitpfade abfragen:

```bash
execweave path run.graph.json \
  'session:abc' \
  'network_endpoint:1.2.3.4:443'
```

Auf Kanten beschränken, deren aggregierte Belege kausal sind:

```bash
execweave path run.graph.json SOURCE TARGET --causal-only
```

Relationen beschränken:

```bash
execweave path run.graph.json SOURCE TARGET \
  --relation LAUNCHED \
  --relation SPAWNED \
  --relation CONNECTED_TO
```

Die Pfadsuche ist derzeit:

- gerichtet
- Breitensuche
- nur einfache Pfade (ein Knoten darf in einem zurückgegebenen Pfad nicht wiederholt werden)
- durch `--max-depth` begrenzt
- durch `--max-paths` begrenzt

So verhindert ExecWeave, dass ein zyklischer Ausführungsgraph unbegrenzt viele Abfrageergebnisse erzeugt.

## Aktuelle Akzeptanzkriterien für Phase 2

- [x] Phase-1-Eingabe vor dem Graphaufbau validieren
- [x] Entitäten als Knoten materialisieren
- [x] Knoten anhand stabiler Entitäts-ID deduplizieren
- [x] Wiederholte `(source, relation, target)`-Ereignisse aggregieren
- [x] Ereignisbelege an Kanten bewahren
- [x] Kausalitätssemantik bewahren
- [x] Zeitliche First/Last-Metadaten bewahren
- [x] Keine künstlichen Kanten für Lifecycle-Ereignisse nur mit Quelle
- [x] Graphzusammenfassung
- [x] Graphfilterung
- [x] Gerichtete Pfadabfrage
- [ ] Bessere Entitätsauflösung zwischen semantisch äquivalenten Ressourcen-IDs
- [ ] Zeitliche Snapshots / Zeitfensterfilterung
- [ ] Kompakte Belegindexierung für sehr große Läufe
- [ ] Tests für Graphformat-Migration/Versionierung
- [ ] Interaktive lokale Graph-UI

Die interaktive UI gehört zu Phase 3. Sie sollte diesen Graphvertrag verwenden, statt rohe Collector-Logs direkt zu lesen.
