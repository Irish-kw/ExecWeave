# Grok Bot real-machine Antigravity acceptance — ExecWeave PR #40

Verifier: ExecWeaveBot (independent). Implementation SHA tested: `f79d73d3231b6862419fab484111b449b2778c07`.
This report is evidence, not a merge decision. `PR_READY_TO_MERGE` is not asserted.

## Git provenance

REPO=Irish-kw/ExecWeave
BRANCH=fix/root-layout-toolcall-aggregation
START_SHA=f79d73d3231b6862419fab484111b449b2778c07
MAIN_SHA=abf1e6b50f0581ce6f8d055f9a12fd8448d02d80
PR_NUMBER=40
WORKTREE_CLEAN_BEFORE_RUN=NO

Note: the only dirty path before the run was untracked `artifacts/` created for this evidence directory. `src/`, `tests/`, `pyproject.toml`, and `.github/` were not modified.

## Environment

OS=Debian GNU/Linux 13 (trixie)
ARCH=x86_64
PYTHON_VERSION=Python 3.13.5
BROWSER_VERSION=Google Chrome 151.0.7922.169
EXECWEAVE_VERSION=0.8.6
EXECWEAVE_IMPORT_PATH=/workspace/ExecWeave/src/execweave/__init__.py
EXECWEAVE_EXECUTABLE=/workspace/execweave-venv/bin/execweave
ANTIGRAVITY_VERSION=1.1.23
ANTIGRAVITY_EXECUTABLE=/home/box/.local/bin/agy
RUN_TIMESTAMP=2026-09-01T10:24:10Z (first launch); recorded run used below is RUN2 started 2026-09-01T10:29:08Z
TZ=UTC on the machine; user zone Asia/Taipei

## Real execution

REAL_EXECWEAVE_STARTED=YES
REAL_ANTIGRAVITY_STARTED=YES
REAL_AGY_PROMPTS_ENTERED=YES
REAL_AGY_TOOL_CALLS_EXECUTED=YES
EXECWEAVE_RECORDED_REAL_AGY=YES
PROVIDER_CREATED_CHILDREN=8
PROVIDER_CREATED_MAIN_ROUNDS=2

First background `script` PTY launch (run1, port 43287) never received TUI input. It was stopped. RUN2 launched in a visible xfce4-terminal with `execweave live --open --watch-root /workspace/agy-pr40 --output-dir .../raw/run2 --linger 1800 -- /home/box/.local/bin/agy`. Workspace trust was accepted. Reasoning was set with `/effort low` (Gemini 3.7 Flash · low) before Round 1. Round 1 and Round 2 were pasted into the same main conversation `58d4e2ea-7635-4d05-9a77-73ac366594e9`.

Children (subtask nodes): R1-A1 Worker, R1-A2 Worker, R1-A3 Worker, R1-A4 Worker, R1-A5 Worker, R2-A1 Worker, R2-A2 Worker, R2-A3 Worker.

R1-A1 conversation `a767b64f-de19-4df0-99d8-d534b9c9b0da` executed two separate `run_command` tool calls:
- `echo EW_PR40_CALL_ONE`
- `echo EW_PR40_CALL_TWO`

Both Bash approvals were granted in the real Agy TUI.

## Root/topology

UNIQUE_ROOT=FAIL
ROOT_IS_REAL_MAIN_AGY=FAIL
CHILDREN_DO_NOT_STEAL_ROOT=PASS
GENERIC_ANTIGRAVITY_ALIAS_REMOVED=FAIL
TWO_MAIN_ROUNDS_PRESERVED=PASS

Live Dashboard search for `/root` dimmed every node; no node is labeled `/root` (also absent from finished `graph.json`). The genuine main conversation is rendered as `AGENT conversation · 58d4e2ea` with `identity_semantics=provider_conversation_id`, `routing_identity_only=true`, `execution_observed=false`. Child conversations keep their own UUIDs and are not labeled `/root`. A generic `agent:Antigravity` node remains in the finished graph. Round 1 and Round 2 user turns both belong to conversation `58d4e2ea`. Eight child conversations were created and remain distinct.

LIVE_ROOT_ID=(none labeled /root; main conversation 58d4e2ea-7635-4d05-9a77-73ac366594e9)
FINISHED_ROOT_ID=(none labeled /root; same main conversation id)
LIVE_CHILD_COUNT=8
FINISHED_CHILD_COUNT=8

## Interaction

REAL_POINTER_DRAG=PASS
INCIDENT_EDGES_REDRAW_DURING_DRAG=PASS
MANUAL_POSITION_PERSISTS_AFTER_RELEASE=PASS
ARRANGE_BUTTON_PRESENT=PASS
REAL_ARRANGE_CLICK=PASS
ARRANGE_RECOMPUTES_POSITIONS=PASS
ARRANGE_IS_NOT_JUST_FIT=PASS

`/root` did not exist, so the real pointer dragged the main AGENT node `conversation · 58d4e2ea` ~150px right and ~60px down. The node followed the pointer, stayed after release, and incident edges redrew. Arrange was clicked on the real toolbar button (not `window.__execweaveArrangeGraph`). Layout recomputed; `/root` still did not appear.

