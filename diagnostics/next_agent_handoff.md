# Handoff: implementation-only agent, then return for native review

## Mandate

User explicitly requested a stop/checkpoint. Continue source review, fixes and
offline/CI contracts; **do not execute real-provider or native acceptance journeys**.
You do not have the original Windows machine. Local/hosted unit tests and offline
Chromium fixtures are permitted, but are not evidence of native live-provider PASS.
No cloud Codex/Claude/Antigravity calls; no Ollama live run/model download; no user
authentication/config mutation. All real-machine requirements remain unverified
until this work returns to the original agent/environment for review and execution.

Repo: Irish-kw/ExecWeave; branch: test/live-dashboard-acceptance; PR #51 Draft.
Last implementation checkpoint: 06ebe5cc906035cad055bae6a812b4213432b350.
Main baseline: a098eeb81f641b6e3fb1d65cc1905f46aa8eae30.
Fetch first; these hashes may be stale. Before EVERY Git write fetch/recheck the
remote. Use only fast-forward integration and atomic non-force push. If another
writer advanced, read their work before integrating; never overwrite or rewrite it.
Do not merge PR/main, tag, release, force push, rebase public history, remove tests,
relax thresholds or convert required checks into optional SKIPs.

## Read first

- diagnostics/current_state_reaudit.md
- diagnostics/gate_status.md
- diagnostics/gate_status_history_through_g3.md
- diagnostics/execweave_full_audit.md and diagnostics/pr_regression_map.md
- scripts/dashboard_acceptance.py, owned_cleanup_acceptance.py,
  ollama_visible_acceptance.py, ollama_interactive_acceptance.py,
  python_native_acceptance.py and scripts/acceptance/
- Relevant tests and all five PR workflow definitions.

The audit/map preserve baseline observations and contain stale present-tense
language. Neither these documents nor CI green may establish current product PASS.
Memory test actual name: tests/test_http_proxy_response_memory.py (12 MiB).
Edge crossing threshold remains 73; readability gates remain node >=24px,
label >=7px; automatic fit floor .5, explicit Fit floor .07.

## Independently observed progress

- Remote 1d6d65f five workflows SUCCESS (run IDs in current_state_reaudit.md).
- Native Windows Browser 59 passed, zero selected skips/failures.
- Native Windows offline scenario PASS, with its five out-of-scope SKIPs intact.
- REAUDIT-001 fixed in 06ebe5c: removed bare-PID finally kill from cleanup scenario
  and test. Two added structural guards were red before; 21 targeted tests green
  after. Existing native orphan/sentinel/mismatch tests retained. Formal Windows
  cleanup PASS with zero remainders and unrelated sentinel preserved.
- Formal G4 **FAIL**: real deepseek-r1:1.5b/client/headed Live worked, nodes 4->8,
  but Windows CTRL_BREAK yielded 3221225786 and only events/semantic JSONL.
  No events.semantic.jsonl, graph.json or viewer.html. Owned cleanup PASS.
- G5 real journey not executed. G6 native Python not executed by this re-audit.
- No full final-head visual review; do not inherit one.

Raw original-machine artifacts are ignored/local, not in Git. Missing files in
your environment are not evidence that the original run passed or failed anew.

## Priority implementation work

1. REAUDIT-002: fix formal Windows live collector interrupt/finalization strategy.
   G4/G5 launch ExecWeave through pipe-backed CREATE_NEW_PROCESS_GROUP and send
   CTRL_BREAK. Collector handles KeyboardInterrupt, but the actual journey failed
   before finalization. Prior scratch success used an actual ConPTY Ctrl+C.
   Determine a safe real terminal strategy (including collector, not merely client).
   Preserve process identity and bounded cleanup. No fake PTY, no broad console
   broadcast, no killing existing servers. Do not claim the fix works natively
   from mocks/source checks; label NEEDS_NATIVE_VALIDATION.

2. REAUDIT-003: G4 checks graph type `endpoint`, but native schema uses
   `network_endpoint`; absent Network is currently SKIP. Required G4 Network must
   FAIL if unobserved. Use actual process-associated CONNECTED_TO evidence, not
   arbitrary endpoint existence. Preserve unavailable-provider reporting.

