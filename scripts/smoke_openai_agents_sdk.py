"""Real OpenAI Agents SDK span smoke without API keys or external requests.

Runs SDK tracing primitives and a real Runner with a scripted offline model.
A deterministic local tool is invoked; it performs no network or OS effect.
Run with the optional openai-agents extra installed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    from agents.tracing import (
        agent_span, function_span, generation_span, handoff_span, response_span,
        task_span, turn_span, set_trace_processors, trace,
    )
    from execweave.openai_agents_sdk import install_agents_sdk_tracing
    from agents import Agent, Runner, function_tool
    from agents.testing import ScriptedModel, assistant_message, function_call

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
                with task_span("Simulation Stage"):
                    with turn_span(turn=1, agent_name="Simulation_Agent"):
                        with function_span("lookup", input="synthetic", output="synthetic"):
                            pass
                        with handoff_span(from_agent="Simulation_Agent", to_agent="Reviewer"):
                            pass
        @function_tool
        def local_status() -> str:
            """Return a deterministic local value; no OS or network effects."""
            return "local-ok"

        model = ScriptedModel(
            steps=[
                [function_call("local_status", "{}", call_id="synthetic-tool-1")],
                [assistant_message("offline-test-finished")],
            ],
            emit_traces=True,
        )
        agent = Agent(
            name="OfflineSDKAgent",
            instructions="Use the local-only test tool.",
            tools=[local_status],
            model=model,
        )
        result = Runner.run_sync(agent, "Execute the test function.")
        assert result.final_output == "offline-test-finished"
        model.assert_complete()

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
        assert len(coverage) == 2
        counts = next(x["attributes"]["span_counts"] for x in coverage
                      if x["attributes"]["span_counts"].get("handoff") == 1)
        assert counts["agent"] == 2
        assert counts["function"] == 1
        assert counts["generation"] == 1
        assert counts["response"] == 1
        assert counts["handoff"] == 1
        assert counts["task"] == 1
        assert counts["turn"] == 1
        assert any(e["relation"] == "SDK_TASK_SPAN_ENDED" for e in events)
        assert any(e["relation"] == "SDK_TURN_ENDED" for e in events)
        assert not any(e["event_type"] == "TASK_COMPLETED" for e in events)
        assert all(row["attributes"]["unclosed_spans"] == 0 for row in coverage)
        assert any(x["attributes"]["span_counts"].get("agent", 0) >= 1 for x in coverage
                   if x["attributes"]["span_counts"].get("handoff", 0) == 0)
        assert sum(x["event_type"] == "TOOL_RESULT" for x in events) >= 2
        assert recorder.callback_errors == 0
        print("Native Agents SDK tracing and real Runner smoke: PASS (offline, metadata only)")


if __name__ == "__main__":
    main()
