# ExecWeave v0.8.3 Audit Coverage Gaps

Baseline: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`.

This document lists what the audit has **not** proved. A coverage gap is not a bug unless a separate finding in `bug-inventory.*` establishes one.

## 1. Real provider executions are not uniformly reproducible in this audit environment

The GitHub connector gives repository read/write access, but this audit session does not have authenticated local installations/accounts for every provider CLI and cannot independently launch all provider runtimes. As a result, provider paths were traced from current code, repository fixtures/tests and current official documentation where available, but the following still require real/sanitized captures before the v0.8.3 release candidate can be called fully audited:

- Google Antigravity: 1 / 2 / 5 / 10 agents, parallel and sequential children, repeated `Stop`, incomplete/torn transcript, schema mismatch.
- Claude Code: 1 / 2 / 5 / 10 agents, parallel children, nested child if currently supported, independent sessions in one ExecWeave run.
- OpenAI Codex: the repository has strong real multi-agent fixtures, but the release candidate still needs a fresh current-provider run after all v0.8.3 fixes are assembled.
- Cursor Agent: `subagentStart` / `subagentStop`, failed child, identical-role siblings and nested delegation where the current provider exposes it.
- OpenCode: two independent root sessions, parent/child sessions and simultaneous tool calls through the current plugin wire.
- Gemini CLI: current hook payload verification against an installed current CLI.

## 2. Antigravity historical-turn loss remains unresolved

The user supplied a real observation in which earlier Antigravity turns disappeared instead of remaining as folded historical rounds. The repository does not yet contain a sanitized three-turn Antigravity fixture that reproduces this end to end.

Required closure:

1. sanitize a real three-turn Antigravity transcript/hook sequence;
2. archive it into the run-local content store;
3. project raw evidence -> graph -> conversation records -> dashboard;
4. exercise repeated Stop/poll updates;
5. verify in Chromium that rounds 1 and 2 remain present/folded and round 3 remains current/open;
6. repeat with one child conversation and one parent conversation to prove isolation.

Until this is reproduced or explicitly dismissed, `SUS-001` remains a release blocker.

## 3. PR #25 is a moving implementation line, not the audit baseline

PR #26 intentionally audits from `main` and does not modify or rebase onto PR #25. PR #25 is the v0.8.3 graph ergonomics/routing implementation line and reached ready-for-review state during this audit.

Its own report states that it added real Chromium coverage for adaptive sizing, reversible focus, placement and routing, with a recorded crossing regression floor. That is useful evidence, but PR #26 must not silently treat a separate branch as the final release candidate.

Required closure after the eventual v0.8.3 candidate is assembled:

- rerun PR #25's Chromium tests on the candidate SHA;
- rerun conversation-fold Chromium tests on that same SHA;
- rerun provider/identity regressions after P0/P1 fixes;
- verify Live, Finished and static `viewer.html` together, rather than accepting independent branch results.

## 4. Browser combination coverage is incomplete

Existing Chromium tests are strong in specific areas, especially historical-round folding, and PR #25 adds focus/layout/routing tests. The following state combinations still need an explicit release-candidate matrix:

- focused node + 800 ms live poll;
- focused node disappears in new payload;
- focused node becomes folded;
- manual zoom + live poll;
- Fit graph + live poll;
- Follow latest + live poll;
- manually opened historical round + live poll + agent switch + return;
- inspector open while selected node is updated;
- Unicode search + type filter;
- relation search/filter + focus + clear focus;
- search clear while follow-latest is active;
- replay while focused;
- export after transition to FINISHED.

## 5. Large graph measurements are not yet recorded on the final candidate

The audit requirement asks for small (~10), medium (~50) and large (100–300+) graphs with different evidence mixes. PR #25 reports a crossing baseline on its dense fixture, but the system-wide release candidate still needs comparable measurements across:

- agent-heavy;
- process-heavy;
- file-heavy;
- network-heavy;
- tool-heavy;
- mixed graphs.

Record at minimum:

- edge crossings;
- node overlaps;
- edge/node intersections;
- graph bounding box;
- unchanged-node displacement between polls;
- deterministic positions/path data for identical payloads.

## 6. Cross-platform native evidence requires real OS runs

Source inspection covers the portable collector and platform-specific modules, but this audit did not execute a full native matrix on Linux, macOS and Windows.

Still required:

- Windows path case/slash/drive-letter identity;
- long Windows paths in graph/search/inspector;
- macOS filesystem watcher behavior and its lack of PID attribution where applicable;
- Linux native collector vs portable fallback attribution;
- symlink/realpath handling;
- IPv6 endpoint formatting and deduplication;
- watcher-limit exhaustion behavior;
- short-lived process/socket stress.

Architectural limitations that cannot be eliminated by testing are listed separately as `KNOWN LIMITATION` rather than left ambiguous here.

## 7. Processes that outlive the launched root need explicit product semantics

The portable collector stops active sampling after the launched root exits. A child that survives the root can therefore remain alive after the run loop ends. This is currently classified as a known limitation, not a confirmed correctness defect.

The product still needs a documented decision for v0.8.3+:

- whether ExecWeave intends to follow descendants after root exit;
- how long it would follow them;
- how run completion should be represented while descendants remain alive.

## 8. Short-lived sockets remain a polling blind spot

Portable network evidence is sampled through process connection polling. Connections that open and close between samples can be missed. A real stress fixture should quantify the miss rate, but no test can turn polling into complete event capture.

Any dashboard or documentation claim must therefore avoid implying complete network provenance on the portable backend.

## 9. Tool-call attribution coverage is uneven across providers

The repository contains good provider-specific tool adapters, but a uniform behavioral matrix has not been run for every provider with:

- one call;
- repeated same tool;
- parallel calls;
- same tool from several agents;
- failed call;
- missing call identity;
- short-lived call;
- tool arguments/results;
- model attribution.

This matters most where one evidence path uses a provider hook and another parses transcript/content because dual paths can create duplicate identities.

## 10. Model switching and cross-provider model-name collisions need release-candidate regression coverage

`AUD-008` confirms that several API/gateway paths use global `model:catalog:<name>` IDs. Beyond fixing that issue, the release candidate should test:

- model switching within one run;
- same model label across two unrelated providers;
- aliases changing during a run;
- missing model name;
- one model shared by several agents without losing agent -> model attribution.

## 11. Replay/export parity needs stronger behavioral coverage

The controls exist in the shared dashboard, but the audit has not independently exercised every replay/export path after a run finishes. The release candidate should prove that replay/export uses the same archived run evidence and does not depend on an external provider transcript directory that was claimed to have been copied into the run.

## 12. Test-quality gaps remain even with a green suite

The repository contains several high-quality behavioral tests, including Chromium tests and real multi-agent fixtures. It also contains tests that deliberately preserve known limitations, such as the current cross-session root-conversation merge.

A green suite therefore cannot by itself mean release correctness. For v0.8.3, audit closure requires reviewing whether every P0/P1 regression tests the desired fixed behavior rather than merely documenting current behavior.
