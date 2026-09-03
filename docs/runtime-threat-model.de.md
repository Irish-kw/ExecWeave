<!-- i18n-nav:start -->
<p align="center">
  <a href="runtime-threat-model.md">English</a> |
  <a href="runtime-threat-model.zh-TW.md">繁體中文</a> |
  <a href="runtime-threat-model.zh-CN.md">简体中文</a> |
  <a href="runtime-threat-model.ja.md">日本語</a> |
  <a href="runtime-threat-model.ko.md">한국어</a> |
  <a href="runtime-threat-model.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="runtime-threat-model.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Runtime-Bedrohungsmodell und bekannte Umgehungsgrenzen

Dieses Dokument definiert die Beobachtungsgrenzen, die ExecWeave v0.6.5 als Teil seines testbaren Vertrags behandelt. Es ist ein **Bedrohungsmodell für Observability**, keine Sandbox-Sicherheitsgarantie: Der beobachtete Befehl kann nicht vertrauenswürdig sein und versuchen, Aktivitäten schwer beobachtbar zu machen; gleichzeitig wird angenommen, dass Betriebssystem-Kernel und ExecWeave-Installation nicht auf Kernel-Ebene kompromittiert sind.

## Portable backend

Der portable backend verwendet psutil snapshots für process/network-Aktivität und watchdog für filesystem-Änderungen.

- **Kurzlebige process:** Ein child, der vollständig zwischen zwei process samples startet und endet, kann verpasst werden. Das konfigurierte poll interval ist keine garantierte Obergrenze des blind window, da scheduler delays den tatsächlichen Abstand verlängern können.
- **Kurzlebige sockets:** Eine Verbindung, die zwischen zwei socket observations entsteht und wieder verschwindet, kann verpasst werden. Berechtigungen oder Einschränkungen der platform API können socket state ebenfalls verbergen.
- **Descendants, die länger als der root command leben:** Ist ein child beim Ende der root observation noch aktiv, erfindet ExecWeave kein exit event. Ein portable run ist jedoch kein always-on monitor; spätere Aktivität eines überlebenden oder reparented descendant liegt außerhalb des Beobachtungsfensters des abgeschlossenen Runs.
- **Filesystem attribution:** watchdog-Änderungen sind session-correlated observations und bewusst `causal=false`. Sie beweisen nicht, dass ein bestimmter PID den Schreibvorgang ausgeführt hat.
- **Negative evidence:** Das Fehlen eines portable process/network/filesystem event ist kein Beweis dafür, dass die Aktivität nicht stattgefunden hat.

## Linux strace backend

Der strace backend folgt mit `strace -ff` der Lineage des gestarteten Commands und ausgewählten syscall classes.

- Innerhalb dieser traced lineage können clone/fork-Belege kurzlebige descendants erhalten, die portable polling verpassen könnte.
- Bei unterstütztem syscall evidence können filesystem/network events dem traced process zugeordnet werden.
- Dies ist **keine OS-wide visibility**. Aktivitäten außerhalb der traced lineage, nicht unterstützte oder nicht geparste syscall patterns, permission/ptrace-Beschränkungen und kernel behavior außerhalb der ausgewählten evidence classes liegen außerhalb der Aussage.
- Der read/write access mode eines open beweist keinen byte-level data flow. ExecWeave behauptet nicht, die später tatsächlich gelesenen oder geschriebenen Bytes zu kennen.

## Specialized hooks und direct API integrations

Claude, Codex, Antigravity, Cursor, OpenCode, model-runtime, gateway, proxy und direct-API integrations können an ihren expliziten integration points stärkere semantic content evidence liefern, legen aber keinen provider-hidden state offen.

- Eine response-only integration beweist nur die an ExecWeave übergebenen response fields.
- Ein caller-supplied request+response exchange beweist nur den bereitgestellten exchange und behauptet keine transparent wire interception.
- Die hook coverage ist darauf begrenzt, was der upstream agent oder die IDE dem Hook tatsächlich bereitstellt.
- Full-fidelity storage bedeutet vollständige Aufbewahrung der am integration point offengelegten Inhalte, nicht vollständige Sicht auf model provider oder Betriebssystem.

## Regression contract

`tests/test_threat_model.py` hält folgende Grenzen als deterministic executable tests fest:

1. ein portable child, das nur zwischen zwei process samples existiert;
2. ein portable socket, das nur zwischen zwei socket samples existiert;
3. ein beim Ende der root-process observation noch lebendes child, ohne ein exit event zu erfinden;
4. portable filesystem changes bleiben session-correlated und non-causal;
5. der entsprechende strace trace case behält die `SPAWNED` attribution eines kurzlebigen child bei.

Die Tests verwenden bewusst keine timing races nach dem Muster „N ms schlafen und hoffen, dass CI es verpasst“. Das blind window wird als expliziter Zustand zwischen observations modelliert, damit der Vertrag unter Linux, macOS und Windows reproduzierbar bleibt.

## Bedeutung eines missing event

Ein missing event bedeutet nur, dass die canonical evidence dieses Runs keine entsprechende observation enthält. Es ist kein Beweis für Nicht-Eintreten, solange ein zukünftiger backend nicht ausdrücklich einen vollständigen negative-evidence scope definiert und belegt. Finding severity und evidence fidelity bleiben getrennte Dimensionen.
