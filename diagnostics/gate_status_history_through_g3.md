# Acceptance gate ledger

Baseline: a098eeb81f641b6e3fb1d65cc1905f46aa8eae30 (v0.8.11).
Only completed checks are PASS. A checkpoint commit does not close a gate.

| Gate | State | Evidence / remaining work |
|---|---|---|
| G0 baseline and evidence checkpoint | PASS | Native Windows baseline, public PR inventory, audit findings saved; no implementation changes |
| G1 baseline audit report | PASS | Architecture/history, native/browser findings, priorities and design recorded; unexecuted release journeys explicitly remain open |
| G2 minimal defect fixes | PASS | NEW-001/002/003/004/005/006 are verified; the final large-response memory gate is green on Ubuntu, macOS and Windows at exact head `f9edc66` |
| G3 offline acceptance | PASS | Formal `scripts/dashboard_acceptance.py` loopback relay/live/finished journey passes on Ubuntu, macOS and Windows at exact head `0f04fe6`; native/provider-only capabilities remain explicitly outside this gate |
| G4 visible live acceptance | NOT_STARTED | Preliminary real Ollama evidence exists; formal visible harness still required |
| G5 interactive visible and cleanup | NOT_STARTED | Owned PID/create-time cleanup is now formalized cross-platform; the interactive visible provider journey itself is still pending |
| G6 native cross-platform validation | NOT_STARTED | CI/browser/owned-cleanup suites are green on three hosted OSes, but the formal native/provider acceptance matrix is not complete |
| G7 final regression and human review | NOT_STARTED | Draft PR #51 is validation-only; no merge, tag or release permitted |

## Resume protocol

1. Inspect git status/remote branch and this ledger before editing; preserve unrelated changes.
2. Keep unfinished requirements explicit. Unperformed tests must never be described as performed.
3. Commit each completed gate and each independent bug fix separately. Commit messages identify scope, evidence, limitations and the next gate.
4. Save long-running evidence immediately. Large local browser/runtime artifacts remain under `.execweave-acceptance`; do not stage credentials, provider homes, virtual environments or browser binaries.
5. `test/live-dashboard-acceptance` is the implementation branch. `main` remains the v0.8.11 baseline until an explicit later merge decision.

## Exact-head five-green checkpoint

Verified implementation head: `dc3b09f6e2605707047c4857f6f610d764f8e295`.
Baseline remained `main` @ `a098eeb81f641b6e3fb1d65cc1905f46aa8eae30` while these checks ran.

Draft PR #51 triggered the full pull-request gates. All five workflows completed SUCCESS on the same implementation head:

- CI #930 / run `33963805935`: SUCCESS; Ubuntu 3.12, Windows 3.12 and macOS 3.12 jobs completed, including Ruff, unit/integration tests, provider smokes, graph/viewer materialization and platform-specific checks.
- Viewer Agent Isolation #334 / run `33963805939`: SUCCESS on Ubuntu, macOS and Windows. Each OS collected 1053 tests, deselected 995 and ran **58 viewer_e2e tests with 58 passed / 0 failed**. The crossing threshold remains 73; it was not raised.
- Provider Capability Stage Integrity #274 / run `33963805933`: SUCCESS. `tests/test_http_proxy.py` is restored to its baseline red-line content; the NEW-005 socket-ordering regression lives in the new `tests/test_http_proxy_streaming.py`. The checked `do_CONNECT` remains the actual runtime handler and still returns 405; no TLS MITM contract was weakened.
- Windows Launcher Compatibility #525 / run `33963805932`: SUCCESS.
- Provider Dashboard Contract #46 / run `33963805926`: SUCCESS across its provider contract matrix.

This checkpoint proves the checked source/test state above. It does **not** complete G3-G7, prove every real provider is installed/usable on all OSes, close the response-memory issue, or substitute for human visual review.

## G3 formal offline acceptance checkpoint

Verified formal-runner head: `0f04fe68a0871fbf892be67bc5f39758acce1767`.
`main` remained the v0.8.11 baseline while this exact head was tested. All five pull-request workflow families completed SUCCESS:

- CI #935 / run `33966622745`: SUCCESS.
- Viewer Agent Isolation #344 / run `33966622816`: SUCCESS on Ubuntu, macOS and Windows. Each OS first passed the existing 58-test viewer suite, then independently ran `scripts/dashboard_acceptance.py --mode offline --require offline-ollama-fixture` to PASS.
- Provider Capability Stage Integrity #279 / run `33966622765`: SUCCESS.
- Windows Launcher Compatibility #530 / run `33966622743`: SUCCESS.
- Provider Dashboard Contract #51 / run `33966622740`: SUCCESS.