3. Strengthen real-answer checks: current G4 non-empty live Final plus matching
   finished Final can accept equally wrong output or placeholders. Compare actual
   client final evidence, treating thinking output/terminal wrapping explicitly.
   Do not confuse prompt marker or 'Not observed' with final. Keep short bounded
   prompts; do not force one exact answer as a substitute for capture fidelity.
   Existing _clean_output removes ANSI/CR but does not decode arbitrary terminal
   redraws. Native validation must settle actual CLI behavior.

4. G5: require true Windows ConPTY backend, not just class.backend label; test
   actual PTY behavior where available, with missing capability explicitly
   unavailable. Check readiness before typing, one terminal/two rounds, actual
   response exchange identity (not model load/probe response counts), visible
   output, genuine interrupt, fold state through changed updates/selection,
   exact live/finished ownership/parity. Current Windows unit contract merely
   checks availability/class label and returns: it proves no native session.
   Missing terminal integration must remain required pending, not PASS.

5. Audit reporting: required capability SKIPs can currently leave provider PASS
   when any other feature passed. Make required scope explicit without turning
   offline's out-of-scope five features into fake PASS. Preserve failures across
   retries. Add run source SHA/dirty-state metadata so artifacts cannot imply
   exact-head evidence they do not provide. Distinguish negative semantic absence
   checks in Python from actual semantic support in the rendered report.

6. Harden all runners' KeyboardInterrupt/report persistence, failure screenshot/
   console evidence, browser/reader cleanup and live visible output. Existing
   pageerror listeners alone do not capture console.error. Avoid broad refactor.

7. Define G6 matrix and its explicit release-blocking required cells; add safe
   offline/process/browser CI coverage without real-provider calls. Native Python
   runner exists but is not invoked in Viewer workflow. Its actual journey and
   final parity/attribution still need review. No fabricated Windows/macOS/Linux
   provider results. Portable file changes are not syscall reads; Linux live uses
   portable, record can use strace; preserve macOS observation limitations.

8. Review temporary _dashboard_shell_base/_http_proxy_base/_stage/_bounded module
   seams and runtime AST security guard. Public handler disables CONNECT with 405
   and rebinds the base handler. Do not replace this with a decorative checked
   class that isn't the runtime handler. Consolidation is deferred while native
   journeys remain red; do not start a large architecture rewrite.

## Explicit return-to-original-machine checklist

Record each as NEEDS_NATIVE_VALIDATION in the gate ledger (not a feature result
value; result schema remains PASS/FAIL/SKIP_UNAVAILABLE). Required unavailable
cells block gate completion.

- Windows G4: fresh owned server/relay, independent existing-model client,
  headed prompt/final, exact client capture, native process/network, same document,
  actual root click, real interrupt, all five artifacts, finished parity, cleanup.
- Windows G5: actual ConPTY collector/client, one interactive session/two prompts,
  real output, history open/closed persistence, terminal interrupt, finalization,
  unrelated sentinel survives, zero owned remnants.
- Windows G6 Python: real process/child/file/network action, actual inspectors,
  strict absence of semantic evidence, same-document live/finished consistency.
- Actual Cursor arbitrary installation resolution/launcher behavior without
  adopting or terminating an existing user desktop instance.
- macOS local Ollama + PTY + native process/file/network and limitations.
- Linux portable and real strace path + local Ollama + PTY + native evidence.
- Deliberate PID reuse/native lifecycle stress: not proved by synthetic mismatch.
- Harness Ctrl+C/crash/error cleanup, browser/temporary relay/reader remnants.
- Human-visible screenshot review: live/finished/dense graph/history/tool/process/
  file/network inspectors at specified viewports, not just green DOM assertions.

## Delivery back

One independent bug per clear commit; record red/green commands, evidence and
limitations. Push non-force after remote check. Observe Actions for the EXACT
final HEAD; do not borrow parent green or create an endless docs/status cycle.

Return: final SHA, main SHA, PR state, commit list, exact-head five-workflow IDs/
statuses, fixes and remaining defects, CI/offline evidence, ordered commands for
original Windows machine, all NEEDS_NATIVE_VALIDATION cells, and artifact paths.
Do not mark G4/G5/G6/G7 PASS. READY_FOR_HUMAN_MERGE_DECISION stays NO pending
original-agent code review and real-machine validation. No merge/tag/release.
