<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-1-runtime-collection.md">English</a> |
  <a href="phase-1-runtime-collection.zh-TW.md">繁體中文</a> |
  <a href="phase-1-runtime-collection.zh-CN.md">简体中文</a> |
  <a href="phase-1-runtime-collection.ja.md">日本語</a> |
  <a href="phase-1-runtime-collection.ko.md">한국어</a> |
  <a href="phase-1-runtime-collection.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="phase-1-runtime-collection.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 1 — Laufzeiterfassung

Phase 1 stellt einen lokalen, graphbereiten Laufzeit-Ereignisstrom bereit, den Phase 2 in einen Ausführungsgraphen umwandeln kann.

## Status

**Phase 1 ist für den Linux-Referenzpfad und den portablen Fallback abgeschlossen.**

ExecWeave bietet jetzt zwei Erfassungs-Backends:

- `strace` — Linux-Erfassung auf Basis von Systemaufrufen. Erfasst kurzlebige Nachkommen sowie prozesszugeordnete Datei-/Netzwerkaktionen anhand von Syscall-Belegen.
- `portable` — psutil + watchdog als Fallback für Linux, macOS und Windows. Prozess-/Netzwerkereignisse werden per Polling erfasst; Dateisystemänderungen werden mit der Sitzung korreliert und ausdrücklich als nicht kausal markiert.

`auto` bevorzugt unter Linux `strace`, wenn es installiert ist, und wählt andernfalls `portable`.

```bash
execweave doctor
execweave run --backend auto -- claude
```

## Installation

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Installieren Sie unter Debian/Ubuntu das Linux-Referenzbackend mit:

```bash
sudo apt-get install strace
```

Anschließend:

```bash
execweave run -- claude
execweave run -- codex
execweave run -- agy
execweave run -- opencode
execweave run -- python my_agent.py
```

Ereignisse werden lokal geschrieben nach:

```text
.execweave/runs/<session-id>.jsonl
```

Rohe `strace`-Dateien werden nach dem Parsen standardmäßig gelöscht. Bewahren Sie sie nur zum Debuggen auf:

```bash
execweave run --keep-native-trace -- claude
```

## Ende-zu-Ende-Verifikation von Phase 1

Ein Phase-1-Lauf kann geprüft werden, ohne bereits den Phase-2-Graphen zu erstellen:

```bash
execweave doctor
execweave run --output run.jsonl -- python my_agent.py
execweave validate run.jsonl
execweave benchmark --backend auto --iterations 5
```

`execweave validate` prüft den Vertrag des Ereignisstroms, darunter:

- gültige JSONL-Datensätze;
- genau eine Sitzungs-ID pro Datei;
- eindeutige Ereignis-IDs;
- lückenlose Sequenznummern ab 1;
- gültige Zeitstempel;
- erforderliche Ereignis-/Entitätsfelder;
- genau ein `session.started` und ein `session.finished` für einen abgeschlossenen Lauf.

Für einen unterbrochenen Lauf, dem legitimerweise `session.finished` fehlt:

```bash
execweave validate --allow-incomplete run.jsonl
```

ExecWeave verweigert standardmäßig auch die Wiederverwendung einer bestehenden, nicht leeren Ausgabedatei. Dadurch wird verhindert, dass ein zweiter Lauf stillschweigend eine neue Sitzung mit neu gestarteter Sequenzzählung an denselben Ereignisstrom anhängt.

## Backend-Fähigkeitsmodell

### Linux-Backend `strace`

Das native Referenzbackend von Phase 1 verfolgt Nachkommen mit `strace -ff` und zeichnet auf Systemaufrufen basierende Kanten auf.

