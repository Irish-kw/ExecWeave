# Source/offline hardening checkpoint (2026-09-06)

## Synchronized state and evidence boundaries

Started clean after fast-forward from 2f93d629 to
`0cd04b3e4c64bcb8abd06c95be71ae97392f7efa`. Origin/main remained
`a098eeb81f641b6e3fb1d65cc1905f46aa8eae30`. GitHub PR #51 was OPEN/DRAFT,
explicitly validation-only. No merge, tag, release or history rewrite.

Fresh five-family PR evidence for exact 0cd04b3: all SUCCESS:

| Family | Run ID |
|---|---|
| CI | 33987193636 |
| Viewer | 33987193633 |
| Integrity | 33987193632 |
| Windows Launcher | 33987193651 |
| Provider Contract | 33987193631 |

These results do not close real-provider gates. No real Ollama or cloud provider
was executed during this source/offline hardening turn.

## Corrected stale handoff claims

- 2f93d629 already binds the two rounds to distinct marker/request identities.
- 0d209416/33593e5/7742b2c added required terminal round-trip coverage. pywinpty
  was in the Windows **dev** extra, not e2e, at entry; Viewer installs dev,e2e
  together. This checkpoint also declares it in e2e so that extra alone provides
  the dependency for its required Windows terminal test.
- 0cd04b3 already introduced Ctrl+C then /bye through a provider-aware wrapper.
  f2d6a43 additionally makes the underlying POSIX interrupt method write Ctrl+C
  instead of issuing an external SIGINT, and clarifies the /bye timeout error.
- `tests/test_dashboard_live_camera_e2e.py` does not exist. Relevant actual files:
  `test_dashboard_camera_scheduler_e2e.py` and `test_dashboard_node_drag_camera_e2e.py`.
- Older audit/PR-map present-tense statements are historical, not current results.

## Independent native evidence from BEFORE this turn

The original Windows agent preserved clean-2f93d629 verification locally under
`.execweave-acceptance/verify-2f93d629/verification.md`. It was read, not rerun here:

- 61 Browser tests and 26 targeted contracts passed.
- G4 `ollama-visible-windows-8cb07766` reported PASS (17.203 s), using the revised
  owned-server-exit strategy. It did NOT validate ExecWeave terminal-A Ctrl+C.
- G5 `ollama-interactive-windows-56cab98a` FAILED (33.781 s): idle client remained
  alive after Ctrl+C and printed `Use Ctrl + d or /bye to exit.` Both rounds and
  fold assertions had run; subsequent finished/other assertions had not. Finally
  producing graph/viewer does not turn those unexecuted assertions into PASS.
- Python `python-native-windows-97fcb271` passed OS-only acceptance (12.906 s).
  Prompt/Final/Tool fields were negative absence checks, not semantic support.
- All three formal runs reported no owned remainder. No later-head native PASS
  may be borrowed from these historical artifacts; raw artifacts are ignored/local.

## Terminal transcript implementation

Shared PTY/ConPTY capture now tees a redacted, control-free line transcript to
stdout and its artifact. UTF-8 decoding is incremental; redaction waits for a whole
line or EOF so labels/tokens split across reads cannot leak. Output writes from
transcript instances are serialized. This is not a screen recording or ANSI replay.
A line over 64 KiB is explicitly replaced by an omission notice for bounded safe
redaction; such a transcript is NOT full-fidelity raw terminal evidence. Model HTTP
raw evidence remains separately captured by the product. Long-line fidelity and
partial-line token-by-token display are not claimed by this implementation.

Tests include split credentials/code points, EOF flush, control filtering, bounded
oversized lines, and actual terminal echo appearing in both artifact and stdout.

Local full pytest after tee implementation: 1098 passed, 2 skipped, 163.56 s;
Ruff PASS. Skips: POSIX launcher and Linux strace on Windows. JUnit is local at
`.execweave-acceptance/hardening-offline.xml`. The extra stdout echo assertion was
also executed independently after that suite started and passed.

### NEW-007 / P1 acceptance harness: relative output breaks finished offline viewer

