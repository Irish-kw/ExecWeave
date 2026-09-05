# ExecWeave full product audit

Status: BASELINE AUDIT RECORDED. Implementation may address the findings below.
This is not overall acceptance completion: unexecuted provider/OS journeys and
remaining verification gaps are explicitly retained, not converted to PASS.
Started 2026-09-05 on native Windows, Python 3.12.4.

## Baseline and evidence policy

```
START_SHA=a098eeb81f641b6e3fb1d65cc1905f46aa8eae30
ORIGIN_MAIN=a098eeb81f641b6e3fb1d65cc1905f46aa8eae30
LATEST_TAG=v0.8.11
EXECWEAVE_VERSION=0.8.11
AUDIT_BRANCH=audit/full-product-regression
```

Fresh clone, fetch all tags/prune, checkout main, fast-forward-only pull completed.
No AGENTS.md found in repository or workspace root. No reset, merge, tag, release,
provider configuration changes, or preexisting branch deletion performed.
GitHub releases/latest independently confirmed v0.8.11, published 2026-09-05
05:23:20Z, targeting the baseline SHA (non-draft, non-prerelease).

Evidence levels: SOURCE (code inspection), SYNTHETIC (generated fixtures),
NATIVE (actual OS process experiment), BROWSER (real browser execution),
LIVE_PROVIDER (installed authenticated provider). None implies another level.
Unexecuted checks never count as PASS. Adding a matrix does not prove other OS results.

## 1. Architecture reconstructed from code

Entrypoints enumerated from pyproject.toml, not README.
`execweave` enters `execweave.entry:main`; separate provider record/hook CLIs,
model-runtime, OpenAI-compatible, Anthropic, HTTP proxy, inference gateway,
inference identity and LiteLLM callback entrypoints exist.

`entry.main` bootstraps provider configuration before passing live to CLI.
`live_core.run_live` unconditionally chooses `backend="portable"`, even on Linux;
it creates a token-protected loopback HTTP server, sets the run-bound semantic
sidecar environment, runs the collector, validates runtime events, merges sidecar,
builds graph and writes viewer, marks the live state finished, then closes server.
`workflow.record_to_viewer` uses backend auto (strace when available) and produces
OS artifacts. `provider_record.record_provider_to_viewer` adds bootstrap, semantic
merge, and a separate inferred tool/process correlation stream. Thus plain record,
provider-record and live are not interchangeable pipeline paths.

`dashboard_shell.DASHBOARD_HTML` combines live_view with clean/focus/layout/panel
injections. Static viewer uses that shell but replaces polling startup with an
embedded graph/conversation snapshot and FINISHED status. `live.py` patches core
exports and introduces bounded raw-event tails and viewer projection. Sharing the
shell does not establish equal update, content-serving, or finalization behavior.

## 2. Provider support matrix

Reconstructed from hook CLIs, adapters, content/archive modules, provider_record,
auto_specialized and HTTP proxy source. “Available surface” is conditional on the
provider emitting it and the run-bound hook/relay receiving it; it is not a live PASS.