Es kann Beziehungen wie diese erzeugen:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --DELETED--> file
process --RENAMED_TO--> file
process --CHANGED_CWD_TO--> directory
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
process --EXITED--> ...
```

Diese Ereignisse enthalten:

```json
{
  "attribution": "syscall",
  "causal": true,
  "backend": "strace"
}
```

`OPENED_READ` und `OPENED_WRITE` beschreiben den durch den Open-Systemaufruf nachgewiesenen Zugriffsmodus. Sie behaupten absichtlich **nicht**, dass später tatsächlich ein `read()` oder `write()` auf Byte-Ebene stattfand. Bytegenaues Datenfluss-Tracking gehört in einen späteren Collector.

### Portables Backend

Das portable Backend startet den Befehl direkt und verwendet psutil/watchdog.

Es kann Folgendes erzeugen:

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Dateisystemänderungen bleiben explizite Sitzungsbeobachtungen:

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

Dadurch präsentiert ExecWeave zeitliche Korrelation nicht als kausale Zuordnung.

## Ereignisreihenfolge und Identität

Der JSONL-Sink fügt jedem Ereignis eines Laufs eine monoton steigende `sequence`-Nummer hinzu. Zeitstempel werden separat beibehalten.

Portable Prozess-IDs verwenden PID + Prozess-Erstellungszeit, da Betriebssysteme PIDs wiederverwenden.

Das Linux-Syscall-Backend begrenzt Prozess-IDs auf die ExecWeave-Sitzung:

```text
process:<session-id>:<pid>
```

Eine Prozessidentität wird daher niemals global allein aus einer PID abgeleitet.

Der strace-Parser führt außerdem vor dem Ausgeben von Graphereignissen einen Prozess-Eltern-Pass durch. Dadurch wird verhindert, dass ein Kindprozess fälschlich als Sitzungswurzel markiert wird, wenn ein Trace-Eintrag des Kindes und der `clone()`/`fork()`-Eintrag des Elternprozesses in getrennten Trace-Dateien denselben Zeitstempel haben.

## Kurzlebige Prozesse

Das portable Backend kann einen Prozess verpassen, der vollständig zwischen zwei Polling-Intervallen startet und endet.

Das Linux-Referenzbackend beseitigt diese Lücke in Phase 1, indem es Prozess-Systemaufrufe verfolgt und Nachkommen mit `strace -ff` folgt. Die CI enthält einen Integrationstest, der einen kurzlebigen Kindprozess startet und prüft, dass eine `SPAWNED`-Kante ausgegeben wird.

## Zuordnung von Dateisystempfaden

Der Linux-Parser verfolgt Arbeitsverzeichnisse pro Prozess und behandelt gängige `*at`-Systemaufrufe. Relative Pfade werden anhand der besten verfügbaren Syscall-Belege aufgelöst.

Bei seltenen dirfd-Mustern kann die Pfadzuordnung weiterhin unvollkommen sein. Rohe Syscall-Namen und Pfade bleiben als Ereignisattribute erhalten, damit nachgelagerte Verbraucher nachvollziehen können, wie eine Kante zustande kam.

## Netzwerkzuordnung

Das Linux-Backend erfasst `connect()`-Syscall-Belege für:

- IPv4
- IPv6
- Unix-Domain-Sockets

Erfolgreiche Aufrufe erzeugen:

```text
process --CONNECTED_TO--> endpoint
```

Fehlgeschlagene oder asynchrone Aufrufe, einschließlich des üblichen nicht blockierenden Falls `EINPROGRESS`, bleiben erhalten als:

```text
process --CONNECT_ATTEMPTED--> endpoint
```

Das Ereignis behält das Syscall-Ergebnis und errno bei. ExecWeave meldet eine asynchrone Verbindungsanfrage daher weder fälschlich als bestätigte Verbindung noch als völliges Fehlen von Netzwerkaktivität.

Das portable Backend verwendet Socket-Inspektion pro Prozess, sofern das Betriebssystem sie dem aktuellen Benutzer zugänglich macht.

Ein fehlendes Ereignis darf bei einem Backend mit fehlender Berechtigung oder Abdeckung niemals als Beweis dafür interpretiert werden, dass keine Netzwerkaktion stattgefunden hat.

## Datenschutz

Laufzeittelemetrie kann sensible Pfade, Namen ausführbarer Dateien, Befehlsargumente und Endpunkte enthalten.

Phase 1 verwendet folgende Standardwerte:

- alle Ereignisdaten bleiben lokal;
- rohe Syscall-Trace-Dateien werden nach dem Parsen gelöscht, außer `--keep-native-trace` wurde angefordert;
- Dateiinhalte werden nicht verfolgt;
- Byte-Puffer aus `read()`/`write()` werden nicht gesammelt;
- `execve`-Argumente werden über eine Argumentanzahl hinaus nicht in Graphereignisse kopiert.

Der Sitzungs-Wrapper zeichnet dennoch den an ExecWeave übergebenen Befehl auf. Benutzer sollten daher keine Geheimnisse direkt in Befehlszeilen schreiben.

## Diagnose

```bash
execweave doctor
```

Beispiel:

```json
{
  "auto_selected": "strace",
  "platform": "linux",
  "portable": true,
  "strace": true
}
```

## Overhead-Benchmark-Harness

Phase 1 enthält einen wiederholbaren Smoke-Benchmark:

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

oder:

```bash
python benchmarks/phase1_overhead.py
```

Er meldet rohe Basis-/Instrumentierungszeiten, Mediane und ein Overhead-Verhältnis. Dies sind umgebungsspezifische Messungen und keine veröffentlichte Leistungsbehauptung.

## CI-Vertrag

Die GitHub-Actions-Matrix läuft unter Linux, macOS und Windows mit unterstützten Python-Versionen.

Zusätzlich zu Unit-Tests und Linting führt die CI nun aus:

1. `execweave doctor`;
2. einen portablen Ende-zu-Ende-Lauf;
3. `execweave validate` auf diesem portablen Strom;
4. einen Linux-`strace`-Ende-zu-Ende-Lauf;
5. Validierung des nativen Linux-Stroms;
6. einen Phase-1-Benchmark-Smoke-Test.

Damit wird Phase 1 als tatsächlicher CLI-Workflow getestet und nicht nur als isolierte Python-Funktionen.

## Akzeptanzkriterien

- [x] Expliziter ExecWeave-Sitzungs-Wrapper
- [x] Graphbereites Ereignisschema
- [x] Monotone Ereignis-Sequenznummern
- [x] Erfassung des Wurzelprozesses
- [x] Erfassung von Eltern-/Kindprozessen
- [x] Portable Dateisystembeobachtung
- [x] Portable Netzwerkbeobachtung pro Prozess
- [x] Zuverlässige Erfassung kurzlebiger Linux-Prozesse
- [x] Linux-Dateisystem-Syscall-Telemetrie mit Prozesszuordnung
- [x] Linux-Netzwerk-Syscall-Telemetrie mit Prozesszuordnung
- [x] Bewahrung asynchroner/fehlgeschlagener Netzwerkverbindungsversuche
- [x] Stabile Elternzuordnung bei Trace-Einträgen mit gleichem Zeitstempel
- [x] Automatische Backend-Auswahl und Fähigkeitsdiagnose
- [x] Standardmäßiges Löschen roher nativer Traces
- [x] Plattformübergreifender portabler Fallback
- [x] Integritätsvalidator für den Ereignisstrom
- [x] Schutz vor versehentlichem Anhängen mehrerer Sitzungen
- [x] Unit-Tests für Parser, Validator und Backend-Auswahl
- [x] Nativer Linux-Integrationstest in der CI
- [x] Ende-zu-Ende-CLI-Smoke-Validierung in der CI
- [x] Overhead-Benchmark-Harness

## Explizit außerhalb von Phase 1

Folgende Punkte bleiben zukünftige Arbeit und werden nicht fälschlich als abgeschlossen markiert:

- Windows-ETW-Backend mit prozesszugeordneter Dateisystemerfassung
- macOS-Endpoint-Security-Backend mit Prozesszuordnung
- Linux-eBPF-Backend zur Reduzierung des ptrace-Overheads
- DNS-zu-Domain-Korrelation
- Bytegenaues Read/Write-Datenfluss-Tracking
- semantische Agent/Tool/MCP-Telemetrie
- Graphmaterialisierung und interaktive Visualisierung

Diese Fähigkeiten können dasselbe Ereignismodell speisen, ohne den Phase-1-Vertrag zu ändern.

## Warum `strace` vor eBPF?

Phase 1 benötigt eine korrektheitsorientierte Referenzimplementierung für Prozess-/Datei-/Netzwerkzuordnung und Ereignissemantik. `strace` ist leicht zu inspizieren, einfach zu testen und erfasst kurzlebige Nachkommen, ohne Kausalität zu erfinden.

Ein eBPF-Backend ist der natürliche nächste Optimierungsschritt für geringeren Overhead und dauerhafte Erfassung, sollte aber dieselbe Graphereignis-Semantik implementieren, statt sie implizit neu zu definieren.

## Mitwirken

Nützliche nächste Beiträge umfassen Linux eBPF, Windows ETW, macOS Endpoint Security, Pfad-/Entitätsauflösung, Overhead-Evaluierung, Datenschutz/Redaktion und reproduzierbare Agent-Workloads.

Bitte bewahren Sie bei neuen Collector-Backends die Unterscheidung zwischen nachgewiesener kausaler Zuordnung und Beobachtung auf Sitzungsebene.