The formal offline scenario uses one unique marker per run and a real local HTTP sequence: loopback model -> ExecWeave relay -> staged semantic sidecar -> live dashboard -> Chromium -> completed runtime stream -> strict semantic merge -> graph -> `viewer.html`. It verifies all of these as PASS on each hosted OS:

- launch of the harness-owned model/proxy/live server/browser;
- prompt visible in the live dashboard before response release and before any response semantic event exists;
- completed live update occurs in the same document with no duplicate prompt;
- projected conversation ownership is the real `agent_path=/root`, not a hard-coded DOM label;
- projected prompt contains the unique marker and assistant Final equals the exact DONE marker rather than merely matching text from the prompt;
- assistant `echo` tool call is present in `OBSERVED_ASSISTANT_TOOL_CALLS` on the same staged exchange identity;
- finished viewer details equal completed live details, live/finished conversation snapshots match, and the staged content store has no orphan files;
- browser page-error list is empty;
- all harness-owned server/client threads stop cleanly.

The scenario reports `SKIP_UNAVAILABLE`, not PASS, for File activity, Process, Network, Multi-agent and Fold state because this one-root offline semantic fixture does not claim native OS observation, a real provider process tree or multi-round/multi-agent coverage. Those capabilities remain assigned to later gates.

Two formal-runner defects were exposed and corrected without weakening product validation: the first implementation tried to strict-merge an intentionally unfinished runtime stream, and the second used a synthetic `start+10s` session-finish timestamp that failed correctly on slower macOS. The final runner snapshots live state before materialization and timestamps `session.finished` at actual completion; the strict validator remains unchanged.

G3 is therefore closed for the explicitly defined offline scope only. This does **not** prove a real provider on every native OS, complete visible/interactive acceptance, or substitute for G7 human review.

## G1 interaction checkpoint

- `diagnostics/audit_real_clicks.py`: PASS, six actual clicks across live/static, polling and changed-payload fold persistence (synthetic Codex pipeline).
- `diagnostics/audit_eight_children.py`: PASS, four viewports, eight isolated children, two root rounds; long Unicode prompt scroll reachability also PASS. This intentionally imports preconstructed entries, not provider capture.
- `diagnostics/audit_python_journey.py`: native Windows OS-only journey PASS, node count 2 -> 6 without refresh; file/process/network inspectors clicked; semantic content absent as expected; no owned child remainder.
- Ruff on the three audit scripts: PASS. Baseline audit report closed after adding provider availability, missing-journey and unknown-scan ledgers. This closes the audit-before-implementation gate, not the final acceptance program.

## G2 / NEW-006 process identity

Red: merge-to-graph regression produced 3 failures (contradictory identity, future sole PID candidate, explicitly matching future candidate); valid past match passed.

Green: minimal resolver fix prevents explicit create-time mismatch fallback and future-process matching. Contradictory evidence remains unresolved in the materialized graph and preserves candidate IDs for inspection. Full exact-head CI is now green. Native OS PID reuse has still not been deliberately forced, so that narrower stress case remains unclaimed.

## G2 / NEW-005 streaming and staged semantic capture

Transport red: both native HTTP content-length and chunked tests blocked while the upstream withheld the final chunk. `HTTPResponse.read1` now forwards available bytes; the independent native probe improved first-byte latency from 1.218s to 0.032s.

Semantic publication was then split into two real phases using one `exchange_id`:

- request evidence, request config and request raw content are materialized immediately after dispatch and before waiting for model response headers/body;
- response completion uses response-only emitters, so it does not duplicate request evidence;
- request-only capture no longer creates an empty response artifact;
- the full-fidelity metadata artifact that was previously written and then orphaned by outer filtering is avoided on the staged path;
- OpenAI-compatible `OBSERVED_PROVIDER_REQUEST_CONFIG` is now request-phase evidence too.

The three-OS viewer run verifies both OpenAI-compatible and Ollama two-phase capture leave no orphan content and no request duplicates. `test_relay_prompt_live_e2e.py` also passes on all three OSes: the prompt is visible in the live DOM before the response is released, no response semantic event exists at that point, the completed live final appears once, and finished viewer details equal the live details.