| Provider | Observation source / wiring | Prompt / assistant source | Tools | Identity / correlation | Failure / unsupported boundary |
|---|---|---|---|---|---|
| Codex | hooks -> codex_hook_cli -> summary/metadata/content/archive stages; codex-record additionally enables/imports first-party rollout trace | hook content + validated root/child rollout paths | hook tool payloads, rollout function calls/results | native thread/session, agent path/parent thread, child agent_transcript_path; PID merge, optional inferred provider-record correlation | hook support/build dependent; encrypted text remains opaque; live does not execute codex-record trace enrichment; detached old provider may not inherit sidecar |
| Claude | Claude hooks -> claude_hook_cli, adapter, full fidelity, main/child transcript archive | submitted prompt/Stop content and validated transcript_path/agent_transcript_path | PreToolUse/PostToolUse/failure and archived child transcript tools | session + agent_id for subagents; declared lifecycle topology, run-bound sidecar | disabled hooks, missing transcript, optional content failure; no hook proves unexposed reasoning or arbitrary SDK traffic |
| Antigravity | named hooks under .gemini/config, PostToolUse/PreInvocation/Stop; validated transcript and invocation archives | USER_EXPLICIT/USER_INPUT vs MODEL/PLANNER_RESPONSE transcript records | toolCall args; validated transcript request/result order; child transcript tools | exact conversationId; validated invoke_subagent result/Created At/Role linking; executionNum for execution | transcript ownership is not provider root authority; missing/mutated native wire causes abstention; response after Stop may arrive too late; no invented delivery evidence |
| OpenCode | installed TypeScript plugin -> opencode_hook_cli and provider bus events | chat.message/parts, experimental.text.complete/model-context messages | tool.execute.before/after args/result | sessionID canonical agent, parentSessionID / task linkage; callID | plugin loader/API changes, missing stable IDs, detached process; no arbitrary transcript/TLS capture |
| Cursor | hook contract -> cursor_hook_cli / full fidelity / delegation | beforeSubmitPrompt candidate, exposed assistant response hooks | pre/post/failure tool input/output; shell/read-file/edit hooks | conversation/session/generation IDs and explicit subagent hooks; inferred tool/process correlation only when requested | prompt can be blocked; does not read transcript_path; desktop existing-instance handoff may defeat launch environment |
| Ollama | recognized ollama run changes client OLLAMA_HOST to relay; serve binds public relay and moves real server to internal port; model /api/ps probe | native /api/chat or /api/generate request and response; stream assembler | model-exposed calls only, not executed tools by ordinary ollama run | runtime endpoint/request occurrence; unique Ollama owner alias for viewer; independent clients observed via same relay | preexisting server left unclaimed; nonloopback/IPv6 server relay not rewritten; Python SDK not automatically redirected; streaming delayed and capture after full response |
| OpenRouter | inference-gateway event/exchange imports | response-only event cannot prove prompt; exchange supplies both | response/exchange-exposed calls | gateway + sanitized endpoint + request/deployment/model identities | not transparent CLI interception; caller must supply evidence; no agent tree from request alone |
| LiteLLM | gateway import or explicit LiteLLM callback | callback/exchange request/response fields | exposed response tool calls | gateway/endpoint scope and request ID | callback installation required; synthetic provider contract is not actual callback invocation |
| OpenAI-compatible | explicit event/exchange import or local HTTP relay configured as SDK base URL | event response only; exchange request+response; stream reassembly | exposed function/tool-call payloads, no proof of execution | endpoint-scoped request/model, explicit identity links where provided | relay accepts explicit HTTP upstream, rejects HTTPS and CONNECT; cannot silently proxy public HTTPS APIs; no automatic SDK monkeypatch |
| Anthropic API | explicit anthropic event/exchange importer | response-only vs request+response import | exposed content tool_use/tool_result | provider-qualified model and observation/native request IDs | not equivalent to Claude Code hook integration; no automatic Python SDK interception |
| model-runtime | event/exchange/probe CLIs for Ollama, llama.cpp, vLLM, LM Studio; select recognized process probes | exchange payload only; loaded-model probe has no prompt | exposed request/response tools only | runtime/endpoint/native-or-observation identity | a loaded model event proves neither inference nor conversation; server command recognition varies |
| inference gateway | gateway CLI + identity linking + optional callback | supplied gateway payloads | supplied payloads | conservative explicit transport/semantic linking | no universal process -> logical-agent causality; upstream routing identity cannot be inferred from a label |
| Generic Python | portable/strace OS collector; optional explicit semantic API/import/relay integration | none from plain wrapping | OS child commands are not semantic tool calls | process PID/create time; caller must provide logical agent/session metadata | no transparent semantic support for arbitrary framework or TLS SDK |

Initial PATH discovery finds `agy.exe` and
`cursor.cmd`; codex, claude, opencode and ollama are not on this shell's PATH.
Additional read-only installation discovery found Codex npm shim, Claude
`~/.local/bin/claude.exe` (2.1.260), and Ollama in Local Programs. AGY is 1.1.26,
Cursor 3.19.7. Authentication has not been inspected or changed. OpenCode not found.

