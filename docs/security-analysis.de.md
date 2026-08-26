<!-- i18n-nav:start -->
<p align="center">
  <a href="security-analysis.md">English</a> |
  <a href="security-analysis.zh-TW.md">繁體中文</a> |
  <a href="security-analysis.zh-CN.md">简体中文</a> |
  <a href="security-analysis.ja.md">日本語</a> |
  <a href="security-analysis.ko.md">한국어</a> |
  <a href="security-analysis.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="security-analysis.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Sicherheitsanalyse

ExecWeave enthält eine konservative, nachvollziehbare Regelschicht über einem abgeschlossenen Ausführungsgraphen.

```bash
execweave analyze run.graph.json
```

Denselben Bericht in eine Datei schreiben:

```bash
execweave analyze run.graph.json --output analysis.json
```

Das aktuelle Analyseschema ist `0.2`.

## Ziel

Die Analyseschicht priorisiert Graphbelege für die Prüfung. Sie behauptet nicht, dass ein Agent bösartig ist, nur weil er auf eine sensible Ressource zugegriffen oder das Netzwerk kontaktiert hat.

Die zentrale Regel lautet:

> **Koinzidenz oder Prozessabstammung nicht in Datenflussbehauptungen umwandeln.**

## Aktuelle Regeln

### Zugriff auf sensible Dateien

Die Regel sucht nach Dateikanten, die gängige sensible Speicherorte oder Dateinamen betreffen, darunter beispielsweise:

- `~/.ssh/*`
- `~/.aws/credentials`
- `~/.kube/config`
- Docker-Konfiguration
- `.npmrc`
- `.pypirc`
- `.netrc`
- `.env`
- gängige Dateinamen privater SSH-Schlüssel

Eine kausale, systemaufrufbasierte Prozesskante ist ein stärkerer Beleg als eine nicht kausale Sitzungsbeobachtung.

### Externer Netzwerkkontakt

Die Regel identifiziert Prozesskanten zu externen Netzwerkendpunkten und schließt offensichtliche Loopback-/private-/Link-Local-Adressen aus.

Die aktuelle Laufzeittelemetrie basiert hauptsächlich auf IP-Endpunkten. DNS-/Domain-Korrelation ist zukünftige Arbeit.

### Möglicher sensibler Datei-zu-Netzwerk-Pfad im selben Prozess

Wenn **derselbe Prozess** kausale Belege für den Zugriff auf eine sensible Datei und danach kausale externe Netzwerkaktivität aufweist, erzeugt ExecWeave einen Priorisierungsbefund.

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

Der Befund speichert:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

Der Graph beweist, dass der Prozess beide Aktionen in chronologischer Reihenfolge ausgeführt hat. Er beweist **nicht**, dass Bytes aus der Datei über die Verbindung übertragen wurden.

### Möglicher delegierter sensibler Datei-zu-Netzwerk-Pfad

Analyseschema `0.2` folgt außerdem chronologischen kausalen `SPAWNED`-Kanten.

Beispiel:

```text
parent process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── SPAWNED ──────→ child process
                         └── CONNECTED_TO ─→ external endpoint
```

Ein delegierter Befund wird nur ausgegeben, wenn:

1. die Kante zum Zugriff auf die sensible Datei kausal ist;
2. die `SPAWNED`-Kante oder -Kette kausal ist;
3. die Spawn-Sequenz nach der Sequenz des sensiblen Dateizugriffs liegt;
4. der externe Netzwerkbeleg des Nachkommen nach der Spawn-Kette liegt;
5. die Pfadtiefe innerhalb der konservativen Traversierungsgrenze des Analyzers bleibt.

Dies beweist einen chronologischen Prozessabstammungspfad. Es beweist weiterhin **nicht**, dass das Kind Dateidaten vom Elternprozess erhalten hat.

Delegierte Befunde speichern ausdrücklich:

```json
{
  "causal_process_lineage": true,
  "data_inheritance_proven": false,
  "ipc_proven": false,
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

`SPAWNED` ist ein Beleg für Prozesserzeugung/-abstammung, nicht für Speichervererbung, Pipe-Schreibvorgänge, socketpair-Transfer, Shared-Memory-Transfer, Übertragung von Geheimnissen über Umgebungsvariablen oder irgendeine andere konkrete Datenbewegung.

Tatsächliche Datenfluss- oder Exfiltrationsbehauptungen erfordern stärkere Belege wie Taint Tracking, IPC-bewusste Provenienz oder bytegenaue Read-/Write-/Netzwerktelemetrie.

## Schweregrad

Schweregrade sind Priorisierungsstufen und keine Schwachstellenscores:

- `high`
- `medium`
- `low`
- `info`

Aktuelle Beispiele:

- externe Verbindung allein: informativ;
- Zugriff auf sensible Datei: abhängig von Relation und Stärke der Zuordnung;
- sensibler Lesezugriff im selben Prozess gefolgt von bestätigter externer Verbindung: Signal hoher Priorität;
- delegierter Kindprozess-Pfad: niedriger als ein äquivalenter Pfad im selben Prozess, weil der Datentransfer über die Prozessgrenze nicht bewiesen ist.

## Backend-Abhängigkeit

Die Analysequalität wird durch die Qualität des Collectors begrenzt.

Das Linux-Referenzbackend `strace` kann für unterstützte Operationen prozesszugeordnete Syscall-Belege liefern. Das portable Backend besitzt eine schwächere Dateisystemzuordnung und kann daher dieselben Schlussfolgerungen auf Prozessebene nicht stützen.

Der Analyzer respektiert die `causal`-Metadaten des Graphen, statt schwächere Belege aufzuwerten.

## Ausgabe

Der Bericht enthält:

- Analyseschema-Version
- Sitzungs-ID
- Gesamtzahl der Befunde
- Anzahl nach Schweregrad
- explizite Einschränkungen
- Regel-ID pro Befund
- Titel und Zusammenfassung
- zugehörige Knoten-IDs
- zugehörige Kanten-IDs
- Ereignis-IDs der Belege
- regelspezifische Attribute

Delegierte Befunde enthalten zusätzlich die Prozesskette, Anzahl der Delegationssprünge, Spawn-Sequenzen und explizite Negativgarantien zu Datenvererbung/IPC/Datenfluss.

## Zukünftige Analyseschichten

Mögliche Erweiterungen umfassen:

- Auflösung von Credential- und Secret-Entitäten
- DNS-/Domain-Korrelation und Kontext
- explizite IPC-Kanten
- Provenienz von Umgebungsvariablen und geerbten Handles
- semantischer Agent-/Tool-/MCP-Kontext
- Anomalieerkennung
- Ranking von Angriffspfaden
- bytegenaues Datenfluss-/Taint-Tracking
- Laufzeitrichtlinien allow / warn / block

Diese Erweiterungen sollten weiterhin klar zwischen beobachteten Belegen, inferiertem Risiko, Prozessabstammung und nachgewiesenem kausalem Datenfluss unterscheiden.