Formal CLI reproduction at aa861a2 with `--output-dir .execweave-acceptance/hardening-offline`
failed after successful live assertions: `ValueError: relative path can't be expressed
as a file URI`. Local failed run: `offline-windows-820efba8`. Root cause: `_run_offline`
retains a relative run root and calls `.as_uri()` on it. Default CLI path is also
relative. CI used absolute output roots and therefore missed the normal CLI path.
All OSes share the source defect; only Windows reproduction is claimed here.

Minimal fix resolves/expands the output root at the runner boundary. New required
Browser regression invokes the actual CLI from a temporary cwd with a relative path
containing spaces and requires finished viewer, cleanup and retained offline SKIPs.
Red: 1 failed with the exact URI error. Green: 1 passed; Ruff PASS. The earlier
failed report remains preserved and is not rewritten as PASS.

## Remaining source risks and native requirements

| Scope | Current proof | Required remaining evidence / disposition |
|---|---|---|
| G4 Windows | Historical revised server-exit run passed | NEEDS_NATIVE_VALIDATION at new source; original collector Ctrl+C remains separate |
| G5 Windows | Offline terminal input/output + wrapper contracts | NEEDS_NATIVE_VALIDATION: one real ConPTY client, two rounds, Ctrl+C survival, /bye exit, headed live/fold/finished, cleanup |
| macOS/Linux Ollama | CI fixtures/terminal contracts only | NEEDS_NATIVE_VALIDATION: existing local model, PTY, provider/native observation and finalization |
| G6 portable Python | Hosted three-OS OS-only checkpoint and prior Windows run | Not provider semantics; current exact-head artifacts require review |
| Linux strace | CI record/run smoke with network disabled | Full process/file/network + Browser journey NOT proved by smoke; retain required gap |
| Cursor launcher | CI command/shim contracts | Actual installed arbitrary-path/desktop handoff remains NEEDS_NATIVE_VALIDATION; do not take over user GUI |
| Codex/Claude/AGY/OpenCode | Provider-shaped fixture/archive/hook contracts | Proves parsing given supplied evidence, not native hooks/plugin emission; no paid live tests authorized |
| AGY 5+3 children | Constructed/replayed ownership and history coverage | Current real provider wire/ingestion/manual validation remains distinct |
| PID reuse | Creation-time contradiction/future-candidate regressions; owned sentinel tests | NOT_DETERMINISTICALLY_EXERCISED for actual OS PID recycling; no fork storm or fabricated native PASS |
| G7 | Not started | Exact-head artifacts, secrets scan and human review AFTER required native gates |

No required capability has been waived. Ledger descriptions do not precisely close
every provider-native release cell; unresolved cells remain release-blocking rather
than being silently reclassified as optional. Portable file notifications are not
syscall reads; macOS sampling permissions/FSEvents limits remain explicit.

Open defects requiring further source hardening/review:

1. G4 final comparison previously accepted substrings. This follow-up now compares
   the complete normalized assistant output and rejects placeholders and open
   thinking blocks. The two original negative probes now fail correctly. Thinking
   framing follows https://raw.githubusercontent.com/ollama/ollama/main/cmd/cmd.go
   (`Thinking...` / `...done thinking.` complete lines); unknown CLI formats must
   fail closed pending installed-version native validation. Red: 1 failed/12 passed;
   green G4/G5 targeted selection: 28 passed. No exact model-answer requirement was
   substituted for capture fidelity; whitespace normalization permits terminal wrapping.
2. Windows ConPTY label is not itself backend proof: pywinpty backend selection
   can depend on its environment. Corrected in this checkpoint by explicitly
   passing the nonempty string `"0"` (pywinpty treats integer zero as falsy), plus
   required cross-platform isatty assertion. A native dev-CI test deliberately
   sets PYWINPTY_BACKEND=1 yet requires explicit ConPTY selection on Windows and
   unaffected real PTY selection on POSIX, both with actual TTY/echo.
   Both terminal subprocess tests passed locally; no provider was executed.
3. G4 independent-client output remains file-only; interactive tee does not fix G4.
4. Browser `pageerror` does not capture all `console.error` messages.
5. G4/G5 Ctrl+C/crash report persistence and reader-resource cleanup need review.
6. Temporary interactive/public-module rebinding adds another shim; do not perform
   broad consolidation while real journeys remain unaccepted.