## 3. OS support matrix

Native environment: Windows exercised. WSL Ubuntu is installed but not yet tested;
no macOS machine has been established. WSL is not a substitute for macOS results.
Existing CI selects all three OS for src/tests/scripts/workflow changes and release
tags, but normal pytest does not install the optional Playwright extra. Dedicated
Browser workflow runs **Ubuntu only**, selecting `-m viewer_e2e`.

| Path | Windows | macOS | Linux |
|---|---|---|---|
| live | portable psutil + watchdog | portable psutil + watchdog | also portable, hardcoded |
| record/run auto | portable | portable | strace if available, otherwise portable |
| process | polling, short processes can be missed | same | syscall-derived only with strace |
| filesystem portable | native watchdog change notifications; session-level, not causal reads/writes | same contract | inotify or polling fallback, same session contract |
| network portable | sampled process connections | permission-dependent sampling, errors suppressed | sampling in live; strace path differs |

There is no distinct ETW Windows or syscall-level macOS backend in backends.py.

## 4. Semantic evidence boundaries

OS telemetry must not be presented as framework-independent semantics.
Generic Python command has no lifecycle integration in agent_bootstrap; automatic
relay is selected only for recognized Ollama run/serve commands. Python SDKs and
frameworks do not become semantically visible merely by wrapping python.
OpenAI/Anthropic-compatible SDK traffic requires explicit observation/relay wiring;
HTTPS packet observation does not expose prompts. Framework agent identity needs
provider metadata or explicit instrumentation; an HTTP request alone proves neither
LangGraph node identity nor CrewAI/AutoGen agent ownership.

Semantic process references are resolved by PID/create time in semantic.py;
provider_record correlation is separately inferred and non-causal. Live does not
call the provider-record postprocessing correlation path.

## 5. Historical PR/regression map

See pr_regression_map.md and the preserved 50-PR inventory. Merged first-parent
changes and regression chains were reviewed separately from PR descriptions.
Closed/unmerged #26 and #40 are not treated as shipped changes. Current native
and browser results supersede historical assertions of success.

## 6. Existing test coverage map

CI source inspected: provider smokes invoke `scripts/emit_*` Python fixtures,
not the provider clients. Most disable both file and network collection.
Live smoke runs Python sleeping 0.2 seconds, validates JSONL and graph summary;
it does not launch a browser or assert semantic conversation presence.
Confirmed native baseline: **981 passed, 1 failed, 29 skipped**, excluding 27
marked browser tests. Failure is tests/test_command.py Cursor shim resolution in
the presence of a real local Cursor installation.

Marked browser baseline: **27 passed** on Windows. Explicitly running five
unmarked geometry/focus/tool modules adds **27 tests: 19 passed, 8 failed**.
These five modules are excluded by the dedicated Browser CI marker selection;
the ordinary CI environment lacks Playwright so they skip. This is a verified
test-discovery gap, not an inference from filenames.

## 7. Missing real-user-journey tests

The above CI smokes cannot independently establish real provider authentication,
native hooks, TUI input, or live/finished UI parity. Missing release-journey gates:

| Journey | Current evidence | Required acceptance extension |
|---|---|---|
| Codex/Claude native CLI + hooks | parser/archive fixtures and browser contracts | actual short file action, native sidecar and root final in both viewers |
| Antigravity two rounds, 5+3 children | provider-shaped preconstructed graph/entries | raw native wire/archive replay through ingestion; optional controlled live scenario |
| OpenCode plugin | synthetic plugin/bus contracts | installed plugin + actual client with session ownership |
| Cursor Windows launcher | native discovery, shim regression failure | safe desktop/CLI automation, no preexisting-window takeover |
| Ollama separate client/server | actual Windows ConPTY + headed live/final | standard-port/preexisting-server boundaries, controlled --open and repeatable harness |
| Python OS-only | actual file/network/live growth + finished inspectors | three native OS results and explicit negative semantic assertions |
| Generic SDK/framework semantics | source observation boundary only | explicit local relay/instrumented fixture, never a fake framework-support PASS |
| Crash/interrupt cleanup | real Ollama Ctrl+C, child lifetime reproduction | harness interruption and descendants-after-root on each OS |
| Browser discovery | marked and previously excluded suites executed | discover all E2E modules, repair stale assertions without weakening layout gates |

