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

Das Manifest enthält zwingend `malicious_writer_resistance: false` und `external_trust_anchor: false`. Diese Werte sind Bestandteil des schema contract und keine optionale Formulierung der Dokumentation.

## Trust boundary

Ein local digest ist nützlich, um accidental corruption, unvollständige Kopien oder post-seal changes relativ zum Zeitpunkt des Seal zu erkennen. Er verhindert jedoch nicht, dass ein process mit Schreibzugriff auf sowohl run evidence als auch `integrity.json` beide neu schreibt. Ein solcher process kann die hashes neu berechnen und ein neues intern konsistentes Manifest erzeugen.

Für eine stärkere Garantie muss `manifest_body_sha256` oder das vollständige Manifest an einen Ort außerhalb der write boundary des observed process kopiert oder mit einem für diesen process nicht verfügbaren key geschützt bzw. signiert werden. Erst diese externe Maßnahme erzeugt den trust anchor; ExecWeave behauptet nicht, dass ein Manifest im selben directory allein einen solchen Anker schafft.

## Betriebsregeln

Versiegeln Sie nur einen abgeschlossenen run. Verifizieren Sie archived oder transferred evidence, bevor Sie sich darauf verlassen. Eine verification error bedeutet, dass das directory nicht mehr exakt dem sealed inventory entspricht; sie ist kein Beweis für bösartige Aktivität. Müssen nach dem Seal weitere artifacts erzeugt werden, erstellen Sie diese zuerst und versiegeln Sie anschließend eine neue finalized copy, statt das ursprüngliche Manifest still zu überschreiben.