Full Browser selection after NEW-007: 63 passed, 1038 deselected, 100.12 s, no
selected skips. JUnit: `.execweave-acceptance/hardening-viewer.xml`. ConPTY isatty/
environment assertions were added afterwards and tested separately as described
above; do not attribute those extra assertions to this earlier 63-test run.

Exact f2d6a43 PR workflow checkpoint, all SUCCESS: CI 33988876537;
Viewer 33988876542; Integrity 33988876561; Windows Launcher 33988876550;
Provider Contract 33988876563. This is not green evidence for subsequent commits.

Exact aa861a2 PR workflow checkpoint, all SUCCESS: CI 33989220786;
Viewer 33989220800; Integrity 33989220791; Windows Launcher 33989220785;
Provider Contract 33989220799. NEW-007 is committed separately as 32ccec5.

Exact 32ccec5 PR workflow checkpoint, all SUCCESS: CI 33989543984;
Viewer 33989543951; Integrity 33989543962; Windows Launcher 33989543959;
Provider Contract 33989544019. This includes the relative-output CLI regression.

Final local source/offline suite (including explicit ConPTY selection, TTY and
NEW-007): **1100 passed, 2 skipped**, 157.71 s. Both skips remain POSIX launcher
and Linux strace on Windows. JUnit: `.execweave-acceptance/hardening-final-offline.xml`.
Full repository Ruff and diff whitespace checks passed. These are local checked-tree
results, not a claim that a not-yet-created final commit already passed Actions.

This is a bounded source-hardening checkpoint, not REPO_SIDE_WORK_COMPLETE=YES:
the remaining G4 comparison/display, complete console capture, crash persistence
and terminal long-line fidelity gaps above are still source work. Do not relabel
all remaining work as native-only. G6 native matrix and deliberate PID reuse remain
separately unaccepted. No model or real provider was launched in this turn.

## Commands to return to the original Windows reviewer (DO NOT run in this turn)

First fetch/pull fast-forward and record clean HEAD; do not substitute a historical
SHA. Use existing binaries/model only. The following PATH changes affect only the
reviewer's shell, not persistent configuration. Confirm these paths still exist.

```powershell
$env:PATH = "$PWD\.execweave-acceptance\venv\Scripts;$env:LOCALAPPDATA\Programs\Ollama;$env:PATH"
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.execweave-acceptance\browsers"
$env:PYTHONIOENCODING = 'utf-8'
python scripts/ollama_visible_acceptance.py --model deepseek-r1:1.5b --timeout 45 --require ollama --output-dir .execweave-acceptance/native-review/g4
python scripts/ollama_interactive_acceptance.py --model deepseek-r1:1.5b --timeout 45 --require ollama --output-dir .execweave-acceptance/native-review/g5
```

Review both summary.json/report.html and actual terminal transcript/screenshots;
inspect finalized events.jsonl, semantic.jsonl, events.semantic.jsonl, graph.json,
viewer.html. Verify cleanup and unrelated-process survival. The G4 command tests
wrapped-server exit on Windows, not collector-terminal Ctrl+C. That original
journey requires a separately owned terminal-A validation and must not be marked
PASS by either command above. Missing binary/model/browser is unavailable and
`--require ollama` must fail overall. Never download a model automatically.

G0/G1/G2/G3 retain their explicitly historical/scoped ledger status; G4/G5/G6 remain
IN_PROGRESS, G7 NOT_STARTED. READY_FOR_HUMAN_MERGE_DECISION=NO.

## Integrity correction after bba6bf7

Exact bba6bf7 Integrity run 33992274452/job 101376498335 failed. Raw job log was
retrieved and independently reproduced: `_assert_no_new_skip_or_xfail` rejected
the new non-Windows skip in the ConPTY environment test. The guard is unchanged.
The test now executes the actual host backend on both branches: ConPTY with explicit
selection on Windows, real PTY on POSIX. It never changes os.name, returns early,
or treats a platform skip as a transport PASS. Existing test identity and Windows
assertions are preserved, with POSIX TTY/echo assertions added. Local Windows
targeted result: 1 passed; Ruff PASS. Fresh CI is still required for the correction.