## 8. Browser/visual findings

Installed Playwright 1.62.0 and dedicated Chromium under .execweave-acceptance.
Browser skill runtime returned no browsers after documented discovery; independent
repo Playwright execution used for native Chromium testing.
Headed audit at 1440x1000, 1920x1080, 1366x768, 1280x720 produced eight screenshots
for two-round conversation and dense (35 added processes, 10 added agents) cases.
All eight had no measured box overlap, label overflow, page overflow, or JS errors;
real first-node hit-target clicks succeeded. Dense graph renders only 37 nodes due
to folding, and initial Fit shrinks labels to unreadable size (visually confirmed at
1280x720). This is why passing simple geometry assertions does not prove usability.
More interaction, long prompt, live growth and per-provider evidence remain pending.

Unmarked routing test measures **89 crossings vs baseline 73**. Other failures
include stale lane-coordinate assumptions and external endpoint cluster IDs;
do not classify all eight assertions as eight product defects. Independent actual
2D geometry is necessary to separate obsolete layout policy from real overlap.

## 9. Conversation correctness findings

Existing Antigravity two-round/eight-child fixture was independently exercised
with real pointer hit-target clicks in headed Chromium at all four requested
viewports. One root retained two rounds; all eight children exposed only their
own task/thinking/response markers; child finals did not overwrite root. Open
history survived updated entries, explicit collapse, agent switches and reload
retained the correct root content. Source entries/graph are synthesized directly:
this proves UI ownership behavior, NOT real Antigravity hook/archive ingestion.
Evidence: `diagnostics/audit_eight_children.py`, local run `6034e2dd`.

Additional 1000-line Unicode root prompt run `35b3ea12` passed all four viewports
and all eight child selections. Root detail content extends below the viewport
inside its scroll container; final response was scrolled into view and verified
on screen, so tall content alone is not reported as clipping. No JS errors.

The existing Codex round-state contract was rerun with actual locator.click()
instead of synthetic dispatchEvent and headed Chromium. Static and live paths
passed six root/child hit-target clicks, polling, changed payload, persistent
expand/collapse and selection switches. Evidence: `diagnostics/audit_real_clicks.py`,
run `c133d077`. The live server still projects a fixture: not a provider test.

## 10. Provider-specific findings

Provider configuration/authentication was not modified. Read-only preflight of
the installed hook files found existing ExecWeave wiring and predicted no bootstrap
changes for Codex, Claude, Antigravity and Cursor. Authentication usability is not
inferred from files or command availability. No cloud live run has yet been accepted.

| Provider | Native command discovery | Live audit evidence / boundary |
|---|---|---|
| Codex | npm shim, 0.153.4 | hooks/archive source audited; actual authenticated journey deferred to harness |
| Claude | local bin, 2.1.260 | same; do not disable hooks with bare mode |
| Antigravity | agy.exe, 1.1.26 | two-round/eight-child UI-only probe passed; native root authority remains critical |
| OpenCode | not found | unavailable locally, must SKIP_UNAVAILABLE unless --require makes overall failure |
| Ollama | Local Programs, 0.33.3; installed 1.5b and 7b models | actual 1.5b serve/client + Ctrl+C journey described below; streaming latency defect remains |
| Cursor | cmd shim 3.19.7, multiple desktop install locations | installation-dependent old test failure; desktop detached launch is not proof of inherited hooks |
| Python | dedicated venv, 3.12.4 | native OS-only action chain; semantic content correctly absent |

Ollama discovery can auto-start its desktop/server process. Only identified processes
started by the audit were stopped; user servers/models were not deleted. Future
harness must disable history/pruning via child environment and avoid claiming an
existing server. Never copy credentials into report artifacts.

## 11. Generic Python/framework findings