Memory red gate: exact head `322f5630893a6a5c0cd988fd55f7d5f87c91281c` added a 16,800,336-byte Ollama NDJSON response whose canonical assistant output is only `DONE`. The gate first requires the raw full-fidelity response artifact to remain exactly 16,800,336 bytes and the canonical semantic response to contain `DONE`, then requires traced transport/capture peak memory to remain at or below 12,582,912 bytes. The unbounded implementation failed only this memory assertion on all three hosted OSes: Ubuntu `85,940,663`, macOS `85,999,882`, Windows `85,999,534` bytes.

Green: the product-default relay now uses file-backed raw response capture and incrementally parses streamed frames from disk. The parsed stream-chunk evidence is itself written as a file-backed canonical JSON array, while provider response emitters still receive the assembled canonical response. Explicit custom recorder callbacks retain the historical `response_body: bytes` API and continue through the old path. Raw response evidence, `OBSERVED_INFERENCE_STREAM_CHUNKS`, canonical Final/tool calls, prompt-before-response publication, and first-byte streaming remain required; the 12 MiB threshold was not raised. A follow-up cleanup closes the temporary raw capture on an interrupted relay before early return.

Exact-head verification at `f9edc6693825ede8e600d877de00e07131302fd4` is five-workflow green:

- CI #946 / run `33969608149`: SUCCESS. Ubuntu, macOS and Windows all passed the large-response memory gate and the full CI job sequence.
- Viewer Agent Isolation #366 / run `33969608109`: SUCCESS on Ubuntu, macOS and Windows. Each OS passed all **59 viewer_e2e tests**, the formal G3 offline journey, and the formal owned-process cleanup journey.
- Provider Capability Stage Integrity #290 / run `33969608118`: SUCCESS; CONNECT remains disabled with 405 and the staged runtime handler contract is intact.
- Windows Launcher Compatibility #541 / run `33969608158`: SUCCESS.
- Provider Dashboard Contract #62 / run `33969608137`: SUCCESS.

NEW-005 is therefore closed for the audited transport/staged-semantic/memory defect scope, and this was the final open item in G2. G2 is PASS. This does **not** claim constant memory for arbitrarily large canonical assistant text itself; it proves the relay no longer retains/copies the complete large wire response in RAM merely to preserve raw/stream evidence.

Historical real Ollama run `96e56662` preserved matching live/final captured text and cleanup, but the model itself did not return the requested DONE marker. That run remains exact-answer FAIL, not a capture failure or a formal G4 PASS. Earlier `4007a5f5` is limited positive evidence only.

## G2 / NEW-002 Cursor test isolation

The shim-only test supplies an empty desktop fallback candidate list so a developer machine's installed Cursor does not invalidate the fallback fixture. Product command resolution is unchanged; desktop preference and arbitrary/custom installation locations remain separately tested. The current Windows Launcher workflow and full Windows CI are green.

## G2 / NEW-001 browser discovery and layout repair

Five previously omitted browser modules are now collected by `viewer_e2e`. What began as 27 marked tests became a 58-test three-OS suite before the separate NEW-004 readability gate raised the suite to 59 tests.

The initially exposed failures were reviewed independently instead of being blanket-labeled product bugs. Confirmed layout defects were fixed without raising the crossing threshold:

- post-Dagre layout now restores ExecWeave semantic X lanes and evidence bands;
- wide runtime/process nodes no longer intrude into the next semantic lane;
- connected evidence stays beside the execution spine and detached evidence is packed below it;
- evidence lanes keep independent row starts instead of being serialized into one global rank list;
- the Arrange button no longer runs a second unconstrained Dagre pass;
- bundle members use deterministic ordered parallel rails instead of sharing one dense trunk, reducing the crossing fixture below the recorded 73 baseline;
- external endpoint clustering is tested separately from lane geometry using loopback fixtures where raw endpoint identity is required.

Viewer Agent Isolation #344 was 58/58 PASS on Ubuntu, macOS and Windows at the G3 exact head. The later NEW-004 and NEW-003 checkpoints verify the expanded 59-test suite on all three OSes. Formal visible-provider acceptance remains separate.

## G2 / NEW-003 owned descendants

Native audit reproduced a child process outliving the launched root. Historical PR #26 had already documented descendant lifetime as a collector boundary, so the product was not changed to wait indefinitely for every descendant; a provider daemon could otherwise keep the session alive forever.

The acceptance harness now uses `scripts/acceptance/processes.py` to track only explicitly seeded PID + creation-time identities and their recursively observed descendants. Once an owned child is observed it remains owned even after its root exits. Cleanup gives a bounded grace interval, then bounded terminate/kill, and refuses PID-reuse/create-time mismatches. It never adopts a process by executable name or command line.

