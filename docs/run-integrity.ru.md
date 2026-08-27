# Целостность run

<!-- i18n-nav:start -->
<p align="center">
  <a href="run-integrity.md">English</a> |
  <a href="run-integrity.zh-TW.md">繁體中文</a> |
  <a href="run-integrity.zh-CN.md">简体中文</a> |
  <a href="run-integrity.ja.md">日本語</a> |
  <a href="run-integrity.ko.md">한국어</a> |
  <a href="run-integrity.fr.md">Français</a> |
  <a href="run-integrity.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

ExecWeave v0.6.5 может seal завершённый run в виде детерминированного SHA-256 inventory и позднее выполнить verify этого inventory. Функция предназначена для обнаружения локального повреждения и изменений после seal. Если manifest и evidence остаются в одной и той же доступной для записи trust boundary, эта возможность намеренно не описывается как tamper evidence, устойчивое к атакующему.

## Область действия

`execweave-integrity seal` рекурсивно инвентаризирует все regular files в выбранном run directory, кроме самого `integrity.json`. Записи детерминированно сортируются по relative POSIX path и содержат path, размер в байтах и SHA-256 digest. Symbolic links отклоняются: инструмент не следует по ним и не нормализует их скрыто.

Seal следует выполнять только после завершения capture и создания всех необходимых derived artifacts. Файл, появившийся после seal, будет отмечен как unsealed; изменение, замена или удаление sealed file приводит к ошибке verification.

## Seal и verify

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

`seal` отказывается перезаписывать существующий integrity contract. `verify` завершается успешно только тогда, когда manifest schema корректна, manifest body digest совпадает, каждый sealed file имеет ожидаемый размер и SHA-256, а после seal не появилось дополнительных regular files.

## Manifest contract

| Поле | Значение |
| --- | --- |
| `schema_version` | Версия integrity schema; в v0.6.5 используется `0.1`. |
| `files` | Детерминированно упорядоченный inventory sealed files. |
| `manifest_body_sha256` | SHA-256 canonical manifest content без самого поля digest. |
| `trust_model` | Явное описание того, что local seal доказывает и чего не доказывает. |

Manifest обязательно содержит `malicious_writer_resistance: false` и `external_trust_anchor: false`. Эти значения являются частью schema contract, а не необязательной оговоркой в документации.

## Trust boundary

Local digest полезен для обнаружения accidental corruption, неполного копирования и post-seal changes относительно момента seal. Однако он не мешает process, способному переписать и run evidence, и `integrity.json`: такой process может пересчитать hashes и создать новый внутренне согласованный manifest.

Для более сильной гарантии скопируйте `manifest_body_sha256` или полный manifest в место вне write boundary observed process либо защитите/подпишите его key, недоступным этому process. Именно это внешнее действие создаёт trust anchor. ExecWeave не утверждает, что manifest в том же directory сам по себе является таким якорем.

## Эксплуатационные правила

Seal следует выполнять только для завершённого run. Перед использованием archived или transferred evidence выполните verify. Любая verification error означает, что directory больше не совпадает точно с sealed inventory; сама по себе она не доказывает злонамеренную активность. Если после seal необходимо создать новые artifacts, сначала создайте их, затем seal новую finalized copy вместо скрытой перезаписи исходного manifest.