No framework integration/SDK monkeypatch/sitecustomize or OPENAI_BASE_URL/
ANTHROPIC_BASE_URL injection found in src. Every row below inherits the OS bounds
in section 3, regardless of whether the code calls itself an agent.

| Wrapped program | Process/child | File | Network | Prompt/assistant/tool-result/agent/conversation |
|---|---|---|---|---|
| plain Python | sampled in live; descendants/fast children incomplete | session changes, no transparent Windows/macOS reads | sampled connections | absent without explicit semantic emission |
| LangChain | same | same | same | only explicitly observed model exchange; chains/tools/agents not transparent |
| LangGraph | same | same | same | graph nodes/state are not inferred from OS events |
| CrewAI | same | same | same | crew/role/subagent identity not inferred |
| AutoGen | same | same | same | conversational agents/messages require explicit evidence |
| custom framework | same | same | same | explicit sidecar schema/instrumentation required |
| OpenAI SDK | same | same | HTTPS connection metadata | base URL/explicit exchange integration required; public HTTPS cannot use this HTTP-only relay as upstream |
| Anthropic SDK | same | same | HTTPS connection metadata | explicit Anthropic exchange import, not Claude hooks |
| Ollama SDK | same | same | sampled local socket | point SDK at an owned managed serve relay; wrapping python alone does not install relay |
| OpenAI-compatible SDK | same | same | same | local HTTP endpoint relay or explicit import; agent/tool execution remains outside model-call scope |

Real native Python child-lifetime experiment used a Unicode/space workspace and
confirmed late file exists but no corresponding file-target event or child-exit event.
Native full Python file/write/read and held loopback socket action chain completed
under real ExecWeave live in Unicode/space workspace. Browser nodes grew from 2
to 6 without reload. events.jsonl contains process started/exited, file created/
modified, network.connection and session completion. Finished file/process/network
nodes were physically clicked and displayed their corresponding inspectors.
No semantic sidecar content was emitted, as expected for uninstrumented Python;
an argv marker inside process details is explicitly NOT counted as prompt capture.
Evidence: `diagnostics/audit_python_journey.py`, run `05dc0878`, no owned processes
remaining and no page errors. The first probe skipped clustered raw process IDs
and incorrectly escaped Unicode IDs for CSS; real rendered-node traversal then
verified both file and process clicks. These were audit-probe defects, not product
defects. This remains an OS-only journey, not a semantic acceptance PASS.

## 12. Cross-platform risks

Windows evidence is native, not os.name mocking. macOS and Linux results remain
unexecuted. Native watchdog notifications are not syscall file-read evidence;
psutil connection permissions and timing differ across OS. Linux live hardcodes
portable even when strace exists, whereas record auto selects strace. Windows
cmd shims/desktop handoff and ConPTY are separate contracts from POSIX PTYs.

Three-OS CI must install browser dependencies and execute offline fixtures, browser
E2E, wrapper parsing, timeout/interrupt and owned-child cleanup checks. A configured
matrix is not a PASS result. CI must never automatically spend cloud provider tokens
or modify provider homes. Headed Linux requires a display (e.g. Xvfb); Windows/macOS
must actually launch their native browser/PTY implementations.

## 13. Unknown/new defects

### NEW-001 — Browser gate silently excludes geometry/tool modules (P1)

- Reproduction: run `pytest -m viewer_e2e --collect-only`, compare with explicit
  test_graph_edge_routing_e2e, test_graph_node_sizing_e2e, test_graph_lane_separation_e2e,
  test_graph_clear_focus_e2e and test_tool_traffic_e2e selection.
- Expected: Browser CI executes all intended browser regressions.
- Actual: dedicated gate 27/27 PASS; excluded modules 8 FAIL / 19 PASS.
- Root cause: missing module markers plus optional Playwright absent in main CI.
- Scope: baseline v0.8.11, workflow applies across platforms; native Windows verified.
- Minimal proposal: mark all browser modules, require browser dependencies in
  three-OS browser matrix, review obsolete assertions independently.
