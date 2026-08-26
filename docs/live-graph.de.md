<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <a href="live-graph.ko.md">한국어</a> |
  <a href="live-graph.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live-Graph

ExecWeave kann einen lokalen Ausführungsgraphen streamen, während ein KI-Agent oder ein beliebiger Befehl noch läuft.

```bash
execweave live --open -- claude
```

## Aktueller Vertrag

Das Live-MVP verwendet bewusst den `portable`-Collector.

Das Linux-Backend `strace` parst Trace-Dateien derzeit erst nach dem Ende des Befehls. Es liefert stärkere, auf Systemaufrufen basierende Zuordnung, ist in der aktuellen Implementierung jedoch keine Live-Ereignisquelle. ExecWeave bezeichnet nachbearbeitete Belege nicht als Live-Telemetrie.

Für stärkere Linux-Zuordnung nach dem Lauf verwenden Sie:

```bash
execweave record --backend strace --open -- claude
```

## Datenfluss

```text
Befehl
  ↓
portable Collector
  ↓
events.jsonl
  ↓
partielle Graphmaterialisierung
  ↓
lokaler HTTP-Server
  ↓
/graph.json
  ↓
Browser-Viewer
```

Der Browser pollt `/graph.json`, solange der Lauf aktiv ist. Jeder Snapshot wird aus denselben Phase-1-Ereignisstrom- und Phase-2-Graphverträgen aufgebaut wie die finalen Artefakte.

Wenn der Befehl endet, führt ExecWeave Folgendes aus:

1. validiert den abgeschlossenen Ereignisstrom;
2. schreibt `graph.json`;
3. schreibt den eigenständigen `viewer.html`;
4. markiert den Live-Graphen als abgeschlossen;
5. stellt den finalen Viewer kurz bereit und beendet anschließend den lokalen Server.

## Netzwerkfreigabe

Der Live-Server bindet ausschließlich an:

```text
127.0.0.1
```

Er wird nicht auf `0.0.0.0` bereitgestellt und soll nicht von anderen Hosts im LAN erreichbar sein.

Port explizit wählen:

```bash
execweave live --port 8765 --open -- claude
```

Port `0` ist der Standard und weist das Betriebssystem an, einen verfügbaren lokalen Port zu wählen.

## Artefakte

Das Standard-Laufverzeichnis ist:

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

Ein anderes Verzeichnis wählen:

```bash
execweave live --output-dir my-live-run --open -- claude
```

Bestehende, nicht leere Artefakte werden abgelehnt statt überschrieben.

## Unvollständige Snapshots

Während eines Live-Laufs ist `events.jsonl` absichtlich unvollständig, weil die Sitzung noch nicht beendet ist.

Live-Graph-Snapshots verwenden daher den `allow_incomplete`-Modus des Graph-Builders. Strukturelle Validierung bleibt aktiv: fehlerhaftes JSON, inkonsistente Sitzungen, ungültige Entitäten oder beschädigte Sequenzreihenfolgen gelten nicht als gültige Graphbelege.

Der finale Graph wird erst erstellt, nachdem die normale Validierung der vollständigen Sitzung erfolgreich war.

## Einschränkungen des portablen Backends

Das aktuelle Live-MVP erbt die Garantien des portablen Collectors:

- Prozesserkennung erfolgt per Polling;
- sehr kurzlebige Prozesse können verpasst werden;
- Dateisystemänderungen werden mit der Sitzung korreliert statt Prozessen zugeordnet;
- Netzwerkinspektion pro Prozess hängt von Sichtbarkeit und Berechtigungen des Betriebssystems ab.

Diese Einschränkungen bleiben in den Zuordnungsmetadaten der Ereignisse sichtbar. Der Live-Viewer wertet eine nicht kausale Beobachtung nicht zu einer kausalen Kante auf.

## Zukünftige native Live-Backends

Geplante Collector umfassen:

- Linux eBPF;
- Windows ETW;
- macOS Endpoint Security.

Ziel ist, dieselbe ExecWeave-Ereignissemantik zu erhalten und gleichzeitig Vollständigkeit, Prozesszuordnung und Laufzeit-Overhead zu verbessern.

## CI-Abdeckung

Die CI-Konfiguration des Repositorys enthält einen `live`-Smoke-Pfad, der:

- eine lokale Live-Sitzung startet;
- einen kurzen Befehl ausführt;
- finale Artefakte schreibt;
- `events.jsonl` validiert;
- den resultierenden Graphen zusammenfasst.

Unit-/Integrationstests prüfen außerdem den lokalen `/graph.json`-Endpoint direkt.
