# Stop checkpoint: source/offline work, then return for native review

The user requested a bounded checkpoint, push and handoff. Do not infer completion.
Branch: `test/live-dashboard-acceptance`; PR #51 must remain Draft/validation-only.
Main baseline: `a098eeb81f641b6e3fb1d65cc1905f46aa8eae30`.
Fetch and fast-forward before work. Never reset/rebase/force/merge/tag/release.
Before every Git write fetch again and inspect concurrent remote changes.
Commit author AND committer: GWW <49675917+Irish-kw@users.noreply.github.com>.

## Changes preserved at this checkpoint

- f2d6a43: POSIX terminal Ctrl+C is an input byte, not an external killpg signal.
- aa861a2: redacted interactive terminal stdout tee with bounded buffering.
- 32ccec5: formal offline runner resolves relative artifact paths before file URI use.
- bba6bf7: explicit ConPTY selection, Windows e2e pywinpty dependency, actual TTY.
- ee5bbe3: platform-native terminal contract on both OS families, without new skips.
- 1c3cb1e: full client Final equality; reject truncation and thinking-only answers.
- 38397a1: G4 client stdout/stderr and ExecWeave status are displayed while running,
  redacted; a harmless real Python child proves visibility before process exit.
- This checkpoint preserves BrowserDiagnostics and its actual Chromium negative
  contract: console.error and unhandled Promise rejection, redacted log, screenshot.
  **The helper is NOT integrated into formal runners yet.** This is preparatory
  coverage, not evidence that formal JS-console gates have been hardened.

## Evidence and SHA discipline

Exact 1c3cb1e: five PR families SUCCESS (CI 33992814906; Viewer 33992814964;
Integrity 33992814949; Windows Launcher 33992814936; Provider Contract 33992814968).
These results do NOT apply to subsequent commits.

Local checkpoint targeted selection: 26 passed in 7.49 seconds; full Ruff PASS.
Command: pytest tests/test_acceptance_visible_pipe.py
tests/test_ollama_visible_acceptance.py tests/test_ollama_interactive_acceptance.py
tests/test_acceptance_browser_diagnostics_e2e.py -q, with EXECWEAVE_E2E_REQUIRED=1.
Older full-suite evidence is in acceptance_hardening_20260906.md; do not attribute
1100 passed or the older 63-browser run to this latest checkpoint.
Full local required browser selection at this checkpoint: **64 passed, 1041
deselected, zero selected skips**, 98.22 seconds. Command: pytest -m viewer_e2e -q
--junitxml=.execweave-acceptance/handoff-viewer.xml with EXECWEAVE_E2E_REQUIRED=1
and the existing acceptance Chromium cache. No real provider was run.
Fetch latest Actions for the actual remote HEAD. Any pending checks are pending,
not inherited green. Inspect logs and preserve failures without weakening gates.

## Remaining source/offline work (do not call repo-side complete)

1. Integrate BrowserDiagnostics into formal G4/G5/offline/native-Python runners:
   console.error AND pageerror must affect results; preserve browser-console.log
   and FAILURE.png on failure. Add regression for real runner propagation, not
   only the helper. Ensure failure artifact directories exist before screenshots.
2. Audit KeyboardInterrupt/crash finalization and report persistence, reader-thread
   joins and failure reporting. Cleanup must retain PID + create_time identity and
   preserve unrelated processes. Test with bounded harmless children, no provider.
3. TerminalTranscript currently omits lines exceeding its 64 KiB safe-redaction
   buffer in both stdout and artifact. This is an explicit fidelity gap; solve
   without exposing credentials or claiming raw full fidelity for omitted text.
4. Recheck G4 network ownership evidence: node presence alone is weaker than an
   endpoint edge associated with the owned observed process.
5. Run full relevant offline/browser tests and exact-head five workflows after
   fixes; keep each independent defect and its evidence in a clear commit.

Do not undertake large shim/renderer refactors during this checkpoint. The wrapper
debt remains documented. Keep memory <=12 MiB and crossing threshold 73 unchanged.

## Gates and native boundary

G0/G1/G2/G3 retain historical/scoped PASS, not a new full-product certification.
G4=IN_PROGRESS; G5=IN_PROGRESS; G6=IN_PROGRESS; G7=NOT_STARTED.
REPO_SIDE_WORK_COMPLETE=NO. READY_FOR_HUMAN_MERGE_DECISION=NO.

The receiving agent is source/offline/CI-only. DO NOT run real Ollama, Codex,
Claude, Antigravity or other live providers; do not download models or alter auth.
Mark the following NEEDS_NATIVE_VALIDATION and return to the original Windows
agent for review/execution after source work is complete:

- G4: owned fresh Ollama server, independent real client, existing model, headed
  browser, prompt/final ownership, Process/Network, live/finished parity, cleanup.
- Original Terminal A collector Ctrl+C finalization. The revised Windows runner
  exits the owned server; that is not proof of collector-terminal Ctrl+C.
- G5: real interactive ConPTY/PTY, two marker-bound rounds, Ctrl+C leaves client
  alive, /bye exits, history fold persistence, finished parity, owned cleanup.
- G6: remaining provider-native OS matrix. Three-OS plain-Python Process/File/
  Network evidence does not certify all native provider paths. PID reuse stress
  remains NOT_DETERMINISTICALLY_EXERCISED, not an implied PASS.
- G7 only after required native gates: final exact-head Actions, artifact/visual
  review, repository secret/artifact scan; no merge/tag/release.

Original Windows reviewer commands (NOT for the receiving agent): first fetch,
pull --ff-only and record clean HEAD; activate the existing acceptance venv and
browser cache, verify the existing model without downloading it, then run:

```powershell
python scripts/ollama_visible_acceptance.py --model deepseek-r1:1.5b --timeout 45 --require ollama --output-dir .execweave-acceptance/native-review/g4
python scripts/ollama_interactive_acceptance.py --model deepseek-r1:1.5b --timeout 45 --require ollama --output-dir .execweave-acceptance/native-review/g5
```

Read summaries, screenshots, transcripts and finished viewer; verify no owned
process remainders. Missing prerequisites cannot become required PASS. See
acceptance_hardening_20260906.md for shell setup and historical native evidence.
