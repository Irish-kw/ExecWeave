# Observed-history navigation and Codex retention

Baseline: `7184d34ed7307e18a72146c22e4a016ecce14f66`, PR #110.
Scope: part of W03. This is not completion of the 0.8.34 plan.

## Reader behavior

I added an on-demand **Browse observed history** entry to the existing agent inspector. The compact round summaries and their disclosure policy remain in place. The reader uses the published conversation index rather than fetching arbitrary files or reconstructing missing provider output.

- Select records by exact source ID and explicit projection-member IDs only. Matching names, paths, shared models, and parent/child proximity do not select another agent's history. Conflicting explicit native executions under one source ID are withheld with a visible explanation.
- Render 25 records per page and search the loaded normalized text and routing fields. Identical text at different occurrences remains separate. Long text is rendered lazily in 16,384-unit pages without splitting UTF-16 surrogate pairs.
- Pin an open snapshot when new records or same-length corrections arrive. Display an update notice; change the open history only on explicit refresh. Search, record page, and expansion state are retained per run and agent in memory, not persisted across browser reloads.
- Close and clear displayed history when switching agents, changing runs, closing the dialog, or leaving the page. Do not write message bodies or search strings to browser storage.
- Render text literally, not as HTML. Encrypted records do not expose or search a supplied ciphertext body as plaintext. Empty, missing, truncated, routing-only, and conflicting-identity states have distinct explanations.
- Label exact assistant termination strings only as **text matches**, never verified protocol transitions or task success. User inputs, quoted strings, tool outputs, injected context, and explicitly truncated text are excluded from this hint. Original strings remain available; an earlier response is not promoted to a final answer.

Search covers the published normalized text, not every full archived payload. Existing per-message text caps still apply. The existing **Recorded source content** reader remains the path to captured bodies. Other providers' upstream preview caps are not removed by this change. None of these views establishes hidden reasoning, delivery, consumption, or task verification.

## Codex publication and identity

The Dashboard publication path opts into retaining normalized rollout records before merging; the general parser's default 80-record preview remains backward compatible. The post-merge 80-record deletion is removed as well. Existing source truncation flags remain true rather than being presented as repaired. Child inherited-history cutoffs and root-user-prompt exclusion still apply, with the count recomputed after filtering.

A negative regression reproduced a separate problem: the Codex reconciliation pass could rejoin independent roots sharing a derived `codex:root` alias after the core publication had separated them. The reconciliation now checks the same execution namespace as publication before its source-ID shortcut and rejects derived aliases as fallback join keys. A positive case retains native-thread aliases within the same execution scope.

## Change impact and rollback

| Change | Affected paths | Required preservation |
|---|---|---|
| On-demand history UI | `viewer_history_browser.py`, `viewer_agent_panel.py` | Existing round summaries, fold handling, lifecycle seams, Live/Static shell, literal rendering, selection isolation |
| Dashboard rollout retention | `codex_conversation.py`, `conversation_preview_codex.py`, `conversation_records.py` | Default preview callers, child cutoffs, provider visibility flags, occurrence identity |
| Reconciliation scope | `conversation_records_codex.py` | Native identity namespace, non-Codex paths, same-scope native alias positive cases |

No collector, raw event, content hash, layout, release metadata, or existing test file is changed. The history UI may be reverted independently of the retention/identity fixes. Do not restore cross-execution alias joins to resolve a UI regression. The increased normalized-history payload needs the outstanding large-run and three-OS checks; bounded dialog DOM is not a claim that every Dashboard or server-memory budget has passed.

## Local verification

The source came from exact-head package artifact `10553900613`, downloaded from the `7184d34` Wheel Install Smoke run. Its ZIP SHA-256 was verified as `39dbdc9c89550c79e9bf9f289aeac3abb2ee8862256ee6b7875db20fa90a577e`. All five pre-edit production files were checked against their remote Git blob IDs. The package contains the full production modules, not the complete repository test suite.

```sh
PYTHONPATH=src EXECWEAVE_E2E_CHROMIUM=/usr/bin/chromium python -m pytest -q \
  tests/test_observed_history.py \
  tests/test_codex_preserved_history.py \
  tests/test_history_publication_http.py
```

Result: **63 passed**, with no skipped or deselected cases in this targeted run. Python compilation and Ruff for all changed modules/new tests passed. The tests exercise actual Chromium component interactions and assembled Live/Static/projected-static JavaScript syntax. Sixteen provider/framework labels use synthetic records; they are cross-label UI contracts, not sixteen fresh provider recordings. A generated rollout also traverses the real Codex parser, publication merge, and assembled static Dashboard before locating its middle record.

Three HTTP tests use the real Live handler and a local server: absent/wrong tokens receive 401, and the valid token returns all 210 published records with no-store caching. Browser navigation to that server was separately attempted and rejected by the environment with `ERR_BLOCKED_BY_ADMINISTRATOR`. Therefore native server authentication is tested locally, but browser-over-HTTP acceptance is not. No transport or cryptographic substitute is counted as an end-to-end pass.

Local runtime: Linux, Python 3.13.5, Chromium. Required Python 3.10/3.12, Windows/macOS, installed-wheel, full legacy-suite, fresh-provider, and independent user-journey results must be checked on the new commit. Prior-head passes are not substitutes. W01 task/result health separation, W05 handoffs, W06 workflow layout, W07 itemized health, and remaining W08 closure work are still outstanding.
