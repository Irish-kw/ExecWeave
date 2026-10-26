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

Der Live-Runtime-Collector verwendet bewusst das plattformübergreifende `portable`-Backend. Seit v0.6.4 kann jeder Live-Lauf zusätzlich einen zweiten append-only Strom spezialisierter Belege über einen laufbezogenen Sidecar aufnehmen.

ExecWeave exportiert den Sidecar-Pfad an den gestarteten Befehl als:

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Spezialisierte Belege können über mehrere attribution-sichere Wege automatisch eintreffen:

- konfigurierte Hooks für Claude Code, OpenAI Codex, Antigravity und Cursor;
- das installierte OpenCode-Plugin;
- Loopback-Model-Catalog-Probes, wenn ExecWeave erkannte lokale Ollama-, llama.cpp- oder vLLM-Server startet;
- ein success-gated LM-Studio-Post-Launch-Probe für `lms server start --port <port>`, sofern vor dem Start kein kompatibler Endpoint existierte;
- der ExecWeave-Custom-Callback für LiteLLM Proxy, nachdem er einmal konfiguriert wurde und der Proxy innerhalb der aktuellen `execweave live`-Umgebung gestartet wird.

Das bedeutet **nicht**, dass `live` Anbieter-, Gateway- oder Runtime-Einstellungen stillschweigend verändert. Hook-/Plugin-/Callback-Integrationen müssen dort, wo nötig, einmal eingerichtet werden. Automatische Model-Runtime-Probes sind auf erkannte lokale Startbefehle und Loopback-Endpoints beschränkt. OpenRouter-Routing-Metadaten bleiben nicht automatisch, weil entfernte HTTPS-/Netzwerkbeobachtung keine autoritativen Provider-Routingdetails offenlegt.

Das Linux-Backend `strace` parst Trace-Dateien derzeit erst nach dem Ende des Befehls. Es liefert stärkere, auf Systemaufrufen basierende Zuordnung, ist in der aktuellen Implementierung jedoch keine Live-Ereignisquelle. ExecWeave bezeichnet nachbearbeitete Belege nicht als Live-Telemetrie.

Für stärkere Linux-Zuordnung nach dem Lauf:

```bash
execweave record --backend strace --open -- claude
```

## Datenfluss in v0.6.4

```text
specialized producers ─┐
  Agent hooks/plugin   │
  model-runtime probe  ├─→ semantic.jsonl ────────────────┐
  LiteLLM callback     │                                  │
                      ─┘                                  │
                                                         ↓
Befehl ─→ portable ─→ events.jsonl ───────→ incremental live normalizer
                                                         ↓
                                                  GraphAccumulator
                                                         ↓
                                              localhost HTTP server
                                                         ↓
                                                 /live.json deltas
                                                         ↓
                                                   browser / Top
```

OS-Runtime-Belege bleiben der unabhängige Ground-Truth-Strom. Spezialisierte Belege werden nur vorläufig in den Live-Graph normalisiert; sie dürfen weder den rohen Runtime-Strom umschreiben noch fehlende Belege erzeugen.

Browser und abgekoppeltes `execweave top`-Dashboard konsumieren sequenznummerierte `/live.json`-Snapshots/Deltas. `/graph.json` bleibt als aktueller Snapshot-Endpunkt verfügbar. Die inkrementelle Aufnahme liest nur neu angehängte JSONL-Bytes und puffert eine unvollständige letzte Zeile bis zu ihrem Zeilenumbruch.

Wenn der Befehl endet, führt ExecWeave Folgendes aus:

1. validiert den abgeschlossenen Runtime-Ereignisstrom;
2. vervollständigt jede vorbereitete, attribution-sichere Post-Command-Spezialbeobachtung;
3. führt bei vorhandenen spezialisierten Belegen die kanonische Runtime+Specialized-Zusammenführung nach `events.semantic.jsonl` aus;
4. baut den finalen Graphen aus diesem kanonischen Strom neu auf, statt dem vorläufigen Live-Zustand zu vertrauen;
5. schreibt `graph.json` und den eigenständigen `viewer.html`;
6. markiert den Live-Graph als abgeschlossen und stellt den finalen Viewer kurz bereit, bevor der lokale Server beendet wird.