- Evidence: .execweave-acceptance/browser-baseline.xml and unmarked-browser.xml.

### NEW-002 — Installed Cursor makes synthetic shim test fail (P2)

- Reproduction: baseline full non-browser suite on this Windows machine.
- Expected: isolated shim regression should not depend on a user's desktop install.
- Actual: resolves real Local Programs Cursor.exe, expected temporary cursor.cmd.
- Root cause: command resolver intentionally checks desktop installation fallback;
  test does not isolate that lookup. Distinguish intended resolver policy from test defect.
- Scope: Windows with installed Cursor, v0.8.11 confirmed; #47 changed this path.
- Minimal proposal: isolate desktop candidates in this old shim-only test and keep
  separate native/custom-install assertions. Product resolution policy review pending.
- Evidence: .execweave-acceptance/baseline.xml, tests/test_command.py:57.

### NEW-003 — Child survives collector completion (P1)

- Reproduction: native Python parent starts child; parent sleeps 0.4s then exits;
  child writes a file at 2s and exits at 3s. Dedicated Unicode/space workspace.
- Expected: lifetime boundary accurately describes ongoing descendants; harness
  must own and clean all spawned processes, including those outliving root.
- Actual: collector returns 0 in ~0.59s while child lives; no child-exit event.
- Root cause: run loop is `while process.poll() is None`; normal return does not
  wait/track/clean descendants. Interrupt cleanup enumerates only current descendants.
- Scope: portable all OS by source, native Windows demonstrated on v0.8.11.
- Minimal proposal: explicit owned-descendant lifecycle/cleanup strategy; avoid
  terminating unrelated provider servers. Product behavior decision remains pending.