## Tool aggregation

MARKER_CALL_ONE_OBSERVED=PASS
MARKER_CALL_TWO_OBSERVED=PASS
SEMANTIC_FULL_FIDELITY_DEDUPED=PASS
DUPLICATE_TOOL_ENTITIES_CANONICALIZED=PASS
EXPECTED_MARKER_INVOCATIONS=2
MARKER_LOGICAL_INVOCATIONS=2
ACTUAL_TOTAL_TOOL_INVOCATIONS=19
RAW_TOOL_EVIDENCE_COUNT=19
CALLED_TOOL_EDGE_RENDERING=PASS

Live UI showed a single canonical `TOOL run_command ×2` with Calls=2 and a `CALLED_TOOL` edge `conversation · a767b64f → run_command ×2`. Finished graph has one `tool:antigravity:run_command` and two `tool_call` nodes, plus declared command nodes for each echo. Extra real provider tools were not hidden: invoke_subagent×2, view_file×3, manage_subagents×4, send_message×8, run_command×2.

EXTRA_TOOL_INVOCATIONS=invoke_subagent×2 view_file×3 manage_subagents×4 send_message×8

## Tool inspector

TOOL_NODE_CLICKABLE=PASS
INVOCATIONS_SECTION_PRESENT=PASS
INVOCATIONS_EXPANDABLE=PASS
CALL_ONE_INPUT_VISIBLE=PASS
CALL_ONE_OUTPUT_VISIBLE=FAIL
CALL_TWO_INPUT_VISIBLE=PASS
CALL_TWO_OUTPUT_VISIBLE=FAIL
TIMESTAMPS_VISIBLE=PASS
RAW_CALL_IDS_VISIBLE=PASS
CONTENT_REFERENCES_VISIBLE=PASS

Both invocation rows expanded in the real Dashboard. Inputs show `CommandLine: "echo EW_PR40_CALL_ONE"` and `echo EW_PR40_CALL_TWO` with timestamps and content SHA-256 refs. Both records show `"output": null` — captured stdout of the echo markers was not visible in the inspector.

## Live/finished parity

LIVE_DASHBOARD_OPENED=PASS
FINISHED_DASHBOARD_OPENED=PASS
VIEWER_HTML_PRESERVED=PASS
LIVE_FINISHED_ROOT_PARITY=PASS
LIVE_FINISHED_TOPOLOGY_PARITY=PASS
LIVE_FINISHED_TOOL_AGGREGATION_PARITY=PASS

Live after finish and `viewer.html` both lack `/root`, both show 8 R1/R2 workers, both aggregate the two echo calls into one `run_command` tool. Meaning of the graph did not change because the run finished. Finished artifacts: `raw/run2/viewer.html`, `raw/run2/graph.json`, `raw/run2/events.semantic.jsonl`.

LIVE_MARKER_INVOCATIONS=2
FINISHED_MARKER_INVOCATIONS=2
LIVE_TOOL_CALL_COUNT=19
FINISHED_TOOL_CALL_COUNT=19

## Evidence

LIVE_SCREENSHOT=screenshots/live-both-rounds-graph.webp
DRAG_SCREENSHOT=screenshots/after-drag.webp
ARRANGE_SCREENSHOT=screenshots/after-arrange.webp
FINISHED_SCREENSHOT=(captured after viewer.html materialization; see screenshots/ and computerUse assets)
TOOL_INSPECTOR_SCREENSHOT=screenshots/tool-invocations-expanded.webp
VIEWER_HTML=viewer.html (copy) and raw/run2/viewer.html
RAW_EXECWEAVE_DIR=raw/run2/
STDOUT_LOG=execweave_stdout.log
STDERR_LOG=(none separate; live TUI/PTY)
SHA256_MANIFEST=SHA256SUMS.txt
RAW_ARTIFACT_PUSH=(set after git push)

## Verifier integrity

USED_MOCK=NO
USED_SYNTHETIC_JSON=NO
USED_FIXTURE_AS_REAL_EVIDENCE=NO
PRODUCTION_CODE_CHANGED_BY_VERIFIER=NO
FAILURE_EVIDENCE_PRESERVED=YES
RACE_DETECTED=NO

## First observed failure

The Live Dashboard never presented an authoritative `/root` node for the real main Agy conversation. Search for `/root` matched nothing. Finished `graph.json` also contains no `/root` / `viewer_root`. The main conversation is `58d4e2ea-7635-4d05-9a77-73ac366594e9` rendered as `Antigravity conversation` with `routing_identity_only=true`. A generic `agent:Antigravity` node remains. Secondary inspector issue: echo stdout is `output: null`.

Preserved: screenshots/live-r1-dashboard-fit.webp, screenshots/live-both-rounds-graph.webp, raw/run2/graph.json, raw/run2/viewer.html.

## Gate decision

GROK_BOT_REAL_MACHINE_GATE=FAIL
PRODUCTION_CODE_CHANGED_BY_VERIFIER=NO

Real-machine evidence does not support unique `/root` identity layout. Tool-call aggregation of the two marker invocations is supported. Do not merge. Do not treat this as a pytest-only pass.