Wenn keine spezialisierten Ereignisse eintreffen, bleibt die finale Materialisierung runtime-only.

## Automatisch sichtbare spezialisierte Integrationen

| Integration | Automatische Lieferung in den v0.6.4 Live Viewer |
| --- | --- |
| Claude Code | **Ja**, nachdem die ExecWeave-Hooks konfiguriert wurden |
| OpenAI Codex | **Ja**, nachdem die ExecWeave-Hooks konfiguriert wurden |
| Antigravity | **Ja**, nachdem die ExecWeave-Hooks konfiguriert wurden |
| Cursor | **Ja**, nachdem die ExecWeave-Hooks konfiguriert wurden |
| OpenCode | **Ja**, nachdem das ExecWeave-Plugin installiert wurde |
| Ollama | **Ja**, für erkannte lokale `ollama serve`-Starts |
| llama.cpp | **Ja**, für erkannte lokale `llama-server`-Starts |
| vLLM | **Ja**, für erkannte lokale vLLM-Server-Starts |
| LM Studio | **Ja**, nach erfolgreichem `lms server start --port <port>`, wenn der Endpoint vorher nicht existierte |
| LiteLLM Proxy | **Ja**, nachdem der ExecWeave-Callback konfiguriert wurde und der Proxy den Live-Sidecar erbt |
| OpenRouter | **Nein** für automatische Routing-Metadaten; OS-/Netzwerkaktivität des lokalen Clients kann weiterhin beobachtet werden |

Diese Integrationen teilen denselben laufbezogenen Specialized-Sidecar-Vertrag, behalten aber ihre Belegschichten und Semantik. Ein Model-Katalog beweist nicht, dass ein Agent eine Anfrage verursacht hat; eine Gateway-Antwort beweist nicht, welcher OS-Prozess sie verursacht hat; fehlende Identität wird niemals erfunden.

## Terminal Top

`top` rendert nicht über dem Agent-Terminal. Das ursprüngliche Terminal bleibt interaktiv, während sich das Dashboard in einem separaten Terminalfenster an dieselbe localhost-Live-Sitzung anhängt:

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

`events.jsonl` bleibt runtime-only. `semantic.jsonl` ist der rohe spezialisierte Sidecar und kann Agent/IDE-, Model-Runtime- oder Inference-Gateway-Belege enthalten. Der finale `graph.json` wird bei vorhandenen spezialisierten Belegen aus `events.semantic.jsonl` erstellt, andernfalls direkt aus `events.jsonl`.

Ein anderes Verzeichnis wählen:

```bash
execweave live --output-dir my-live-run --open -- claude
```

Bestehende, nicht leere Artefakte werden abgelehnt statt überschrieben.

## Vorläufige Live-Normalisierung

Während eines Live-Laufs können beide JSONL-Ströme unvollständig sein, weil die Sitzung noch nicht beendet ist.

Der Live-Normalizer arbeitet deshalb inkrementell und konservativ. Bereits beobachtete Runtime-Prozessidentität kann zur Auflösung spezialisierter Prozessreferenzen verwendet werden, fehlende Identität wird jedoch niemals geraten. Spezialisierte Ereignisse, die noch nicht normalisiert werden können, werden nicht zu stärkeren Belegen, nur weil sie live gesehen wurden.

Eine Trunkierung des Sidecars setzt die vorläufige Materialisierung zurück und spielt die aktuellen Dateien erneut ein. Unvollständige abschließende JSONL-Datensätze werden gepuffert statt als vollständige Ereignisse behandelt. Der finale Graph wird weiterhin nach erfolgreicher Runtime-Validierung aus der kanonischen Zusammenführung neu aufgebaut.

## Grenze automatischer Model-Runtime-Probes

