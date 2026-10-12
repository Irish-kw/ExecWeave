# Run-Integrität

<!-- i18n-nav:start -->
<p align="center">
  <a href="run-integrity.md">English</a> |
  <a href="run-integrity.zh-TW.md">繁體中文</a> |
  <a href="run-integrity.zh-CN.md">简体中文</a> |
  <a href="run-integrity.ja.md">日本語</a> |
  <a href="run-integrity.ko.md">한국어</a> |
  <a href="run-integrity.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="run-integrity.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave v0.6.5 kann einen abgeschlossenen run als deterministisches SHA-256 inventory versiegeln und dieses inventory später verifizieren. Die Funktion dient der Erkennung lokaler Beschädigungen und Änderungen nach dem Seal. Wenn Manifest und Evidence in derselben beschreibbaren trust boundary verbleiben, wird dies bewusst nicht als gegen Angreifer resistentes tamper evidence bezeichnet.

## Geltungsbereich

`execweave-integrity seal` inventarisiert rekursiv alle regular files im ausgewählten run directory, mit Ausnahme von `integrity.json` selbst. Die Einträge werden deterministisch nach relative POSIX path sortiert und enthalten path, Byte-Größe und SHA-256 digest. Symbolic links werden abgelehnt, statt ihnen zu folgen oder sie stillschweigend zu normalisieren.

Das Seal soll erst erstellt werden, nachdem Capture und alle gewünschten derived artifacts abgeschlossen sind. Eine nach dem Seal angelegte Datei wird als unsealed gemeldet; Änderungen, Ersetzungen oder Löschungen eines sealed file führen zu einer fehlgeschlagenen Verifikation.

## Seal und verify

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

`seal` überschreibt keinen vorhandenen integrity contract. `verify` ist nur erfolgreich, wenn das manifest schema gültig ist, der manifest body digest übereinstimmt, jedes sealed file die erwartete Größe und den erwarteten SHA-256 besitzt und seit dem Seal kein zusätzliches regular file hinzugekommen ist.

## Manifest contract

| Feld | Bedeutung |
| --- | --- |
| `schema_version` | Version des Integrity schema; v0.6.5 beginnt mit `0.1`. |
| `files` | Deterministisch geordnetes Inventory der sealed files. |
| `manifest_body_sha256` | SHA-256 des canonical manifest content ohne dieses Digest-Feld. |
| `trust_model` | Explizite Aussage darüber, was das local seal beweist und nicht beweist. |


## Grenzen der ausschließlich lokalen Prüfung

<!-- ew:trust:local-only -->

Lokales `seal` / `verify` erkennt unbeabsichtigte Beschädigungen und Änderungen ohne erneutes Versiegeln. **Wer die Aufzeichnungen und `integrity.json` schreiben darf, kann Hashes neu berechnen und konsistente Daten erneut versiegeln.** `valid: true` bestätigt nur lokale Konsistenz, nicht ein manipulationssicheres Audit.

<!-- ew:trust:privileged -->

Root, sudo-berechtigte Agents sowie alle Prozesse mit Schreibzugriff auf das Ausgabeverzeichnis können Aufzeichnungen und Manifest gemeinsam ändern. Betriebssystemrechte und Prozessisolation sind erforderlich; ein anderer Pfad mit denselben Rechten ist keine Isolation.

<!-- ew:compat:no-downgrade -->

**Das Downgrade des Readers von v0.8.35+ auf v0.8.34 wird nicht unterstützt.** Der ältere Reader kann `observation_assessment` unbemerkt verwerfen und Beobachtungen irreführend darstellen. Nur Schlussfolgerungen von Readern ab v0.8.35 sind maßgeblich. Ein Recorder-Rollback rechtfertigt keinen Reader-Rollback.

Nur abgeschlossene Runs versiegeln und vor Nutzung archivierter Daten prüfen. Eine fehlgeschlagene Prüfung beweist eine lokale Inkonsistenz, nicht automatisch einen Angriff. Das Tool lädt weder Daten noch Digests hoch und schafft keine unabhängige Berechtigungsgrenze.
