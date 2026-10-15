"""Real OpenAI Agents SDK span smoke without API keys or external requests.

Only tracing primitives are executed. No Agent model request or tool side effect
is performed. Run with the optional openai-agents extra installed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    from agents.tracing import (
        agent_span, function_span, generation_span, handoff_span, response_span,
        set_trace_processors, trace,
    )
    from execweave.openai_agents_sdk import install_agents_sdk_tracing

    with TemporaryDirectory(prefix="execweave-sdk-smoke-") as folder:
        sidecar = Path(folder) / "semantic.jsonl"
        os.environ["EXECWEAVE_SEMANTIC_SIDECAR"] = str(sidecar)
        os.environ["EXECWEAVE_SESSION_ID"] = "real-sdk-smoke"
        os.environ["EXECWEAVE_RUN_ID"] = "real-sdk-smoke"

        # Never send any smoke trace to an SDK's default remote exporter.
        set_trace_processors([])
        recorder = install_agents_sdk_tracing(capture_mode="metadata_only")
        assert recorder.enabled
        with trace("ExecWeave offline SDK compatibility smoke"):
            with agent_span("Tool_Selector", tools=["lookup"]):
                with generation_span(model="gpt-fixture"):
                    pass
                with response_span():
                    pass
            with agent_span("Simulation_Agent", tools=["lookup"]):
                with function_span("lookup", input="synthetic", output="synthetic"):
                    pass
                with handoff_span(from_agent="Simulation_Agent", to_agent="Reviewer"):
                    pass
        recorder.force_flush()
        events = [json.loads(line) for line in sidecar.read_text().splitlines()]
        kinds = {event["event_type"] for event in events}
        expected = {
            "AGENT_CREATED", "AGENT_STARTED", "AGENT_STOPPED",
            "MODEL_REQUEST", "MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT",
            "MESSAGE_SENT",
        }
        missing = expected - kinds
        assert not missing, f"Missing SDK-derived event categories: {sorted(missing)}"
        assert not any(e["event_type"] == "MESSAGE_RECEIVED" for e in events)
        coverage = [e for e in events if e["relation"] == "OBSERVATION_COVERAGE"]
        assert len(coverage) == 1
        counts = coverage[0]["attributes"]["span_counts"]
        assert counts["agent"] == 2
        assert counts["function"] == 1
        assert counts["generation"] == 1
        assert counts["response"] == 1
        assert counts["handoff"] == 1
        assert coverage[0]["attributes"]["unclosed_spans"] == 0
        assert recorder.callback_errors == 0
        print("Native Agents SDK tracing smoke: PASS (offline, metadata only)")


if __name__ == "__main__":
    main()
