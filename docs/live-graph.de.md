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

Die Live-Runtime-Schicht verwendet bewusst das plattformübergreifende `portable`-Backend. In v0.6.4 kann die Live-Sitzung zusätzlich einen zweiten append-only Strom spezialisierter Belege über einen laufbezogenen semantischen Sidecar aufnehmen.

ExecWeave exportiert den Sidecar-Pfad an den gestarteten Befehl als:

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Bereits konfigurierte Hooks für Claude Code, OpenAI Codex, Gemini CLI und Cursor erben diese Variable automatisch. Das installierte OpenCode-Plugin tut dasselbe. Deren semantische Ereignisse können dadurch im selben Live Viewer erscheinen, ohne auf einen separaten `*-record`-Befehl wechseln zu müssen.

Das bedeutet **nicht**, dass `live` Anbieter-Einstellungen stillschweigend verändert. Die Hook-/Plugin-Integration muss einmal vorab eingerichtet worden sein. Model-Runtime- und Inference-Gateway-Metadaten benötigen weiterhin ihre expliziten Emitter, bis diese Integrationen einen automatischen Beobachtungspfad besitzen.

Das Linux-Backend `strace` parst Trace-Dateien derzeit erst nach dem Ende des Befehls. Es liefert stärkere, auf Systemaufrufen basierende Zuordnung, ist in der aktuellen Implementierung jedoch keine Live-Ereignisquelle. ExecWeave bezeichnet nachbearbeitete Belege nicht als Live-Telemetrie.

Für stärkere Linux-Zuordnung nach dem Lauf verwenden Sie:

```bash
execweave record --backend strace --open -- claude
```

## Datenfluss in v0.6.4

```text
                         ┌─ Provider-Hook / Plugin ─→ semantic.jsonl ─┐
Befehl ─→ portable ─→ events.jsonl ──────────────────────────────────┤
                                                                    ↓
                                                     inkrementeller Live-Normalizer
                                                                    ↓
                                                         GraphAccumulator
                                                                    ↓
                                                     localhost HTTP-Server
                                                                    ↓
                                                        /live.json-Deltas
                                                                    ↓
                                                          Browser / Top
```

OS-Runtime-Belege bleiben der unabhängige Ground-Truth-Strom. Spezialisierte Belege werden nur vorläufig in den Live-Graph normalisiert; sie dürfen weder den rohen Runtime-Strom umschreiben noch fehlende Belege erzeugen.

Der Browser und das abgekoppelte `execweave top`-Dashboard konsumieren sequenznummerierte `/live.json`-Snapshots/Deltas. `/graph.json` bleibt als aktueller Snapshot-Endpunkt verfügbar. Die inkrementelle Aufnahme liest nur neu angehängte JSONL-Bytes und puffert eine unvollständige letzte Zeile bis zu ihrem Zeilenumbruch.

Wenn der Befehl endet, führt ExecWeave Folgendes aus:

1. validiert den abgeschlossenen Runtime-Ereignisstrom;
2. führt bei vorhandenen spezialisierten Belegen die kanonische Runtime+Semantic-Zusammenführung nach `events.semantic.jsonl` aus;
3. baut den finalen Graphen aus diesem kanonischen Strom neu auf, statt dem vorläufigen Live-Zustand zu vertrauen;
4. schreibt `graph.json` und den eigenständigen `viewer.html`;
5. markiert den Live-Graph als abgeschlossen und stellt den finalen Viewer kurz bereit, bevor der lokale Server beendet wird.

Wenn keine spezialisierten Ereignisse eintreffen, bleibt die finale Materialisierung runtime-only.

## Automatisch sichtbare Agent-Integrationen

| Integration | Automatische Lieferung in den v0.6.4 Live Viewer |
| --- | --- |
| Claude Code | **Ja**, nachdem die ExecWeave-Hooks konfiguriert wurden |
| OpenAI Codex | **Ja**, nachdem die ExecWeave-Hooks konfiguriert wurden |
| Gemini CLI | **Ja**, nachdem die ExecWeave-Hooks konfiguriert wurden |
| Cursor | **Ja**, nachdem die ExecWeave-Hooks konfiguriert wurden |
| OpenCode | **Ja**, nachdem das ExecWeave-Plugin installiert wurde |

Alle fünf Integrationen verwenden denselben laufbezogenen Sidecar-Vertrag. Die CI-Regressionsabdeckung ruft jeden Provider-Adapter gegen ein gemeinsames `EXECWEAVE_SEMANTIC_SIDECAR` auf und prüft, dass die resultierenden Provider-Belege in den Live-Graph materialisiert werden.