- Evidence: .execweave-acceptance/native-audit/*/result.json. File-observation
  assertion in first experiment needs narrowing to event target (command contains filename).

### NEW-004 — Dense Fit view is legible only after manual zoom (P2)

- Reproduction: headed audit dense fixture, 1280x720 initial viewer.
- Expected: readable initial actionable graph or a clear usable navigation affordance.
- Actual: graph occupies narrow left strip with text only a few pixels high despite
  large blank canvas; geometry gates are green.
- Root cause: whole-graph Fit on tall fanout with long process labels.
- Scope: shared renderer v0.8.11; four Windows Chromium viewports reproduced.
- Proposal: acceptance measures minimum rendered text/hit-target size and tests
  zoom/focus reachability; layout design change deferred pending evidence review.
- Evidence: .execweave-acceptance/independent-visual/dense-1280x720.png.

Additional source leads, not confirmed native defects: portable seen-process cache
keys only PID; live exceptions skip graph/viewer materialization; repeated bootstrap
config merge has a check-then-replace concurrency window. Streaming and explicit
process identity failures were separately confirmed below.

### NEW-005 — HTTP relay delays streaming to completion (P1, confirmed)

- Reproduction: native loopback HTTP upstream flushes first NDJSON record immediately,
  waits 1.2s, then flushes final record; compare one-byte client reads direct/relay.
- Expected: first record delivered promptly while inference is still running.
- Actual: direct first byte 0.015s, relay first byte 1.218s. Semantic recorder runs
  only after full response; prompt cannot appear while short response is streaming.
- Root cause: http_proxy.py `_relay` uses `response.read(65536)` rather than a
  read-available primitive, and records only after the stream completes. Entire
  response is retained in a bytearray, creating unbounded response memory growth.
- Scope: HTTP relay on all OS by code; native Windows timing confirmed at v0.8.11.
- Test gap: existing stream fixture writes all chunks together; content equality
  after completion does not test streaming latency or intermediate prompt visibility.
- Minimal proposal: use read1 for transport, add a slow flushed upstream timing test;
  request/partial-response semantic publication and bounded capture need explicit design.
- Evidence: .execweave-acceptance/stream-audit/result.json and audit_stream.py.

Implementation status NEW-005 transport: changed HTTPResponse.read to read1.
Two socket-ordering regressions fail before the fix and pass afterwards, covering
content-length and chunked streams; HTTP/Ollama lifecycle selection 15 passed and
Ruff passed. Native delayed upstream first-byte repeat measured 0.032s (baseline
1.218s). Prompt-before-completion semantic emission and response memory bounds
remain OPEN; this small transport fix does not implement those distinct behaviors.

Post-fix real Ollama run `96e56662` preserved matching live/finished prompt and
actual assistant output, full artifacts and cleanup, but the model replied with
unrelated email prose instead of the requested DONE marker. Exact-answer gate FAIL,
not a capture mismatch: provider.log contains the same prose. Scratch audit checked
DONE across the whole inspector and falsely matched the prompt; corrected to the
final-response section. Formal harness must include a negative regression where
prompt contains DONE but assistant does not. Earlier `4007a5f5` actual final text
did contain the correct marker and remains valid limited baseline evidence.

### NEW-006 — Explicit process identity conflict is ignored (P1, confirmed)

- Reproduction: semantic process_reference pid=42/create_time=100, sole runtime
  candidate pid=42/create_time=200, semantic event timestamp=150.
- Expected: unresolved; positive contradictory create time must forbid a match.
- Actual: resolver returns matched=True and the process which did not yet exist.
- Root cause: failed exact create-time match falls through to unconditional single
  candidate resolution; single-candidate path also ignores event-before-start time.
- Scope: semantic.py, all platforms, baseline v0.8.11; synthetic identity reproduction.
- Test gap: PID reuse tests need contradictory explicit identity, not just multiple
  candidates with a convenient timestamp ordering.
- Minimal proposal: abstain immediately on explicit mismatch and require temporal
  consistency for otherwise unambiguous candidates; keep unresolved evidence.
- Evidence: .execweave-acceptance/stream-audit/result.json.

Implementation status NEW-006: minimal resolver fix prevents explicit mismatch
fallback and future-process matches. Added public sidecar merge -> validation ->
graph regression, including a valid past identity control. Red 3 failed/1 passed;
green semantic 8 passed and correlation 13 passed; Ruff passed. Full suite and
browser/provider gates still pending; this does not simulate native PID reuse.

NEW-003 historical qualification: #26 already identified descendants outliving root
as a limitation. It is newly reproduced here and a P1 acceptance-cleanup risk,
not claimed as an unknown historical discovery.

Ollama first native run confirmed actual model response, request/response content,
and graph/viewer materialization on real ConPTY Ctrl+C during cleanup, with zero
remaining owned processes. Audit script initially looked for plaintext in sidecar
instead of content references and timed out; that audit defect is corrected and
Browser live/finished verification was rerun successfully in run `4007a5f5`.
The actual deepseek-r1:1.5b client received a prompt through ConPTY input; headed
Chromium root details contained the exact prompt and final marker both live and
in the finished viewer. Real ConPTY Ctrl+C finalized events.jsonl, semantic.jsonl,
events.semantic.jsonl, graph.json and viewer.html. Console errors and remaining
owned-process lists were empty. Evidence: `.execweave-acceptance/ollama-audit/4007a5f5/result.json`
and four screenshots beside it. This audit uses a dedicated public Ollama endpoint
and owns Chromium directly; it does not yet test CLI `--open` or prove all Ollama
environments work. Do not label the initial timed-out run PASS or the full gate complete.
Each finding will include reproduction, expected/actual, root cause, version/platform
scope, test gap, and proposed minimal correction.

## 14. Priority ranking

P0 release blocker; P1 major correctness; P2 product quality; P3 cleanup.
Confirmed audit findings: P0=0 observed, P1=4, P2=2, P3=0. Zero observed P0 is
not evidence of release readiness. NEW-003 is a known lifecycle boundary independently
reproduced, and NEW-002 is a test-isolation defect, not a confirmed launcher failure.

1. NEW-005: fix transport streaming latency first; separately retain partial semantic
   publication and unbounded response memory as open design/coverage work.
2. NEW-006: refuse contradictory process identities; regression tests must include
   explicit mismatch and event-before-process-start, without fabricated causality.
3. NEW-001: restore discovery of real browser regressions and review all eight failures.
4. NEW-003: build native run-owned cleanup in the harness; do not silently redefine
   product child-lifetime semantics or kill shared provider servers.
5. NEW-002: isolate installation-dependent test setup, preserving real Cursor policy.
6. NEW-004: add readability/navigation gates; avoid wholesale layout replacement.

Unknown-defect scan ledger (source inspection is not a stress-test PASS):

| Area | Evidence and disposition |
|---|---|
| Streaming / long output / memory | delayed first byte reproduced; full-response bytearray unbounded by source; no long-duration RSS bound proven |
| PID reuse / detached children | conflicting identity reproduced synthetically; native child outlives collector; actual OS PID reuse not forced |
| Polling race / stale state | sequence/base-sequence resync and serialized timeout polling inspected; actual fold polling passed; no prolonged reconnect/soak proof |
| Lost/duplicate semantics | archive/history regression suites pass; bounded raw live tails are not equivalent to event deletion; real per-provider replay still required |
| Unicode / spaces | native Python filesystem/socket journey and 1000-line Unicode UI prompt passed; CSS locator escaping corrected in audit probe |
| Crash / Ctrl+C | actual Ollama Ctrl+C materialized files; nonexistent executable raises before materialization; arbitrary mid-write crash recovery not accepted |
| File / network loss | native late child file loss reproduced; portable reads/short sockets remain architectural limits, not promised transparent semantics |
| Attribution / provider isolation | explicit PID conflict found; UI children isolate on constructed fixture; producer-level identity still needs real capture |
| Large graph / clipping | four-viewport dense graph measured, initial Fit readability defect; long-prompt final scroll reachable; no maximum graph performance budget proven |
| Bootstrap / concurrent runs | global semantic env and optimistic check/replace inspected; concurrency race remains hypothesis, no unsafe config experiment performed |

## 15. Acceptance harness design

Baseline report and historical map are now recorded before implementation. Open
verification items above become explicit acceptance requirements, not retrospective
claims of successful audit experiments. Overall completion remains gated by results.

Core `scripts/dashboard_acceptance.py`; thin ps1/sh wrappers only. Separate provider
adapters, native process ownership/PTY transport, browser assertions and reporting.
Run directories use unique OS/provider/scenario IDs under dedicated workspaces;
never reuse a prior marker or treat argv text as a semantic prompt.

Offline mode must drive semantic parsing/graph materialization plus real live and
finished renderer checks. Ready-made UI fixtures remain a separately labeled layer.
Real Python uses negative semantic assertions; instrumented Python, if added, is a
different scenario. Ollama uses owned serve relay and an independent real model
client, actual input and Ctrl+C, then checks all required artifacts and final UI.

Visible mode prints command, exact short prompt, provider output, collector status
and each assertion while headed Chromium is open. Interactive mode adds native
PTY/ConPTY input/readiness with deadlines; unsupported safe GUI automation must
skip honestly. Provider configuration preflight must refuse changes outside isolated
workspace. Avoid shared-server takeover and user browser cleanup.

Gate on exact owned prompt/final/tool evidence, live node growth without reload,
actual hit-target inspector clicks, fold/selection persistence and same-run final
snapshot parity. Use negative cross-provider/child markers. Geometry checks distinguish
intentional scroll containers/clusters from clipping, and measure readability as
well as non-overlap. Screenshots are evidence, not whole-image pixel gates.

Reports contain per-feature PASS/FAIL/SKIP_UNAVAILABLE, explanation/evidence paths,
runtime/request observations and no invented token counts. --require missing provider
fails overall. Browser console/promise errors and leftover owned identities fail.
Track PID + creation time before root exit; graceful provider exit and collector
finalization precede bounded terminate/kill of only owned descendants. Ctrl+C must
save partial report and cleanup. Report/harness commits remain separate from fixes.

## Execution journal

- Baseline synchronized and audit branch created. Product source unchanged.
- Read CI job definitions and enumerated source/test modules.
- Base tools: git, Python, pytest, ruff available; gh/rg/Playwright absent on PATH/base Python.