Automatische Model-Runtime-Beobachtung ist bewusst eng begrenzt. ExecWeave probt nur erkannte lokale Server-Startbefehle und Local-/Loopback-Endpoints. Probe-Fehler sind fail-open und verändern niemals das Ergebnis des gestarteten Befehls.

Bei Ollama, llama.cpp und vLLM kann lokaler Model-State/-Katalog während des Serverlaufs abgetastet werden. LM Studio unterscheidet sich: `lms server start` ist ein kurzlebiger Launcher für einen persistenten Server. ExecWeave bereitet die Beobachtung vor dem Start vor, ordnet einen bereits vorhandenen kompatiblen Endpoint nicht der aktuellen Sitzung zu und materialisiert den Post-Launch-Katalog nur nach erfolgreichem Launcher-Exit.

Katalogrelationen behalten Runtime-spezifische Semantik. Beispielsweise ist die Katalogsichtbarkeit von LM Studio `ADVERTISES_MODEL` und kein Beweis dafür, dass Gewichte zu diesem Zeitpunkt im Speicher resident waren.

## Grenze des LiteLLM-Callbacks

LiteLLM Proxy kann `execweave.litellm_callback.execweave_litellm_callback` einmal über seine Custom-Callback-Konfiguration laden. Läuft der Proxy innerhalb von `execweave live`, erbt er `EXECWEAVE_SEMANTIC_SIDECAR` und schreibt nur whitelisted Routing-/Usage-Metadaten in diesen Lauf.

Der Callback speichert keine Messages, Response-Inhalte, Model-Parameter, beliebige Metadaten, API-Key-Metadaten oder Provider-`api_base`. Provider-Identität wird nicht aus Model-Strings oder URLs hergeleitet. Ohne laufbezogene Sidecar-Umgebungsvariable ist der Callback ein No-op.

LiteLLM-Konfigurationsfragment ausgeben:

```bash
execweave-litellm-callback --print-config
```

## Einschränkungen des portablen Backends

Die aktuelle Live-Runtime-Schicht erbt die Einschränkungen des portablen Collectors:

- Prozesserkennung erfolgt per Polling;
- sehr kurzlebige Prozesse können verpasst werden;
- Dateisystemänderungen werden mit der Sitzung korreliert statt Prozessen zugeordnet;
- Netzwerkinspektion pro Prozess hängt von Sichtbarkeit und Berechtigungen des Betriebssystems ab.

Diese Einschränkungen bleiben in den Zuordnungsmetadaten der Ereignisse sichtbar. Der Live Viewer wertet eine nicht kausale Beobachtung nicht zu einer kausalen Kante auf.

## Sicherheit für große Sitzungen

Live-Aktualisierungen verwenden eine begrenzte Delta-Historie, anstatt bei jeder Abfrage den vollständigen Ereignisstrom erneut einzulesen. Überschreitet der Graph das Sicherheitsbudget des Viewers, wechselt der Live-Endpunkt zu einer kompakten Payload nur mit Zählerwerten, damit Sammlung und finale kanonische Artefakterzeugung weiterlaufen können, ohne den Browser zur Materialisierung eines unsicheren großen SVG-Graphen zu zwingen.

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
- Sidecar-Ankunft, bevor Runtime-Identität verfügbar ist;
- Sidecar-Trunkierung und Replay;
- kanonischen finalen Runtime+Specialized-Neuaufbau;
- automatische Shared-Sidecar-Lieferung für Claude, Codex, Antigravity, Cursor und OpenCode;
- automatische lokale Model-Runtime-Probes für Ollama, llama.cpp und vLLM sowie attribution-sichere LM-Studio-Startbehandlung;
- Datenschutz, fail-open Verhalten und finale Live-Graph-Materialisierung des LiteLLM-Callbacks;
- abgekoppeltes Top-Verhalten ohne Start eines zweiten Agent;
- Top-Attach-URLs ausschließlich auf localhost;
- Clean-Wheel-Installation des LiteLLM-Callback-Setup-Befehls.