## Terminal Top

`top` rendert nicht mehr über das Agent-Terminal. Das ursprüngliche Terminal bleibt für den Agent interaktiv, während das Dashboard in einem separaten Terminalfenster an dieselbe localhost-Live-Sitzung angehängt wird:

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open` ergänzt den Browser-Viewer. Das abgekoppelte Dashboard ist nur ein Attach-Client und startet niemals einen zweiten Agent. Seine interne Attach-URL ist auf HTTP über localhost beschränkt.

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
├── semantic.jsonl
├── events.semantic.jsonl      # nur bei vorhandenen spezialisierten Belegen materialisiert
├── graph.json
└── viewer.html
```

`events.jsonl` bleibt runtime-only. `semantic.jsonl` ist der rohe spezialisierte Sidecar. Der finale `graph.json` wird bei vorhandenen spezialisierten Belegen aus `events.semantic.jsonl` erstellt, andernfalls direkt aus `events.jsonl`.

Ein anderes Verzeichnis wählen:

```bash
execweave live --output-dir my-live-run --open -- claude
```

Bestehende, nicht leere Artefakte werden abgelehnt statt überschrieben.

## Vorläufige Live-Normalisierung

Während eines Live-Laufs können beide JSONL-Ströme unvollständig sein, weil die Sitzung noch nicht beendet ist.

Der Live-Normalizer arbeitet deshalb inkrementell und konservativ. Bereits beobachtete Runtime-Prozessidentität kann zur Auflösung spezialisierter Prozessreferenzen verwendet werden, fehlende Identität wird jedoch niemals geraten. Spezialisierte Ereignisse, die noch nicht normalisiert werden können, werden nicht zu stärkeren Belegen, nur weil sie live gesehen wurden.

Eine Trunkierung des Sidecars setzt die vorläufige Materialisierung zurück und spielt die aktuellen Dateien erneut ein. Unvollständige abschließende JSONL-Datensätze werden gepuffert statt als vollständige Ereignisse behandelt. Der finale Graph wird weiterhin nach erfolgreicher Runtime-Validierung aus der kanonischen Zusammenführung neu aufgebaut.

## Einschränkungen des portablen Backends

Die aktuelle Live-Runtime-Schicht erbt die Garantien des portablen Collectors:

- Prozesserkennung erfolgt per Polling;
- sehr kurzlebige Prozesse können verpasst werden;
- Dateisystemänderungen werden mit der Sitzung korreliert statt Prozessen zugeordnet;
- Netzwerkinspektion pro Prozess hängt von Sichtbarkeit und Berechtigungen des Betriebssystems ab.

Diese Einschränkungen bleiben in den Zuordnungsmetadaten der Ereignisse sichtbar. Der Live Viewer wertet eine nicht kausale Beobachtung nicht zu einer kausalen Kante auf.

## Sicherheit für große Sitzungen

Live-Aktualisierungen verwenden eine begrenzte Delta-Historie, anstatt bei jeder Abfrage den vollständigen Ereignisstrom erneut einzulesen. Überschreitet der Graph das Sicherheitsbudget des Viewers, wechselt der Live-Endpunkt zu einer kompakten Payload nur mit Zählerwerten, damit Sammlung und finale kanonische Artefakterzeugung weiterlaufen können, ohne den Browser zur Materialisierung eines unsicheren SVG-Graphen zu zwingen.

## Zukünftige native Live-Backends

Geplante Collector umfassen:

- Linux eBPF;
- Windows ETW;
- macOS Endpoint Security.

Ziel ist, dieselbe ExecWeave-Ereignissemantik zu erhalten und gleichzeitig Vollständigkeit, Prozesszuordnung und Laufzeit-Overhead zu verbessern.

## CI-Abdeckung

Die CI-Konfiguration des Repositorys deckt Folgendes ab:

- Start einer localhost-Live-Sitzung und finale Artefakterzeugung;
- sequenznummeriertes Snapshot-/Delta-Verhalten und Resynchronisierung;
- unvollständige abschließende JSONL-Datensätze;
- semantischen Sidecar, der eintrifft, bevor Runtime-Identität verfügbar ist;
- Trunkierung und Replay des semantischen Sidecars;
- kanonischen finalen Runtime+Semantic-Neuaufbau;
- automatische Shared-Sidecar-Lieferung für Claude, Codex, Gemini, Cursor und OpenCode;
- abgekoppeltes Top-Verhalten ohne Start eines zweiten Agent;
- Top-Attach-URLs ausschließlich auf localhost.
