# Runtime navigation controls and recorded-response boundaries

Baseline: `b22f0e1e6cfa9cbfe7f3ef3aa232fe1cb1a8254c`, PR #110.

## Failure

The baseline Ubuntu/Python 3.12 JUnit report from Actions artifact 10576548528
contains **3 failures, 2,252 passes and 5 skips**. They affect the relative-output
offline runner, propagation of browser console diagnostics, and relay prompt /
final-response acceptance. The console-diagnostic case fails before it reaches
its intended check because the same recorded-response boundary times out.

The runtime-navigation change appended its action to `#details` after the final
answer. An independently rendered Ollama-shaped response reproduced the tail:

```
FINAL RESPONSE
EXACT FINAL RESPONSE
Runtime evidence for selection
```

The action is not recorded agent output. I moved the selection toolbar beside
`#details`, still within the inspector, rather than weakening response assertions.
The original three acceptance tests are unchanged.

The new Escape regression also exposed a canvas-selection side effect: closing
the runtime dialog propagated Escape to the global canvas handler, removed the
selected-node action, and lost return focus. The dialog now stops only Escape
propagation and retains native modal cancellation. Closing it returns focus to
the selected-source action without clearing the underlying selection.

## Scope and acceptance

This changes only the runtime-navigation module and adds three browser
regressions: exact final-answer boundaries, redraw behavior / return focus, and
re-binding to another selected source. It does not change raw capture, graph
identity, layout, provider parsing, dependencies, workflows, or versions.

The existing 16 runtime-navigation tests and the new three tests pass locally
with the shipped Dashboard, real Chromium, and labeled synthetic records.
These are component interactions using `set_content`, not native HTTP or
fresh-provider recordings. Native navigation remains a current-head CI gate;
local browser policy must not be bypassed or treated as a pass.

The module-level fix can be reverted independently. Doing so restores the
known answer-text contamination and Escape-selection regression. Keep this
record separate from the subsequent content-health and sharing work.