Unit contract red/green: the first helper commit was stopped by Ruff before tests because of one unused import; after that lint-only correction, `ce883d9ab3892a5647336ef1f425f74a4845ff1e` passed the real subprocess tests on Ubuntu, Windows and macOS. The tests force a child to outlive its launched root, require the orphan to be cleaned, and require an unrelated sentinel process to remain alive; a separate mismatch test proves a live process with the same PID but wrong creation-time identity is not touched.

Formal matrix: exact head `7e1f10cbdf061cc6c31ebe307e33b6c8573eda3d` adds `scripts/owned_cleanup_acceptance.py` as a separate scenario after the existing Viewer and G3 offline gates. Viewer Agent Isolation #358 / run `33968069114` passed on Ubuntu, macOS and Windows; each OS passed all **59 viewer_e2e tests**, passed the formal offline G3 journey, and then passed the formal owned-process cleanup journey. The same exact head also completed:

- CI #942 / run `33968069096`: SUCCESS.
- Provider Capability Stage Integrity #286 / run `33968069063`: SUCCESS.
- Windows Launcher Compatibility #537 / run `33968069118`: SUCCESS.
- Provider Dashboard Contract #58 / run `33968069092`: SUCCESS.

NEW-003 is therefore closed at this exact head. This proves the harness can clean only run-owned descendant identities within bounds without redefining product child lifetime or killing an unrelated process. It does **not** make the still-unexecuted interactive provider journey in G5 PASS.

## G2 / NEW-004 initial Fit readability

Red gate: `tests/test_dashboard_initial_fit_readability_e2e.py` fixes Chromium at 1280x720 on the dense seven-agent readability graph, measures first-paint screen-space agent label/node size, and then explicitly clicks `Fit graph` to ensure whole-graph overview remains reachable. At red head `343c7923215bce0663cf463f7eac477c3b13be08`, Viewer run `33967062569` selected 59 tests; the new gate alone failed while the previous 58 passed. macOS measured `scale=0.3979328165`, minimum agent node height `19.8966px` and minimum label height `6px`, below the locked `24px` node / `7px` label gates.

Green policy: exact head `d6d3211015c63fe12229e8ddf9deea2904fdeffa` keeps the first automatic snapshot/delta presentation at a readable `minScale=0.5`, while the user-invoked `Fit graph` continues to use the original `0.07` overview floor. The change is applied at the final shared dashboard HTML seam, so live and static viewers consume the same camera policy; it does not raise the crossing threshold or weaken the full-graph navigation assertion.

Exact-head verification at `d6d3211` is five-workflow green:

- CI #938 / run `33967294473`: SUCCESS.
- Viewer Agent Isolation #350 / run `33967294483`: SUCCESS on Ubuntu, macOS and Windows. Each OS passed all **59 viewer_e2e tests** and then independently passed the formal offline G3 scenario.
- Provider Capability Stage Integrity #282 / run `33967294475`: SUCCESS.
- Windows Launcher Compatibility #533 / run `33967294481`: SUCCESS.
- Provider Dashboard Contract #54 / run `33967294488`: SUCCESS.

NEW-004 is therefore closed at this exact head. G2 remained open at that checkpoint only for the distinct response-memory/RSS bound, which is closed by the later NEW-005 memory checkpoint above.

## G3 reporting and formal-runner checkpoint

Strict PASS/FAIL/SKIP_UNAVAILABLE result model and escaped HTML/JSON reporting are implemented. Unexecuted required assertions fail; unavailable required providers do not pass; later retries cannot erase an earlier failure; reports redact common credential-bearing values. Conversation contracts require the DONE marker in assistant final text rather than merely in the prompt, correct root ownership, and absence of foreign markers.

The formal core runner now exists at `scripts/dashboard_acceptance.py`, is invoked by the three-OS Viewer workflow, and passed the explicit offline scenario on Ubuntu, macOS and Windows at `0f04fe68a0871fbf892be67bc5f39758acce1767`. The five `SKIP_UNAVAILABLE` capabilities named above remain intentionally outside the offline scenario and are not silently promoted to PASS.

Generated environments, browser binaries, temporary runs and raw logs remain local under ignored `.execweave-acceptance/` and `artifacts/dashboard-acceptance/`. They are not deleted. Reports/screenshots must be reviewed and sanitized before sharing; local run evidence is not automatically included in a source push.
