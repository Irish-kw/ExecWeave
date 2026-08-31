# ExecWeave v0.8.3 Dashboard Audit Matrix

Baseline: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`.

Legend:

- **E2E** — existing Chromium/Playwright behavioral coverage was inspected.
- **SOURCE** — implementation path was traced, but this audit environment did not independently launch Chromium.
- **PR25** — behavior is actively being changed by PR #25; final release-candidate verification must run after that branch stabilizes.
- **GAP** — no adequate behavioral check was found or executed.

| Surface | Graph | Conversation | Focus | Fold | Search | Filter | Zoom | Fit | Follow latest | Inspector | Replay | Export |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Live | SOURCE / PR25 | E2E | PR25 | E2E | SOURCE | SOURCE | SOURCE | PR25 | PR25 | E2E/SOURCE | SOURCE | SOURCE |
| Finished in same live page | SOURCE | SOURCE | PR25 | SOURCE | SOURCE | SOURCE | SOURCE | PR25 | PR25 | SOURCE | SOURCE | SOURCE |
| standalone `viewer.html` | SOURCE / PR25 | E2E | PR25 | E2E | SOURCE | SOURCE | SOURCE | PR25 | n/a static | E2E/SOURCE | SOURCE | SOURCE |

## Renderer parity

### Live -> finished

`live_view.py::_restore_live_safety_contracts()` removes the legacy `Open final graph` action, `/final` fetch, `document.open()`, `document.write()` and renderer replacement. `onFinished()` only exposes finished actions. The old strings remain in Python as a patch target, but they are removed from the emitted `LIVE_HTML`.

**Finding:** the feared `/final`/`document.write()` transition is **NOT A BUG** on the audited baseline.

### standalone viewer

`viewer.py` still contains an older standalone template, but the product path goes through `viewer_projection.py`, which overrides the base renderer and calls `dashboard_shell.render_static_dashboard_html()`. `dashboard_shell.py` builds `DASHBOARD_HTML` from the same `LIVE_HTML` plus the dashboard injectors and substitutes only the startup data source for static mode.

**Finding:** the presence of `_VIEWER_TEMPLATE` in `viewer.py` is not evidence that shipped `viewer.html` uses a second product renderer. The actual projection path uses the unified dashboard. **NOT A BUG.**

## Conversation round folding

`tests/test_dashboard_round_fold_state_e2e.py` already uses Playwright/Chromium and exercises both live HTTP and static `viewer.html`:

- historical round starts folded;
- one click leaves it open;
- two polling intervals do not close it;
- identical conversation payload does not rebuild the inspector;
- changed payload preserves the user's open choice;
- a newly discovered historical round defaults closed;
- explicit close survives polling;
- switching to another agent and back preserves that agent's fold state.

This directly dismisses the earlier suspicion that fold-state persistence had only source-string tests. The release candidate still needs the same test suite rerun after PR #25 because #25 changes graph interaction/layout code.

## Agent labels

`tests/test_agent_node_labels.py` contains a behavioral Node execution of the shipped projection and verifies namespaced topology paths (`agent_path`, `child_agent_path`, `root_agent_path`) and provider nicknames are used instead of timestamp-ID prefixes. A simplistic claim that all child labels are always derived from the first eight ID characters is therefore stale.

The real Antigravity `/root` symptom remains upstream of this label machinery: if several conversation agents are independently projected as roots, the dashboard is faithfully displaying the topology it received. Layout/label changes must not be used to hide that identity defect.

## Focus / layout / routing

PR #25 is actively modifying these areas. This audit intentionally does not copy or edit that branch. Final v0.8.3 release verification must be executed against the eventual merge candidate and must cover:

1. Clear focus button, empty-canvas click and Escape.
2. Focus while an 800 ms poll arrives.
3. Focused node removed/folded by a new projection.
4. Manual zoom persistence while polling.
5. Fit mode and follow-latest state while polling.
6. Switching agents while focused.
7. Node/edge position determinism on an unchanged payload.
8. Small (~10), medium (~50) and large (100–300+) graphs.
9. Agent-heavy, process-heavy, file-heavy, network-heavy, tool-heavy and mixed graphs.
10. Crossings, node overlaps, edge/node intersections, graph bounding box and movement between polls.

## Search / filter / replay / export

The controls exist in the shared dashboard source, but this audit environment did not independently execute browser combinations. Before release, Chromium tests should compose at least:

- Unicode search + type filter;
- relation filter + focus + clear focus;
- search clear while follow-latest is active;
- replay while a node is focused;
- export after a live run reaches FINISHED;
- long Windows path, IPv6 endpoint and long tool namespace in search and inspector.

These are coverage gaps, not confirmed defects.

## Protective large-graph behavior

The legacy `viewer.py` protective limits remain relevant to the base standalone renderer, while the current product path uses the unified dashboard projection. The release candidate should verify that the active unified path has an explicit browser memory/DOM policy for 100–300+ nodes and that any protective mode cannot silently omit evidence without disclosure.
