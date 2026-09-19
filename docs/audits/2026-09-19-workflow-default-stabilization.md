# Stabilize the default graph before enabling automatic workflow filtering

Baseline: `875542dba685525f1078ce83e46d4defd5b1a549`, PR #110.

## Scope

I am pausing automatic workflow filtering. The default view now retains the
existing full display projection, including runtime nodes and unresolved
attribution evidence. Workflow overview remains available through the visible
Graph view selector as an explicit, reversible choice. Returning to Default
restores the existing display inventory. Raw events and graph data are unchanged.

This is a small compatibility repair, not the completed workflow-first design.
It does not claim to separate the canonical graph from every presentation scope.
Automatic workflow-first behavior remains deferred until that integration can
preserve existing runtime, selection, folding, routing and export contracts.
There is no test-environment detection or special behavior for test fixtures.

## Reproduction and tests

On the baseline, two unchanged Chromium tests fail: the ambiguous tool-owner
projection loses its original tool edge, and the hidden-type/model bridge loses
its unresolved connection. After this production change, the same two tests pass
without modification. Both are synthetic component interactions in the shipped
Dashboard, not fresh provider recordings or native HTTP acceptance.

`tests/test_layout_pipeline_geometry_e2e.py` is restored byte-for-byte to main:
blob `58b66ee1dc5f9cbebd6c3a1d93e3d20294fb5111`. The temporary full-view setup
change is removed. No assertion or policy gate is weakened, and no new test-change
allowance is introduced.

The workflow tests added by this PR now select Workflow overview explicitly
before checking its filtering behavior. Two additional cases verify that
returning to Default restores the same display graph, and that automatic mode
preserves every published node and edge even with multiple same-named agents.
The focused run reports 68 passed and one native-download case deselected
locally. The unchanged geometry matrix reports 28 passed and one failure:
`test_final_svg_geometry_matrix[dark-many-files]` observes a Fit-camera scale
change across Arrange (0.49768874049186707 to 0.4958469569683075). This remaining
camera-timing issue is not fixed by this batch and is the next isolated item.
The failing result is retained; no timeout or assertion was relaxed.

The two-test before/after run overlaps the focused run. None of these results
substitutes for current-head three-OS CI or native HTTP/offline acceptance.

## Impact and rollback

Only the workflow module, its new tests, the original geometry-test restoration,
and this record change. Content health, sharing, capture, authentication,
serialization, dependencies, workflows and package versions are untouched.

The original geometry-test restoration removes the existing-test modification
that triggered the stage-integrity failure. Current-head CI must still run; this
record does not claim that every prior browser failure is resolved.

Reverting the default policy reintroduces automatic filtering and its known
regressions. Keep the original geometry test intact. The PR stays draft with no
merge, main update, tag or release.
