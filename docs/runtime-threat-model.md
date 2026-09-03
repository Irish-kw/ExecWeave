<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="runtime-threat-model.zh-TW.md">繁體中文</a> |
  <a href="runtime-threat-model.zh-CN.md">简体中文</a> |
  <a href="runtime-threat-model.ja.md">日本語</a> |
  <a href="runtime-threat-model.ko.md">한국어</a> |
  <a href="runtime-threat-model.fr.md">Français</a> |
  <a href="runtime-threat-model.de.md">Deutsch</a> |
  <a href="runtime-threat-model.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Runtime Threat Model and Known Evasion Boundaries

This document defines the observation limits that ExecWeave v0.6.5 treats as part of its testable contract. It is an observability threat model, not a sandbox guarantee: the observed command may be untrusted and may try to make activity difficult to observe, while the operating system and ExecWeave installation are assumed not to be kernel-compromised.

## Portable backend

The portable backend uses psutil snapshots for process/network activity and watchdog for filesystem changes.

- **Short-lived processes:** a descendant that starts and exits entirely between two process samples can be missed. The configured poll interval is not a guaranteed maximum blind window because scheduler delay can make the real gap longer.
- **Short-lived sockets:** a connection that is created and disappears between socket observations can be missed. Permission or platform API restrictions can also hide socket state.
- **Descendants that outlive the root command:** ExecWeave does not fabricate an exit for a child that is still alive when the root observation ends, but the portable run is not an always-on monitor. Activity performed later by a surviving/reparented descendant is outside that completed run's observation window.
- **Filesystem attribution:** watchdog changes are session-correlated observations. They are deliberately `causal=false` and are not proof that a particular PID performed the write.
- **Negative evidence:** absence of a portable process, network, or filesystem event must not be interpreted as proof that the activity did not occur.

## Linux strace backend

The strace backend follows the traced command lineage with `strace -ff` and selected syscall classes.

- Within that traced lineage, clone/fork evidence can preserve short-lived descendants that portable polling could miss.
- File and network events can be attributed to the traced process when supported syscall evidence exists.
- This is **not OS-wide visibility**. Activity outside the traced lineage, unsupported/unparsed syscall patterns, permission/ptrace restrictions, and kernel behavior outside the selected evidence classes remain outside the claim.
- Open/read-write access modes do not establish byte-level data flow. ExecWeave does not claim the contents later read or written by the process.

## Specialized hooks and direct API integrations

Claude, Codex, Antigravity, Cursor, OpenCode, model-runtime, gateway, proxy, and direct-API integrations can provide stronger semantic content evidence at their explicit integration points, but they do not reveal provider-hidden state.

- A response-only integration proves only the response fields supplied to ExecWeave.
- A caller-supplied request+response exchange proves only that supplied exchange; it does not assert transparent wire interception.
- Hook coverage is bounded by what the upstream agent or IDE exposes to that hook.
- Full-fidelity storage means complete preservation of the content exposed at the integration point, not complete visibility into the model provider or operating system.

## Regression contract

`tests/test_threat_model.py` keeps these boundaries executable and deterministic. It covers:

1. a portable child that exists only between process samples;
2. a portable socket that exists only between socket samples;
3. a child that remains alive when root-process observation ends, without inventing an exit event;
4. portable filesystem changes remaining session-correlated and non-causal;
5. the corresponding strace trace case preserving `SPAWNED` attribution for a short-lived child.

The tests intentionally avoid timing races such as "sleep for N milliseconds and hope CI misses it." The blind windows are modeled as explicit states between observations so the contract is reproducible on Linux, macOS, and Windows.

## What a missing event means

A missing event means only that ExecWeave has no canonical observation for that event in the run. It is not evidence of non-occurrence unless a future backend explicitly defines and proves a complete negative-evidence scope. Finding severity and evidence fidelity remain separate dimensions.
