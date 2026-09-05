# PR / regression archaeology

Baseline: a098eeb81f641b6e3fb1d65cc1905f46aa8eae30 (v0.8.11).

All 50 PRs obtained from GitHub; raw descriptions preserved in github_pr_inventory.json. All-state issues API yielded no non-PR issues. PR claims are leads, not evidence of current function. Changed test paths below come from merged first-parent diffs; closed/unmerged PRs are explicitly excluded from shipped-code claims.

| PR | Original issue / intent | Modified source area | Tests changed | Current evidence | Regression risk |
|---|---|---|---|---|---|
| [#50](https://github.com/Irish-kw/ExecWeave/pull/50) | Prepare v0.8.11 release | __init__.py | test_v069_dashboard_release.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#49](https://github.com/Irish-kw/ExecWeave/pull/49) | fix: capture Ollama serve clients and finalize live runs on Ctrl+C | auto_specialized.py, collector.py, strace_backend.py | test_ollama_serve_runtime_integration.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#48](https://github.com/Irish-kw/ExecWeave/pull/48) | Prepare v0.8.10 release | __init__.py | test_v069_dashboard_release.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#47](https://github.com/Irish-kw/ExecWeave/pull/47) | Fix Windows Cursor launch and Ollama serve conversation capture | auto_specialized.py, collector.py, command.py | test_cursor_ollama_session_lifecycle.py | Installed-Cursor synthetic shim test fails natively; real Ollama pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#46](https://github.com/Irish-kw/ExecWeave/pull/46) | Prepare v0.8.9 release | __init__.py | test_v069_dashboard_release.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#45](https://github.com/Irish-kw/ExecWeave/pull/45) | Use dagre edge routing points and post-layout ports | live_view_process_layout.py, live_view_readability.py | test_graph_edge_routing_e2e.py, test_process_tree_layout.py | Explicit Windows Browser tests expose 8 failures across #25 geometry modules; crossing count 89 >73. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#44](https://github.com/Irish-kw/ExecWeave/pull/44) | Fix provider history aggregation and dashboard evidence | antigravity_full_fidelity.py, antigravity_subagent_linkage.py, conversation_records_antigravity.py, graph.py (+5) | test_antigravity_field_run_regressions.py, test_antigravity_subagent_transcript_linkage.py, test_dashboard_information_architecture.py (+4) | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#43](https://github.com/Irish-kw/ExecWeave/pull/43) | Harden provider conversation and dashboard contracts | agent_bootstrap.py, agent_trace.py, antigravity_adapter_base.py, antigravity_full_fidelity.py (+29) | test_agent_bootstrap.py, test_agent_topology_evidence.py, test_agent_trace_viewer_visibility.py (+33) | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#42](https://github.com/Irish-kw/ExecWeave/pull/42) | fix: isolate provider dashboard policy; Codex child rounds | agy_preview_sanitize.py, antigravity_full_fidelity.py, antigravity_hook_cli.py, antigravity_subagent_linkage.py (+33) | test_agy_windows_wire_acceptance.py, test_antigravity_child_panel_policy.py, test_antigravity_child_transcript_tools.py (+17) | PR leaves real AGY 8-child case and first-frame overlap unaccepted. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#41](https://github.com/Irish-kw/ExecWeave/pull/41) | Integrate validated PR #40 dashboard interaction and tool aggregation | antigravity_adapter_base.py, antigravity_full_fidelity_base.py, live_view_markup.py, live_view_readability.py (+2) | None in merged first-parent diff | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#40](https://github.com/Irish-kw/ExecWeave/pull/40) | Fix Dashboard root identity, layout interaction, and tool-call aggregation | Docs / workflow / metadata | None in merged first-parent diff | Closed/unmerged; not assumed shipped. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#39](https://github.com/Irish-kw/ExecWeave/pull/39) | Fix Antigravity root promotion and reused child history | antigravity_subagent_linkage.py, conversation_records.py, viewer_agent_panel.py, viewer_dashboard_focus.py | test_antigravity_root_child_history_v2.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#38](https://github.com/Irish-kw/ExecWeave/pull/38) | Fix Ollama conversation capture and provider history fidelity | antigravity_full_fidelity_base.py, auto_specialized.py, collector.py, conversation_preview.py (+5) | test_provider_conversation_history_integrity.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#37](https://github.com/Irish-kw/ExecWeave/pull/37) | Fix Antigravity conversation identity/topology isolation | antigravity_full_fidelity.py, dashboard_shell.py, viewer_agent_panel.py, viewer_dashboard_focus.py | test_antigravity_multi_conversation_isolation.py, test_conversation_root_authority.py, test_viewer_child_authority.py | Two-round/eight-child preconstructed Browser fixture passes; does not prove capture. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#36](https://github.com/Irish-kw/ExecWeave/pull/36) | docs: reorganize the v0.8.3 README set | Docs / workflow / metadata | test_v069_dashboard_release.py | Metadata/policy only; not functional acceptance. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#35](https://github.com/Irish-kw/ExecWeave/pull/35) | docs: reorganize the v0.8.3 README set | Docs / workflow / metadata | None in merged first-parent diff | Closed/unmerged; not assumed shipped. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#34](https://github.com/Irish-kw/ExecWeave/pull/34) | chore: bump ExecWeave to 0.8.3 | __init__.py | test_v069_dashboard_release.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#33](https://github.com/Irish-kw/ExecWeave/pull/33) | fix: close v0.8.3 model identity gaps | anthropic.py, anthropic_full_fidelity.py, inference_gateway.py, openai_compatible.py (+1) | test_v083_release_gate_p2.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#32](https://github.com/Irish-kw/ExecWeave/pull/32) | fix: stabilize Antigravity cumulative conversation history | conversation_records.py, dashboard_shell.py | test_antigravity_history_replay.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#31](https://github.com/Irish-kw/ExecWeave/pull/31) | fix: align Antigravity conversation identity and topology | antigravity_adapter.py, conversation_archive.py | test_antigravity_identity_topology.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#30](https://github.com/Irish-kw/ExecWeave/pull/30) | fix: unify OpenCode session agent identity | opencode_adapter.py, opencode_full_fidelity.py | test_opencode_identity_unification.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#29](https://github.com/Irish-kw/ExecWeave/pull/29) | fix: scope inference identities by endpoint | inference_gateway.py, model_runtime.py | test_inference_endpoint_identity.py, test_model_runtime.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#28](https://github.com/Irish-kw/ExecWeave/pull/28) | fix: isolate cross-session conversation identity | conversation_records.py | test_conversation_identity_merge.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#27](https://github.com/Irish-kw/ExecWeave/pull/27) | fix: PR25 pre-merge hardening | Docs / workflow / metadata | test_pr25_premerge_hardening_contract.py | Metadata/policy only; not functional acceptance. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#26](https://github.com/Irish-kw/ExecWeave/pull/26) | audit: v0.8.3 system-wide provider/dashboard release gate | Docs / workflow / metadata | None in merged first-parent diff | Closed/unmerged; not assumed shipped. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#25](https://github.com/Irish-kw/ExecWeave/pull/25) | v0.8.3: graph ergonomics and routing | live_view.py, live_view_markup.py, live_view_readability.py, live_view_script_c.py (+3) | test_conversation_agent_focus.py, test_graph_clear_focus_e2e.py, test_graph_edge_routing_e2e.py (+5) | Explicit Windows Browser tests expose 8 failures across #25 geometry modules; crossing count 89 >73. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#24](https://github.com/Irish-kw/ExecWeave/pull/24) | ci: clean up fold-state repair allowance | Docs / workflow / metadata | None in merged first-parent diff | Metadata/policy only; not functional acceptance. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#23](https://github.com/Irish-kw/ExecWeave/pull/23) | test: remove fold-state live polling race | Docs / workflow / metadata | test_dashboard_round_fold_state_e2e.py | Metadata/policy only; not functional acceptance. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#22](https://github.com/Irish-kw/ExecWeave/pull/22) | Release metadata for v0.8.2 | __init__.py | test_v069_dashboard_release.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#21](https://github.com/Irish-kw/ExecWeave/pull/21) | fix: v0.8.2 dashboard readability regressions | live_view.py, live_view_readability.py, viewer_agent_panel.py | test_dashboard_readability_e2e.py, test_dashboard_round_fold_state_e2e.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#20](https://github.com/Irish-kw/ExecWeave/pull/20) | fix: v0.8.2 dashboard readability regressions | Docs / workflow / metadata | None in merged first-parent diff | Closed/unmerged; not assumed shipped. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#19](https://github.com/Irish-kw/ExecWeave/pull/19) | Release metadata for v0.8.1 | __init__.py | test_v069_dashboard_release.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#18](https://github.com/Irish-kw/ExecWeave/pull/18) | The fold budget is a run setting, not a constant | cli.py, dashboard_shell.py, live_core.py, top_cli.py (+2) | test_fold_budget_setting.py, test_viewer_agent_isolation_e2e.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#17](https://github.com/Irish-kw/ExecWeave/pull/17) | A release branch may move the version, a stage still may not | Docs / workflow / metadata | test_release_stage_integrity_version_guard.py | Metadata/policy only; not functional acceptance. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#16](https://github.com/Irish-kw/ExecWeave/pull/16) | Release metadata for v0.8.0 | __init__.py | test_v069_dashboard_release.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#15](https://github.com/Irish-kw/ExecWeave/pull/15) | Non-agent nodes describe themselves, and crowded types fold | viewer_agent_panel.py, viewer_dashboard_clean.py | test_conversation_agent_focus.py, test_dashboard_information_architecture.py, test_dashboard_simplification.py (+1) | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#14](https://github.com/Irish-kw/ExecWeave/pull/14) | v0.8.2: capture file contents and show what changed | Docs / workflow / metadata | None in merged first-parent diff | Closed/unmerged; not assumed shipped. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#13](https://github.com/Irish-kw/ExecWeave/pull/13) | v0.8.0 (1/2): per-round agent panels and the misclassified response | _conversation_records_core.py, viewer_agent_panel.py | test_agent_said_panel.py, test_agent_topology_evidence.py, test_conversation_agent_focus.py (+4) | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#12](https://github.com/Irish-kw/ExecWeave/pull/12) | v0.7.9: unify dashboard presentation | codex_conversation.py, dashboard_shell.py, live.py, live_core.py (+9) | test_agent_message_viewer.py, test_agent_node_labels.py, test_agent_said_panel.py (+26) | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#11](https://github.com/Irish-kw/ExecWeave/pull/11) | feat: add provider capability and evidence matrix | evidence_availability.py, provider_capability.py | test_provider_capability.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#10](https://github.com/Irish-kw/ExecWeave/pull/10) | fix: scope the conversation panel to the selected agent | _conversation_records_core.py, live_view_script_a.py, viewer.py, viewer_conversation_tree.py | test_conversation_agent_focus.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#9](https://github.com/Irish-kw/ExecWeave/pull/9) | fix: scope the conversation panel to the selected agent | Docs / workflow / metadata | None in merged first-parent diff | Closed/unmerged; not assumed shipped. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#8](https://github.com/Irish-kw/ExecWeave/pull/8) | fix: reconcile duplicate Codex message observations | _conversation_records_core.py, conversation_message_identity.py, conversation_records.py | test_conversation_message_observation_dedupe.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#7](https://github.com/Irish-kw/ExecWeave/pull/7) | fix: keep Codex child native identity local | conversation_preview.py | test_codex_routing_native_identity.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#6](https://github.com/Irish-kw/ExecWeave/pull/6) | fix: keep Codex transcript archive independent from content capture | codex_hook_cli.py | None in merged first-parent diff | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#5](https://github.com/Irish-kw/ExecWeave/pull/5) | fix: derive agent topology from provider evidence, not naming conventions | agent_topology.py, codex_conversation.py, conversation_preview.py, conversation_records.py | test_conversation_identity_merge.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#4](https://github.com/Irish-kw/ExecWeave/pull/4) | fix: materialize agent-local Codex subagent conversations | codex_conversation.py, conversation_archive.py, conversation_preview.py, conversation_records.py | test_codex_real_multi_agent_conversation.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#3](https://github.com/Irish-kw/ExecWeave/pull/3) | fix: simplify dashboard information architecture | live.py, viewer_conversation_tree.py, viewer_dashboard_clean.py, viewer_dashboard_focus.py (+2) | test_dashboard_information_architecture.py, test_dashboard_simplification.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#2](https://github.com/Irish-kw/ExecWeave/pull/2) | fix: simplify Codex conversation dashboard | codex_conversation.py, codex_hook_cli.py, conversation_archive.py, conversation_records.py (+4) | test_codex_archive_full_fidelity.py, test_dashboard_simplification.py | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |
| [#1](https://github.com/Irish-kw/ExecWeave/pull/1) | feat: full multi-agent execution trace | agent_trace.py, antigravity_adapter.py, antigravity_adapter_base.py, antigravity_full_fidelity.py (+40) | test_agent_message_viewer.py, test_agent_trace_lifecycle.py, test_agent_trace_viewer_visibility.py (+35) | Current synthetic tests pass unless noted in critical chains below; live provider proof pending. | Producer fixtures, native OS execution and Browser/live/finished boundaries require separate checks. |

## Critical regression chains

- #4–#8: missing child archives → fabricated topology → fail-open capture-stage coupling → inherited parent identity → duplicate observations. Sanitized real-capture parser tests pass now, but do not exercise today's Codex hooks.
- #10/#12/#13/#15: correct conversations.json previously coexisted with wrong UI ownership, question/answer pairing and non-agent panels. Shared shell verified; polling and static bootstrap remain distinct.
- #21/#23/#25/#27/#42/#45: folding and fixed lanes evolved into Dagre. Five #25 browser modules have no viewer_e2e marker. Dedicated CI selects marked tests on Ubuntu only; normal CI lacks Playwright. Native Windows marked gate: 27/27; excluded modules: 19 PASS / 8 FAIL. Failures include obsolete coordinates and External cluster assumptions as well as crossing growth. Do not blindly increase thresholds.
- #26/#28–#33: endpoint/execution identity repairs retain fixture coverage. #26 had already documented descendants outliving root; NEW-003 is independently reproduced here, not claimed as first discovery in project history. Gateway matrix labels run synthetic fixtures, not real gateways.
- #37/#39/#40/#41/#42/#44: repeated AGY root/child authority and wire repairs. #41 explicitly rejected #40's synthetic root test for supplying metadata absent in the real run; stdout remained null. #37 now passes a preconstructed root_topology() + eight-child conversation-entry fixture, proving renderer isolation conditional on inputs, not collector/archive production. #42 explicitly says real AGY eight-child and first-frame overlap were not accepted.
- #38/#47/#49/#50: Ollama run relay → serve relay → collector/finalization → release. #49 launches a fake Python HTTP child by monkeypatching resolution; no real ollama run model. Its interrupt is injected, not real terminal Ctrl+C. Real ConPTY/client/model/Browser audit is tracked separately.
- #11/#17/#24/#43: stage integrity checks protect named tests and explicit capability rows. They cannot establish Browser discovery, real prompt capture or provider wire compatibility. No non-PR issue reports returned by GitHub.

## Complete merged file inventory

### #50

- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `pyproject.toml`
- `src/execweave/__init__.py`
- `tests/test_v069_dashboard_release.py`

### #49

- `src/execweave/auto_specialized.py`
- `src/execweave/collector.py`
- `src/execweave/strace_backend.py`
- `tests/test_ollama_serve_runtime_integration.py`

### #48

- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `pyproject.toml`
- `src/execweave/__init__.py`
- `tests/test_v069_dashboard_release.py`

### #47

- `src/execweave/auto_specialized.py`
- `src/execweave/collector.py`
- `src/execweave/command.py`
- `tests/test_cursor_ollama_session_lifecycle.py`

### #46

- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `pyproject.toml`
- `src/execweave/__init__.py`
- `tests/test_v069_dashboard_release.py`

### #45

- `.github/workflows/provider-capability-stage-integrity.yml`
- `src/execweave/live_view_process_layout.py`
- `src/execweave/live_view_readability.py`
- `tests/test_graph_edge_routing_e2e.py`
- `tests/test_process_tree_layout.py`

### #44

- `.github/workflows/provider-capability-stage-integrity.yml`
- `.github/workflows/provider-dashboard-contract.yml`
- `src/execweave/antigravity_full_fidelity.py`
- `src/execweave/antigravity_subagent_linkage.py`
- `src/execweave/conversation_records_antigravity.py`
- `src/execweave/graph.py`
- `src/execweave/live.py`
- `src/execweave/live_view_script_d.py`
- `src/execweave/live_view_style.py`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_projection.py`
- `tests/test_antigravity_field_run_regressions.py`
- `tests/test_antigravity_subagent_transcript_linkage.py`
- `tests/test_dashboard_information_architecture.py`
- `tests/test_graph.py`
- `tests/test_live_logs_export.py`
- `tests/test_provider_dashboard_contract.py`
- `tests/test_viewer_agent_isolation_e2e.py`

### #43

- `.github/workflows/ci.yml`
- `.github/workflows/provider-capability-stage-integrity.yml`
- `.github/workflows/provider-dashboard-contract.yml`
- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `RELEASE-PLAN-0.8.0.md`
- `docs/antigravity-hooks.md`
- `docs/gemini-hooks.de.md`
- `docs/gemini-hooks.fr.md`
- `docs/gemini-hooks.ja.md`
- `docs/gemini-hooks.ko.md`
- `docs/gemini-hooks.md`
- `docs/gemini-hooks.ru.md`
- `docs/gemini-hooks.zh-CN.md`
- `docs/gemini-hooks.zh-TW.md`
- `docs/internal/provider-capability-matrix.md`
- `docs/live-graph.de.md`
- `docs/live-graph.fr.md`
- `docs/live-graph.ja.md`
- `docs/live-graph.ko.md`
- `docs/live-graph.md`
- `docs/live-graph.ru.md`
- `docs/live-graph.zh-CN.md`
- `docs/live-graph.zh-TW.md`
- `docs/phase-1-runtime-collection.de.md`
- `docs/phase-1-runtime-collection.fr.md`
- `docs/phase-1-runtime-collection.ja.md`
- `docs/phase-1-runtime-collection.ko.md`
- `docs/phase-1-runtime-collection.md`
- `docs/phase-1-runtime-collection.ru.md`
- `docs/phase-1-runtime-collection.zh-CN.md`
- `docs/phase-1-runtime-collection.zh-TW.md`
- `docs/remaining-provider-audit-v0.8.7.md`
- `docs/runtime-threat-model.de.md`
- `docs/runtime-threat-model.fr.md`
- `docs/runtime-threat-model.ja.md`
- `docs/runtime-threat-model.ko.md`
- `docs/runtime-threat-model.md`
- `docs/runtime-threat-model.ru.md`
- `docs/runtime-threat-model.zh-CN.md`
- `docs/runtime-threat-model.zh-TW.md`
- `docs/semantic-telemetry.de.md`
- `docs/semantic-telemetry.fr.md`
- `docs/semantic-telemetry.ja.md`
- `docs/semantic-telemetry.ko.md`
- `docs/semantic-telemetry.md`
- `docs/semantic-telemetry.ru.md`
- `docs/semantic-telemetry.zh-CN.md`
- `docs/semantic-telemetry.zh-TW.md`
- `docs/v0.6.5-hardening-decisions.md`
- `pyproject.toml`
- `scripts/audit_i18n_parity.py`
- `scripts/check_release_stage_integrity.py`
- `scripts/emit_gemini_hook_smoke.py`
- `scripts/sync_i18n_nav.py`
- `src/execweave/agent_bootstrap.py`
- `src/execweave/agent_trace.py`
- `src/execweave/antigravity_adapter_base.py`
- `src/execweave/antigravity_full_fidelity.py`
- `src/execweave/claude_adapter.py`
- `src/execweave/claude_child_transcript.py`
- `src/execweave/claude_hook_cli.py`
- `src/execweave/cli.py`
- `src/execweave/collector.py`
- `src/execweave/conversation_archive.py`
- `src/execweave/conversation_preview_common.py`
- `src/execweave/cursor_adapter.py`
- `src/execweave/cursor_full_fidelity.py`
- `src/execweave/dashboard_shell.py`
- `src/execweave/gemini_adapter.py`
- `src/execweave/gemini_full_fidelity.py`
- `src/execweave/gemini_hook_cli.py`
- `src/execweave/gemini_hook_contract.py`
- `src/execweave/gemini_record.py`
- `src/execweave/live.py`
- `src/execweave/live_core.py`
- `src/execweave/live_view_script_a.py`
- `src/execweave/provider_capability.py`
- `src/execweave/provider_lifecycle.py`
- `src/execweave/viewer.py`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_agent_panel_gemini.py`
- `src/execweave/viewer_agent_panel_registry.py`
- `src/execweave/viewer_dashboard_focus.py`
- `src/execweave/viewer_dashboard_hardening.py`
- `src/execweave/viewer_dashboard_hardening_v2.py`
- `src/execweave/viewer_limits.py`
- `src/execweave/viewer_projection_base.py`
- `tests/fixtures/hooks/gemini.json`
- `tests/fixtures/hooks/manifest.json`
- `tests/test_agent_bootstrap.py`
- `tests/test_agent_topology_evidence.py`
- `tests/test_agent_trace_viewer_visibility.py`
- `tests/test_antigravity_agent_collaboration.py`
- `tests/test_antigravity_child_transcript_tools.py`
- `tests/test_antigravity_cursor_launch.py`
- `tests/test_antigravity_identity_topology.py`
- `tests/test_antigravity_invocation_archive.py`
- `tests/test_antigravity_official_contract.py`
- `tests/test_antigravity_subagent_transcript_linkage.py`
- `tests/test_antigravity_trace_capability_cli.py`
- `tests/test_claude_adapter.py`
- `tests/test_claude_child_transcript_tools.py`
- `tests/test_codex_real_multi_agent_conversation.py`
- `tests/test_collector.py`
- `tests/test_command.py`
- `tests/test_conversation_access.py`
- `tests/test_conversation_agent_isolation.py`
- `tests/test_conversation_identity_merge.py`
- `tests/test_conversation_provider_parity.py`
- `tests/test_cross_provider_agent_trace.py`
- `tests/test_cursor_adapter.py`
- `tests/test_dashboard_information_architecture.py`
- `tests/test_external_endpoints_all_providers.py`
- `tests/test_gemini_adapter.py`
- `tests/test_gemini_full_fidelity.py`
- `tests/test_gemini_hook_contract.py`
- `tests/test_gemini_lifecycle.py`
- `tests/test_gemini_record.py`
- `tests/test_hook_fixture_corpus.py`
- `tests/test_provider_capability.py`
- `tests/test_provider_conversation_evidence.py`
- `tests/test_provider_dashboard_contract.py`
- `tests/test_provider_lifecycle.py`
- `tests/test_v064_live_auto_integrations.py`
- `tests/test_viewer_limits.py`

### #42

- `.github/workflows/provider-capability-stage-integrity.yml`
- `src/execweave/agy_preview_sanitize.py`
- `src/execweave/antigravity_full_fidelity.py`
- `src/execweave/antigravity_hook_cli.py`
- `src/execweave/antigravity_subagent_linkage.py`
- `src/execweave/codex_adapter.py`
- `src/execweave/codex_conversation.py`
- `src/execweave/conversation_preview.py`
- `src/execweave/conversation_preview_antigravity.py`
- `src/execweave/conversation_preview_claude.py`
- `src/execweave/conversation_preview_codex.py`
- `src/execweave/conversation_preview_common.py`
- `src/execweave/conversation_preview_generic.py`
- `src/execweave/conversation_preview_lines.py`
- `src/execweave/conversation_preview_transcript.py`
- `src/execweave/conversation_records.py`
- `src/execweave/conversation_records_antigravity.py`
- `src/execweave/conversation_records_codex.py`
- `src/execweave/conversation_records_common.py`
- `src/execweave/conversation_records_ollama.py`
- `src/execweave/dashboard_shell.py`
- `src/execweave/live_view.py`
- `src/execweave/live_view_process_layout.py`
- `src/execweave/live_view_readability.py`
- `src/execweave/vendor/dagre.min.js`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_agent_panel_antigravity.py`
- `src/execweave/viewer_agent_panel_claude.py`
- `src/execweave/viewer_agent_panel_codex.py`
- `src/execweave/viewer_agent_panel_cursor.py`
- `src/execweave/viewer_agent_panel_default.py`
- `src/execweave/viewer_agent_panel_gemini.py`
- `src/execweave/viewer_agent_panel_ollama.py`
- `src/execweave/viewer_agent_panel_opencode.py`
- `src/execweave/viewer_agent_panel_registry.py`
- `src/execweave/viewer_dashboard_clean.py`
- `src/execweave/viewer_external_endpoints.py`
- `src/execweave/viewer_projection.py`
- `tests/test_agy_windows_wire_acceptance.py`
- `tests/test_antigravity_child_panel_policy.py`
- `tests/test_antigravity_child_transcript_tools.py`
- `tests/test_antigravity_invocation_archive.py`
- `tests/test_antigravity_role_path_fallback.py`
- `tests/test_codex_adapter.py`
- `tests/test_codex_child_panel_policy.py`
- `tests/test_codex_nickname_path_fallback.py`
- `tests/test_dashboard_readability_e2e.py`
- `tests/test_dashboard_simplification.py`
- `tests/test_dashboard_ux_and_hook_projection.py`
- `tests/test_external_endpoints_all_providers.py`
- `tests/test_live.py`
- `tests/test_ollama_panel_policy.py`
- `tests/test_per_agent_conversation_default.py`
- `tests/test_pr25_premerge_hardening_e2e.py`
- `tests/test_process_tree_layout.py`
- `tests/test_viewer_agent_isolation_e2e.py`
- `tests/test_viewer_projection.py`
- `tests/test_windows_codex_agy_display_repair.py`

### #41

- `src/execweave/antigravity_adapter_base.py`
- `src/execweave/antigravity_full_fidelity_base.py`
- `src/execweave/live_view_markup.py`
- `src/execweave/live_view_readability.py`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_dashboard_clean.py`

### #39

- `src/execweave/antigravity_subagent_linkage.py`
- `src/execweave/conversation_records.py`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_dashboard_focus.py`
- `tests/test_antigravity_root_child_history_v2.py`

### #38

- `src/execweave/antigravity_full_fidelity_base.py`
- `src/execweave/auto_specialized.py`
- `src/execweave/collector.py`
- `src/execweave/conversation_preview.py`
- `src/execweave/conversation_records.py`
- `src/execweave/model_runtime_full_fidelity.py`
- `src/execweave/strace_backend.py`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_dashboard_focus.py`
- `tests/test_provider_conversation_history_integrity.py`

### #37

- `src/execweave/antigravity_full_fidelity.py`
- `src/execweave/dashboard_shell.py`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_dashboard_focus.py`
- `tests/test_antigravity_multi_conversation_isolation.py`
- `tests/test_conversation_root_authority.py`
- `tests/test_viewer_child_authority.py`

### #36

- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `tests/test_v069_dashboard_release.py`

### #34

- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `pyproject.toml`
- `src/execweave/__init__.py`
- `tests/test_v069_dashboard_release.py`

### #33

- `src/execweave/anthropic.py`
- `src/execweave/anthropic_full_fidelity.py`
- `src/execweave/inference_gateway.py`
- `src/execweave/openai_compatible.py`
- `src/execweave/openai_compatible_full_fidelity.py`
- `tests/test_v083_release_gate_p2.py`

### #32

- `src/execweave/conversation_records.py`
- `src/execweave/dashboard_shell.py`
- `tests/test_antigravity_history_replay.py`

### #31

- `src/execweave/antigravity_adapter.py`
- `src/execweave/conversation_archive.py`
- `tests/test_antigravity_identity_topology.py`

### #30

- `src/execweave/opencode_adapter.py`
- `src/execweave/opencode_full_fidelity.py`
- `tests/test_opencode_identity_unification.py`

### #29

- `.github/workflows/provider-capability-stage-integrity.yml`
- `src/execweave/inference_gateway.py`
- `src/execweave/model_runtime.py`
- `tests/test_inference_endpoint_identity.py`
- `tests/test_model_runtime.py`

### #28

- `.github/workflows/provider-capability-stage-integrity.yml`
- `src/execweave/conversation_records.py`
- `tests/test_conversation_identity_merge.py`

### #27

- `tests/test_pr25_premerge_hardening_contract.py`

### #25

- `.github/workflows/provider-capability-stage-integrity.yml`
- `docs/v0.8.3-graph-ergonomics.md`
- `src/execweave/live_view.py`
- `src/execweave/live_view_markup.py`
- `src/execweave/live_view_readability.py`
- `src/execweave/live_view_script_c.py`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_dashboard_hardening.py`
- `src/execweave/viewer_dashboard_hardening_v2.py`
- `tests/test_conversation_agent_focus.py`
- `tests/test_graph_clear_focus_e2e.py`
- `tests/test_graph_edge_routing_e2e.py`
- `tests/test_graph_lane_separation_e2e.py`
- `tests/test_graph_node_sizing_e2e.py`
- `tests/test_pr25_premerge_hardening_contract.py`
- `tests/test_pr25_premerge_hardening_e2e.py`
- `tests/test_tool_traffic_e2e.py`

### #24

- `.github/workflows/provider-capability-stage-integrity.yml`

### #23

- `.github/workflows/provider-capability-stage-integrity.yml`
- `tests/test_dashboard_round_fold_state_e2e.py`

### #22

- `.github/workflows/provider-capability-stage-integrity.yml`
- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `pyproject.toml`
- `src/execweave/__init__.py`
- `tests/test_v069_dashboard_release.py`

### #21

- `.github/workflows/provider-capability-stage-integrity.yml`
- `src/execweave/live_view.py`
- `src/execweave/live_view_readability.py`
- `src/execweave/viewer_agent_panel.py`
- `tests/dashboard_readability_fixture.py`
- `tests/test_dashboard_readability_e2e.py`
- `tests/test_dashboard_round_fold_state_e2e.py`

### #19

- `.github/workflows/provider-capability-stage-integrity.yml`
- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `pyproject.toml`
- `src/execweave/__init__.py`
- `tests/test_v069_dashboard_release.py`

### #18

- `.github/workflows/provider-capability-stage-integrity.yml`
- `src/execweave/cli.py`
- `src/execweave/dashboard_shell.py`
- `src/execweave/live_core.py`
- `src/execweave/top_cli.py`
- `src/execweave/view_cli.py`
- `src/execweave/viewer_dashboard_clean.py`
- `tests/test_fold_budget_setting.py`
- `tests/test_viewer_agent_isolation_e2e.py`

### #17

- `.github/workflows/provider-capability-stage-integrity.yml`
- `scripts/check_release_stage_integrity.py`
- `tests/test_release_stage_integrity_version_guard.py`

### #16

- `.github/workflows/provider-capability-stage-integrity.yml`
- `README.de.md`
- `README.fr.md`
- `README.ja.md`
- `README.ko.md`
- `README.md`
- `README.ru.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- `pyproject.toml`
- `src/execweave/__init__.py`
- `tests/test_v069_dashboard_release.py`

### #15

- `.github/workflows/provider-capability-stage-integrity.yml`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_dashboard_clean.py`
- `tests/multi_agent_run_fixture.py`
- `tests/test_conversation_agent_focus.py`
- `tests/test_dashboard_information_architecture.py`
- `tests/test_dashboard_simplification.py`
- `tests/test_viewer_agent_isolation_e2e.py`

### #13

- `.github/workflows/provider-capability-stage-integrity.yml`
- `RELEASE-PLAN-0.8.0.md`
- `src/execweave/_conversation_records_core.py`
- `src/execweave/viewer_agent_panel.py`
- `tests/multi_agent_run_fixture.py`
- `tests/test_agent_said_panel.py`
- `tests/test_agent_topology_evidence.py`
- `tests/test_conversation_agent_focus.py`
- `tests/test_dashboard_information_architecture.py`
- `tests/test_per_agent_conversation_default.py`
- `tests/test_shared_injected_context_scope.py`
- `tests/test_viewer_agent_isolation_e2e.py`

### #12

- `.github/workflows/provider-capability-stage-integrity.yml`
- `.github/workflows/viewer-agent-isolation.yml`
- `src/execweave/codex_conversation.py`
- `src/execweave/dashboard_shell.py`
- `src/execweave/live.py`
- `src/execweave/live_core.py`
- `src/execweave/live_view.py`
- `src/execweave/theme.py`
- `src/execweave/viewer_agent_panel.py`
- `src/execweave/viewer_antigravity_linkage_inspector.py`
- `src/execweave/viewer_conversation_panel.py`
- `src/execweave/viewer_conversation_tree.py`
- `src/execweave/viewer_dashboard_clean.py`
- `src/execweave/viewer_execution_inspector.py`
- `src/execweave/viewer_projection.py`
- `tests/multi_agent_run_fixture.py`
- `tests/test_agent_message_viewer.py`
- `tests/test_agent_node_labels.py`
- `tests/test_agent_said_panel.py`
- `tests/test_agent_topology_evidence.py`
- `tests/test_agent_trace_viewer_visibility.py`
- `tests/test_antigravity_linkage_projection.py`
- `tests/test_claude_hook_viewer.py`
- `tests/test_claude_record.py`
- `tests/test_codex_archive_full_fidelity.py`
- `tests/test_codex_plain_routed_agent_message.py`
- `tests/test_codex_record.py`
- `tests/test_conversation_access.py`
- `tests/test_conversation_agent_focus.py`
- `tests/test_conversation_provider_parity.py`
- `tests/test_dashboard_information_architecture.py`
- `tests/test_dashboard_simplification.py`
- `tests/test_dashboard_ux_and_hook_projection.py`
- `tests/test_delegation_viewer.py`
- `tests/test_execution_viewer.py`
- `tests/test_live_auth.py`
- `tests/test_live_delta.py`
- `tests/test_live_logs_export.py`
- `tests/test_per_agent_conversation_default.py`
- `tests/test_v069_dashboard_release.py`
- `tests/test_v079_review_e2e.py`
- `tests/test_v079_review_regressions.py`
- `tests/test_viewer_agent_isolation_e2e.py`
- `tests/test_viewer_content_inspector.py`
- `tests/test_viewer_projection.py`

### #11

- `.github/workflows/provider-capability-stage-integrity.yml`
- `docs/internal/provider-capability-matrix.md`
- `scripts/check_release_stage_integrity.py`
- `scripts/probe_provider_capability.py`
- `src/execweave/evidence_availability.py`
- `src/execweave/provider_capability.py`
- `tests/test_provider_capability.py`

### #10

- `src/execweave/_conversation_records_core.py`
- `src/execweave/live_view_script_a.py`
- `src/execweave/viewer.py`
- `src/execweave/viewer_conversation_tree.py`
- `tests/test_conversation_agent_focus.py`

### #8

- `src/execweave/_conversation_records_core.py`
- `src/execweave/conversation_message_identity.py`
- `src/execweave/conversation_records.py`
- `tests/test_conversation_message_observation_dedupe.py`

### #7

- `src/execweave/conversation_preview.py`
- `tests/test_codex_routing_native_identity.py`

### #6

- `src/execweave/codex_hook_cli.py`

### #5

- `scripts/check_conversation_records.py`
- `src/execweave/agent_topology.py`
- `src/execweave/codex_conversation.py`
- `src/execweave/conversation_preview.py`
- `src/execweave/conversation_records.py`
- `tests/test_conversation_identity_merge.py`

### #4

- `src/execweave/codex_conversation.py`
- `src/execweave/conversation_archive.py`
- `src/execweave/conversation_preview.py`
- `src/execweave/conversation_records.py`
- `tests/fixtures/codex_multi_agent/hook-payloads.json`
- `tests/fixtures/codex_multi_agent/rollout-main.jsonl`
- `tests/test_codex_real_multi_agent_conversation.py`

### #3

- `src/execweave/live.py`
- `src/execweave/viewer_conversation_tree.py`
- `src/execweave/viewer_dashboard_clean.py`
- `src/execweave/viewer_dashboard_focus.py`
- `src/execweave/viewer_live_layout.py`
- `src/execweave/viewer_projection.py`
- `tests/test_dashboard_information_architecture.py`
- `tests/test_dashboard_simplification.py`

### #2

- `src/execweave/codex_conversation.py`
- `src/execweave/codex_hook_cli.py`
- `src/execweave/conversation_archive.py`
- `src/execweave/conversation_records.py`
- `src/execweave/live.py`
- `src/execweave/viewer_conversation_panel.py`
- `src/execweave/viewer_dashboard_clean.py`
- `src/execweave/viewer_projection.py`
- `tests/test_codex_archive_full_fidelity.py`
- `tests/test_dashboard_simplification.py`

### #1

- `README.md`
- `docs/antigravity-hooks.md`
- `scripts/check_claude_hook.py`
- `src/execweave/agent_trace.py`
- `src/execweave/antigravity_adapter.py`
- `src/execweave/antigravity_adapter_base.py`
- `src/execweave/antigravity_full_fidelity.py`
- `src/execweave/antigravity_full_fidelity_base.py`
- `src/execweave/antigravity_full_fidelity_collaboration_base.py`
- `src/execweave/antigravity_hook_cli.py`
- `src/execweave/antigravity_subagent_linkage.py`
- `src/execweave/antigravity_trace_capability.py`
- `src/execweave/claude_delegation.py`
- `src/execweave/claude_hook_cli.py`
- `src/execweave/claude_hook_contract.py`
- `src/execweave/codex_adapter.py`
- `src/execweave/codex_hook_cli.py`
- `src/execweave/codex_hook_lifecycle.py`
- `src/execweave/codex_message_diagnostics.py`
- `src/execweave/codex_message_transport_diagnostics.py`
- `src/execweave/codex_record.py`
- `src/execweave/codex_rollout_structures.py`
- `src/execweave/codex_rollout_trace.py`
- `src/execweave/codex_rollout_trace_base.py`
- `src/execweave/content_store.py`
- `src/execweave/conversation_archive.py`
- `src/execweave/conversation_records.py`
- `src/execweave/cursor_delegation.py`
- `src/execweave/cursor_delegation_base.py`
- `src/execweave/cursor_full_fidelity.py`
- `src/execweave/cursor_hook_cli.py`
- `src/execweave/cursor_hook_contract.py`
- `src/execweave/gemini_full_fidelity.py`
- `src/execweave/gemini_hook_cli.py`
- `src/execweave/gemini_hook_contract.py`
- `src/execweave/live.py`
- `src/execweave/opencode_event_contract.py`
- `src/execweave/opencode_hook_cli.py`
- `src/execweave/opencode_task_linkage.py`
- `src/execweave/provider_lifecycle.py`
- `src/execweave/provider_record.py`
- `src/execweave/viewer_antigravity_linkage_inspector.py`
- `src/execweave/viewer_content_inspector.py`
- `src/execweave/viewer_conversation_panel.py`
- `src/execweave/viewer_execution_inspector.py`
- `src/execweave/viewer_projection.py`
- `src/execweave/viewer_projection_base.py`
- `tests/test_agent_message_viewer.py`
- `tests/test_agent_trace_lifecycle.py`
- `tests/test_agent_trace_viewer_visibility.py`
- `tests/test_antigravity_agent_collaboration.py`
- `tests/test_antigravity_lifecycle.py`
- `tests/test_antigravity_linkage_projection.py`
- `tests/test_antigravity_official_contract.py`
- `tests/test_antigravity_subagent_transcript_linkage.py`
- `tests/test_antigravity_trace_capability_cli.py`
- `tests/test_claude_adapter.py`
- `tests/test_claude_delegation.py`
- `tests/test_claude_hook_contract.py`
- `tests/test_claude_hook_metadata.py`
- `tests/test_claude_hook_viewer.py`
- `tests/test_codex_adapter.py`
- `tests/test_codex_hook_lifecycle.py`
- `tests/test_codex_message_diagnostics.py`
- `tests/test_codex_message_transport_diagnostics.py`
- `tests/test_codex_reducer_command.py`
- `tests/test_codex_rollout_structures.py`
- `tests/test_codex_rollout_trace.py`
- `tests/test_conversation_access.py`
- `tests/test_cross_provider_agent_trace.py`
- `tests/test_cursor_adapter.py`
- `tests/test_cursor_delegation.py`
- `tests/test_cursor_full_fidelity.py`
- `tests/test_cursor_hook_contract.py`
- `tests/test_cursor_hook_fail_open.py`
- `tests/test_cursor_task_linkage.py`
- `tests/test_delegation_viewer.py`
- `tests/test_execution_viewer.py`
- `tests/test_gemini_full_fidelity.py`
- `tests/test_gemini_hook_contract.py`
- `tests/test_gemini_lifecycle.py`
- `tests/test_opencode_event_contract.py`
- `tests/test_opencode_event_lifecycle.py`
- `tests/test_opencode_task_session_linkage.py`
- `tests/test_viewer_content_inspector.py`
