<!-- i18n-nav:start -->
<p align="center">
  <a href="runtime-threat-model.md">English</a> |
  <a href="runtime-threat-model.zh-TW.md">繁體中文</a> |
  <a href="runtime-threat-model.zh-CN.md">简体中文</a> |
  <a href="runtime-threat-model.ja.md">日本語</a> |
  <a href="runtime-threat-model.ko.md">한국어</a> |
  <a href="runtime-threat-model.fr.md">Français</a> |
  <a href="runtime-threat-model.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>
<!-- i18n-nav:end -->

# Модель угроз Runtime и известные границы уклонения

Этот документ определяет ограничения наблюдения, которые ExecWeave v0.6.5 считает частью своего проверяемого контракта. Это **модель угроз наблюдаемости**, а не гарантия sandbox: наблюдаемая команда может быть недоверенной и пытаться скрыть свою активность, при этом предполагается, что ядро ОС и сама установка ExecWeave не скомпрометированы на уровне kernel.

## Portable backend

Portable backend использует psutil snapshots для process/network и watchdog для изменений filesystem.

- **Короткоживущие process:** child, который полностью запускается и завершается между двумя process samples, может быть пропущен. Настроенный poll interval не является гарантированной верхней границей blind window, поскольку scheduler delay может увеличить фактический интервал.
- **Короткоживущие sockets:** соединение, созданное и исчезнувшее между двумя socket observations, может быть пропущено. Ограничения permissions или platform API также могут скрывать socket state.
- **Descendants, живущие дольше root command:** если child всё ещё жив к моменту завершения root observation, ExecWeave не создаёт ложный exit event. Однако portable run не является always-on monitor; дальнейшая активность выжившего или reparented descendant находится за пределами окна наблюдения завершённого run.
- **Filesystem attribution:** изменения watchdog являются session-correlated observations и намеренно имеют `causal=false`. Они не доказывают, что запись выполнил конкретный PID.
- **Negative evidence:** отсутствие portable process/network/filesystem event не доказывает, что соответствующая активность не происходила.

## Linux strace backend

strace backend следует lineage запущенной команды с помощью `strace -ff` и выбранных syscall classes.

- Внутри traced lineage свидетельства clone/fork позволяют сохранить короткоживущие descendants, которые portable polling может пропустить.
- При наличии поддерживаемого syscall evidence filesystem/network events могут быть attributed к traced process.
- Это **не OS-wide visibility**. Активность вне traced lineage, неподдерживаемые или неразобранные syscall patterns, ограничения permission/ptrace и kernel behavior вне выбранных evidence classes не входят в заявляемую область.
- Read/write access mode операции open не доказывает byte-level data flow. ExecWeave не утверждает, что знает фактически прочитанные или записанные позднее байты.

## Specialized hooks и direct API integrations

Claude, Codex, Gemini, Cursor, OpenCode, model-runtime, gateway, proxy и direct-API integrations могут давать более сильную semantic content evidence в явных integration points, но не раскрывают provider-hidden state.

- response-only integration доказывает только response fields, переданные ExecWeave.
- caller-supplied request+response exchange доказывает только предоставленный exchange и не означает transparent wire interception.
- hook coverage ограничена тем, что upstream agent или IDE фактически предоставляет hook.
- full-fidelity storage означает полное сохранение содержимого, доступного в integration point, а не полную видимость model provider или операционной системы.

## Regression contract

`tests/test_threat_model.py` закрепляет следующие границы как deterministic executable tests:

1. portable child, существующий только между двумя process samples;
2. portable socket, существующий только между двумя socket samples;
3. child, остающийся живым при завершении root-process observation, без выдуманного exit event;
4. portable filesystem changes остаются session-correlated и non-causal;
5. соответствующий strace trace case сохраняет `SPAWNED` attribution для короткоживущего child.

Тесты намеренно не используют timing race вида «sleep N мс и надеяться, что CI случайно пропустит событие». blind window моделируется как явное состояние между observations, поэтому контракт воспроизводим на Linux, macOS и Windows.

## Что означает missing event

Missing event означает только отсутствие соответствующей observation в canonical evidence данного run. Это не доказательство того, что событие не происходило, пока будущий backend явно не определит и не докажет полный negative-evidence scope. Finding severity и evidence fidelity остаются независимыми измерениями.
