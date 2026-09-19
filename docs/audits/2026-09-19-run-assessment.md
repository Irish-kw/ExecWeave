# Run assessment: execution, task verification, and content metadata

Baseline: `746e793deedef0350e5c409d9eb6fcb5c4df923f`, PR #110.
Scope: a first visible W01/W07 slice, not completion of either work package.

## User-facing change

I added a shared **Run assessment** panel with three independent axes:

- **Execution** reports consistent recorded terminal-event metadata. It retains the source event and exit code. Collector failure takes precedence over interruption, which takes precedence over ordinary exit status. A numeric 130 alone does not establish interruption. Missing provenance, malformed booleans, and contradictory metadata remain unknown.
- **Task verification** stays explicitly unverified. Native `TASK_COMPLETED` and `TASK_FAILED` reports are counted separately on observed task nodes, and a task with both reports remains visible in both counts. Neither a completion report, exit code zero, a termination token, nor text claiming that tests passed is treated as independent verification.
- **Recorded content** distinguishes invalid references, source-incomplete records, unknown source completeness, and explicitly opaque/redacted representations. Counts refer to declared graph metadata, not verified readable bodies, successful invocations, or end-to-end recall.

The scope disclosure includes bounded task/terminal provenance and explicitly says that **archive verification is not checked by this panel**. No filesystem lookup or extra network request is performed. The existing content reader still verifies individual bodies when they are opened. The durable finalization verifier is unchanged; its complete report is not yet surfaced through this panel. A graph with no content records does not become a capture failure, capture-disabled verdict, or complete-archive claim.

## Data and presentation boundaries

`run_assessment.py` reads only graph nodes, graph edges, named expansion containers, and the existing session summary. It does not interpret provider bodies, path-like text, or arbitrary nested validation objects. Inferred/view-only task reports are excluded. Repeated reports are counted by distinct task ID, not edge count; the same content hash can still describe multiple content records. Conflicting node identities are withheld and counted explicitly.

Inspection is bounded to 100,000 records. Budget exhaustion, malformed records, ambiguous IDs, compact graphs, and previously projected inputs are marked as partial inventories. The diagnostic provenance list is capped at 20 entries. Byte existence, byte hashes, ownership completeness, message delivery, and source recall are not inferred from this inventory.

The standard projection computes the assessment before task/content folding. The Live envelopes carry it through snapshot, delta, noop, resync, and terminal delivery. Envelope assessment work is cached per update sequence/finished state. The existing projection path still calculates its own presentation metadata; this change is not a claim that all large-run CPU/memory budgets are solved. Compact payloads preserve an assessment when supplied, instead of silently turning hidden content into a zero count.

The shared reader validates the session/source scope before displaying an assessment. Switching runs clears prior results; stale metadata cannot reuse an earlier success. Updates preserve the scope disclosure and do not replace agent/history DOM. The insertion point preserves the existing first/second inspector-section CSS contract: prepending another matching section would have hidden the new panel and exposed the retired activity section. Full-page visibility checks cover this integration risk, not only DOM presence.

## Verification

Source material: exact-head package artifact `10554856266`, ZIP SHA-256 `126693ffaf9468eaf58251b54386a561485f5e0094ad05314e5ecc0a1dd71f80`. Its source marker is PR merge ref `e1144a118768c4064c149ba8fc9cebe17a897265`. All three pre-edit production files were checked byte-for-byte against the corresponding remote Git blobs.

```sh
PYTHONPATH=src EXECWEAVE_E2E_CHROMIUM=/usr/bin/chromium python -m pytest -q tests/test_run_assessment.py
ruff check src/execweave/run_assessment.py src/execweave/viewer_run_assessment.py \
  src/execweave/_dashboard_shell_base.py src/execweave/viewer_projection.py \
  src/execweave/live_core.py tests/test_run_assessment.py
python -m compileall -q src/execweave
```

The targeted run reports **65 passed**, with no skipped or deselected cases. It includes actual Chromium interactions; complete Live/Static/projected-static assembly and JavaScript syntax; visible-panel and dark/light warning tests; run isolation; literal rendering; retained history expansion; exact envelope-kind checks; and partial-inventory boundaries.

Two tests launch real child processes through the portable collector, with exit codes 0 and 7. Another launches the real Live workflow with exit code 3, then reads its actual graph, viewer, and finalization outputs. It verifies that a failed execution and unverified task coexist with a complete exported archive, without putting the derived assessment into the raw graph. A real HTTP-server test exercises the existing `/live.json` handler: missing/wrong tokens receive 401, a valid token receives the scoped assessment, and caching remains `no-store`.

Local runtime is Linux/Python 3.13.5 with Chromium. These checks do not replace the required Python 3.10/3.12 Windows/macOS/Linux matrix, the entire legacy suite, fresh model-provider recordings, or independent user acceptance. Browser interactions use local documents; the backend HTTP test is not browser-over-HTTP acceptance. No paid model was called.

## Change impact and rollback

| Change | Files | Preservation and regression boundary |
|---|---|---|
| Conservative metadata reducer | `run_assessment.py` | No file reads, provider-body parsing, task-success inference, or raw mutation. Unknown/partial remains explicit. |
| Shared panel | `viewer_run_assessment.py`, `_dashboard_shell_base.py` | Existing inspector CSS/DOM, history expansion, theme, literal rendering, singleton assembly, and cross-run isolation. |
| Pre-fold assessment | `viewer_projection.py` | Raw nodes/edges remain unchanged; graph geometry and ownership policy are unchanged. |
| Live envelopes | `live_core.py` | All envelope kinds, terminal invalidation, auth handler, compact payload retention, and no new polling. |

No recorder, original event, captured content hash, finalization policy, existing test file, workflow, dependency, package version, or release metadata is changed. The panel and metadata publication can be reverted together without changing recorded evidence. Do not replace unknown states with success to resolve a compatibility regression.

## Outstanding work

W01 still needs an explicit independent task-validation contract and the remaining execution/cleanup/error cases. W07 still needs occurrence-level, versioned denominators across conversation/model/tool sources, not just declared graph content. Finalization health and final synchronization status still require a unified Live/Finished/Offline presentation. The full 0.8.34 plan, large-run acceptance, and fresh-provider verification remain open.
