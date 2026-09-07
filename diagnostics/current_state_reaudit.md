# Current-state re-audit (2026-09-05)

Remote inspected after fresh fetch: `1d6d65f89b91889fdc3526c8378f18fd6142bc85`.
Main remains `a098eeb81f641b6e3fb1d65cc1905f46aa8eae30`.
PR #51 is OPEN / DRAFT, validation-only, not merged. Clean local branch was
39 commits behind and was fast-forwarded, without a merge commit.

## Evidence, not inherited PASS

All five workflow families succeeded for the inspected remote head:
CI 33972746888; Viewer 33972746843; Integrity 33972746856;
Windows Launcher 33972746848; Provider Contract 33972746840.
These are contract/offline evidence, not G4/G5/G6 real-provider acceptance.

Read the current and historical ledgers, baseline audit and PR map, formal
offline/cleanup/G4/G5 runners, reporting/contracts/process ownership code, and
requested browser and memory tests. The requested large-response test filename
is actually `tests/test_http_proxy_response_memory.py`; its limit remains 12 MiB.
Baseline audit and PR map contain historical present-tense descriptions that are
stale for this branch (Ubuntu-only Browser, 27 tests, unbounded response capture).
Do not interpret them as current-head conclusions.

## Reopened findings

### REAUDIT-001 / P1: cleanup finalizer bypasses process identity

Affected: owned_cleanup_acceptance.py and its original subprocess test.
Both ran `psutil.Process(child_pid).kill()` in finally after the identity-aware
tracker had already cleaned the child. PID reuse can therefore target an unrelated
process. Native PID reuse was not forced; source reproduction is conclusive for
the unsafe fallback, not proof that an unrelated user process was killed.

Removed only the bare-PID fallback; the existing bounded tracker retains observed
descendants. Two structural guards fail before and pass after the change. Native
subprocess orphan/sentinel and mismatch tests still run, not replaced by AST tests.
Targeted Windows selection: 21 passed, including G4/G5 contracts and 12 MiB memory.
Formal Windows cleanup: PASS, marker EW-CLEANUP-D182751DC0, tracked=4,
terminated=2, forced kills=0, owned remainders=0, unrelated sentinel survived.
Evidence: `.execweave-acceptance/reaudit/cleanup/ew-cleanup-d182751dc0/summary.json`.
G2 must be revalidated, not inherited as fully closed at current head.

### REAUDIT-002 / P1: formal Windows G4 does not finalize

Real installed deepseek-r1:1.5b, fresh owned endpoint, real independent client,
headed Chromium: prompt/final shown and live nodes 4 -> 8. CTRL_BREAK yielded
3221225786 and only events.jsonl/semantic.jsonl, no merged graph/viewer.
Formal required run correctly FAIL; cleanup reported zero owned remainders.
Evidence: `.execweave-acceptance/reaudit/g4-before/ollama-visible-windows-76f15065/`.
The runner uses a pipe-backed Windows process group, whereas prior successful
scratch evidence used a ConPTY Ctrl+C. Terminal finalization needs correction.

### REAUDIT-003 / P1: G4 can hide required Network

The runner tests graph type `endpoint` although native schema uses
`network_endpoint`, then SKIPs missing Network. G4 requires Network; missing
observation must fail, not become a successful partially skipped provider run.
Final also compares only live/finished, not independent client text; non-empty
placeholder or equally wrong live/static text is insufficient evidence.

### Remaining unaccepted G5/G6 scope

Windows terminal contract returns after checking a class label, without spawning
a ConPTY. Interactive capture logs output but does not display it live. G5 counts
response events without filtering model-load/probe versus actual prompt exchanges.
G6 native Python harness exists but is not executed by the Viewer workflow.
No macOS/Linux local-model evidence has been independently established here.
Native deliberate PID reuse stress remains unexecuted.

Temporary shell/proxy layers contain module-global rebinding and shared HTML string
seams. Runtime public handler overrides CONNECT with 405 and passes that class to
the base server via rebinding. Keep behavior regressions; do not consolidate while
required native journeys remain red.

## Gate interpretation at this checkpoint

G0/G1 baseline artifacts exist (not full current acceptance).
G2 reopened for cleanup safety revalidation; G3 current local Browser/offline rerun
pending; G4 FAIL; G5 IN_PROGRESS/unaccepted; G6 IN_PROGRESS/incomplete;
G7 NOT_STARTED. READY_FOR_HUMAN_MERGE_DECISION=NO.

## Stop/checkpoint requested by user

Cleanup fix committed and pushed as `06ebe5cc906035cad055bae6a812b4213432b350`.
Further local verification completed before stopping:

- Native Windows full marked Browser selection: **59 passed, 1024 deselected**,
  zero selected skips/failures, 94.77 s. JUnit: `.execweave-acceptance/reaudit/viewer.xml`.
  Product source was `1d6d65f`; only the cleanup fix/new guards differed during this
  run. This does not establish final-head remote Actions status.
- Formal Windows offline runner: PASS, marker `EW-OFFLINE-E0FC1C2B0D`,
  `.execweave-acceptance/reaudit/offline/offline-windows-dfc01c99/`.
  The five explicitly out-of-scope features remain SKIP_UNAVAILABLE.
- No new G4/G5 fix has been implemented. G4 failure is preserved, not retried away.
- No G5 real-model run or native G6 run performed during this re-audit.
- No screenshot visual review completed during this re-audit; prior screenshots
  are not silently promoted to a current visual PASS.

This is an interim state audit, not FULL_AUDIT_COMPLETE. Full module-by-module
proxy/AST guard and workflow-history evidence verification remains open. Next agent
must perform source/offline/CI work only; all machine/provider gates must return
to the original Windows environment for review and authorized execution.
