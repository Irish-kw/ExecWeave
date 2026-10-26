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


## Границы локальной проверки

<!-- ew:trust:local-only -->

Локальные `seal` / `verify` обнаруживают случайные повреждения и изменения без повторного seal. **Процесс, способный изменить запись и `integrity.json`, может пересчитать хеши и повторно seal согласованные данные.** `valid: true` означает только локальную согласованность, но не защищённый от подделки аудит.

<!-- ew:trust:privileged -->

Root, Agent с правами sudo и любой процесс с доступом на запись в выходной каталог может изменить как события, так и manifest. Используйте системные разрешения и изоляцию процессов; смена пути при тех же правах не создаёт изоляцию.

<!-- ew:compat:no-downgrade -->

**Открывать записи v0.8.35+ при помощи reader v0.8.34 не поддерживается.** Старый reader может молча игнорировать `observation_assessment` и искажать полноту наблюдений. Учитывайте только выводы reader v0.8.35 и новее. Откат recorder не означает откат reader.

Выполняйте seal только для завершённых runs и verify перед использованием архива. Ошибка проверки указывает на локальную несогласованность, но сама по себе не доказывает злоумышленную активность. Инструмент не загружает записи или дайджесты и не создаёт отдельную границу привилегий.
