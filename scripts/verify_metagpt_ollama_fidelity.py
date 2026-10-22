"""Real installed-MetaGPT and independently captured Ollama HTTP acceptance.

Run in a MetaGPT environment, with a genuine Ollama service. Synthetic prompts
only. A loopback proxy buffers responses (including NDJSON); no headers or
credentials are retained. Fault injection is explicitly labeled in the report.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.client
import importlib.metadata
import json
import platform
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from real_metagpt_acceptance import (
    ActionNode,
    AdapterContext,
    Config,
    ContentCapturePolicy,
    MetaGPTAdapter,
    ObservedOllamaLLM,
    ROOT,
    run_acceptance,
)
from execweave.framework_adapters.metagpt_ollama_compat import enable_chat_history_compatibility
from execweave.framework_adapters.metagpt_recording import observe_actionnode_retries
from metagpt.configs.compress_msg_config import CompressType
from metagpt.provider.base_llm import BaseLLM
from tenacity import stop_after_attempt, wait_none


def read_events(root):
    return [
        json.loads(line)
        for line in (root / "semantic.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def captured(root, stage):
    return [
        (e, json.loads((root / e["attributes"]["content_ref"]).read_text(encoding="utf-8")))
        for e in read_events(root)
        if e["attributes"].get("capture_stage") == stage and e["attributes"].get("content_ref")
    ]


class CaptureProxy:
    def __init__(self, endpoint):
        target = urlsplit(endpoint)
        if target.scheme != "http" or target.hostname not in ("127.0.0.1", "localhost"):
            raise ValueError("Acceptance proxy supports loopback HTTP Ollama only")
        self.wire = []
        self.malformed_remaining = 0
        self.mock = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                body = json.loads(raw)
                entry = {
                    "path": self.path,
                    "payload": body,
                    "source": "mock" if owner.mock else "ollama",
                }
                owner.wire.append(entry)
                if owner.mock:
                    status, content_type = 200, "application/json"
                    result = json.dumps(
                        {"message": {"role": "assistant", "content": "mock"}, "done": True}
                    ).encode()
                else:
                    conn = http.client.HTTPConnection(
                        target.hostname, target.port or 80, timeout=240
                    )
                    try:
                        conn.request("POST", self.path, raw, {"Content-Type": "application/json"})
                        response = conn.getresponse()
                        status, content_type = response.status, response.getheader("Content-Type")
                        result = response.read()
                    finally:
                        conn.close()
                entry["http_status"] = status
                if owner.malformed_remaining:
                    owner.malformed_remaining -= 1
                    result = json.dumps(
                        {
                            "message": {"role": "assistant", "content": "not structured output"},
                            "done": True,
                        }
                    ).encode()
                    entry["fault_injection"] = "replace_real_response_with_malformed_content"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(result)))
                self.end_headers()
                self.wfile.write(result)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


async def verify(args):
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    proxy = CaptureProxy(args.endpoint)
    results = []

    def make(name, compat=False):
        root = output / name
        root.mkdir()
        adapter = MetaGPTAdapter(
            AdapterContext(
                framework="metagpt",
                run_id=name,
                sidecar=root / "semantic.jsonl",
                content_root=root,
                capture_policy=ContentCapturePolicy("prompt_and_response"),
            )
        )
        role = adapter.observe_role("probe")
        cfg = Config.default(reload=True).llm.model_copy(deep=True)
        cfg.base_url = proxy.endpoint + "/api"
        cfg.model, cfg.stream, cfg.timeout = args.model, False, 240
        llm = ObservedOllamaLLM(cfg, adapter=adapter, role_ref=role)
        llm.ollama_message.additional_kwargs["options"]["num_predict"] = 32
        if compat:
            enable_chat_history_compatibility(llm)
        return root, llm, adapter, role

    def check(name, root, start, **details):
        for event in read_events(root):
            attributes = event["attributes"]
            if attributes.get("content_ref"):
                content_bytes = (root / attributes["content_ref"]).read_bytes()
                assert hashlib.sha256(content_bytes).hexdigest() == attributes["content_sha256"]
        actual = proxy.wire[start:]
        recorded = captured(root, "http_transport")

        # Full JSON equality: no keys, options, roles or messages ignored.
        def canonical(p):
            return json.dumps(p, sort_keys=True, ensure_ascii=False)

        assert sorted(canonical(p["provider_payload"]) for _, p in recorded) == sorted(
            canonical(w["payload"]) for w in actual
        )
        attempts = [e["attributes"]["provider_attempt_id"] for e, _ in recorded]
        assert len(attempts) == len(set(attempts))
        outcomes = [
            e
            for e in read_events(root)
            if e["attributes"].get("capture_stage") == "http_transport_outcome"
        ]
        assert sorted(e["attributes"]["provider_attempt_id"] for e in outcomes) == sorted(attempts)
        row = dict(name=name, fidelity="PASS", requests=len(actual), **details)
        results.append(row)
        (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(row), flush=True)

    try:
        history = [
            {"role": "user", "content": "Remember ALPHA. Reply OK."},
            {"role": "assistant", "content": "OK"},
            {"role": "user", "content": "What code?"},
        ]
        cases = [
            ("single", False, False, "Reply OK.", {}),
            ("upstream_history_loss", False, False, history, {}),
            ("corrected_history", True, False, history, {}),
            ("explicit_system", True, True, "Reply OK.", {"system_msgs": ["Reply BRAVO."]}),
            ("default_system", True, True, "Reply OK.", {}),
            ("disabled_system", True, False, "Reply OK.", {"system_msgs": ["Reply BRAVO."]}),
            (
                "format_system",
                True,
                False,
                "Reply OK.",
                {"format_msgs": [{"role": "system", "content": "Reply DELTA."}]},
            ),
            (
                "caller_system",
                True,
                False,
                [
                    {"role": "system", "content": "Reply ECHO."},
                    {"role": "user", "content": "Reply OK."},
                ],
                {},
            ),
        ]
        for name, compat, enabled, msg, kwargs in cases:
            root, llm, _, _ = make(name, compat)
            llm.use_system_prompt = enabled
            start = len(proxy.wire)
            await llm.aask(msg, **kwargs)
            final = captured(root, "acompletion_text")[0][1]["final_messages"]
            wire = proxy.wire[-1]["payload"]["messages"]
            if compat or name == "single":
                assert final == wire
            else:
                assert final == history and wire == history[:1]
            if name == "default_system":
                assert final[0] == {"role": "system", "content": llm.system_prompt}
            if name == "explicit_system":
                assert final[0] == {"role": "system", "content": "Reply BRAVO."}
            if name == "disabled_system":
                assert all(m["role"] != "system" for m in final)
            if name in ("format_system", "caller_system"):
                assert final[0]["role"] == "system"
            check(
                name, root, start, intended_history_preserved=(final == wire), compatibility=compat
            )

        root, llm, _, _ = make("parallel_and_direct", True)
        start = len(proxy.wire)
        assert len(await asyncio.gather(llm.aask("Reply ONE."), llm.aask("Reply TWO."))) == 2
        await llm.acompletion_text([{"role": "user", "content": "Reply DIRECT."}])
        await llm.aask_batch(["Reply BATCH1.", "Reply BATCH2."])
        assert llm._request_count == llm._provider_attempt_count == 5
        by_call = {
            e["attributes"]["logical_call_id"]: p["final_messages"]
            for e, p in captured(root, "acompletion_text")
        }
        for e, p in captured(root, "http_transport"):
            assert by_call[e["attributes"]["logical_call_id"]] == p["provider_payload"]["messages"]
        check("parallel_and_direct", root, start, logical_calls=5)

        root, llm, _, _ = make("compression", True)
        start = len(proxy.wire)
        llm.config.compress_type = CompressType.POST_CUT_BY_MSG
        llm.compress_messages = lambda messages, compress_type: BaseLLM.compress_messages(
            llm, messages, compress_type, max_token=20, threshold=1
        )
        await llm.aask(
            [
                {"role": "user", "content": "A" * 100},
                {"role": "assistant", "content": "B" * 100},
                {"role": "user", "content": "Reply OK."},
            ]
        )
        assert proxy.wire[-1]["payload"]["messages"] == [{"role": "user", "content": "Reply OK."}]
        assert (
            captured(root, "acompletion_text")[0][1]["final_messages"]
            == proxy.wire[-1]["payload"]["messages"]
        )
        check("compression", root, start)

        for config_stream, call_stream in [(False, True), (True, True), (True, False)]:
            name = f"stream_{config_stream}_{call_stream}"
            root, llm, _, _ = make(name)
            llm.config.stream = config_stream
            llm.ollama_message.additional_kwargs["stream"] = config_stream
            start = len(proxy.wire)
            failure = None
            try:
                await llm.aask("Reply OK.", stream=call_stream)
            except Exception as exc:
                failure = type(exc).__name__
            p = captured(root, "http_transport")[0][1]
            assert p["provider_payload"]["stream"] == config_stream
            assert p["transport_stream"] == call_stream
            check(name, root, start, logical_failure=failure)

        root, llm, _, _ = make("pretransport_failure")
        start = len(proxy.wire)
        try:
            await llm.aask([{"bad": "message"}])
        except (KeyError, TypeError):
            pass
        else:
            raise AssertionError("invalid message unexpectedly accepted")
        assert llm._failure_count == 1 and llm._provider_attempt_count == 0
        assert (
            next(e for e in read_events(root) if e["event_type"] == "MODEL_FAILURE")["attributes"][
                "transport_status"
            ]
            == "not_sent"
        )
        check("pretransport_failure", root, start)

        root, llm, _, _ = make("transport_retry")
        start = len(proxy.wire)
        observed_raw = llm.client.arequest_raw
        remaining = [1]

        class FaultSession:
            def __init__(self, session):
                self.session = session

            async def request(self, **kwargs):
                result = await self.session.request(**kwargs)
                if remaining[0]:
                    remaining[0] -= 1
                    await result.read()
                    result.close()
                    raise ConnectionError("controlled retry after real HTTP response")
                return result

        async def retry_raw(method, url, session, **kwargs):
            return await observed_raw(method, url, FaultSession(session), **kwargs)

        llm.client.arequest_raw = retry_raw
        await llm.aask("Reply RETRY.")
        assert llm._request_count == 1 and llm._provider_attempt_count == 2
        check(
            "transport_retry",
            root,
            start,
            fault_injection="ConnectionError after real HTTP response",
            logical_calls=1,
        )

        root, llm, _, _ = make("provider_http_failure")
        start = len(proxy.wire)
        llm.ollama_message.model = "execweave-intentionally-missing-model"
        try:
            await llm.aask("Reply OK.")
        except Exception:
            pass
        else:
            raise AssertionError("missing model unexpectedly succeeded")
        assert proxy.wire[-1]["http_status"] == 404
        assert llm._request_count == llm._failure_count == llm._provider_attempt_count == 1
        check("provider_http_failure", root, start, expected_http_status=404)

        for compat in (False, True):
            name = f"actionnode_{compat}"
            start = len(proxy.wire)
            root = output / name
            summary = await run_acceptance(
                argparse.Namespace(
                    output_dir=root,
                    endpoint=proxy.endpoint,
                    model=args.model,
                    preserve_chat_history=compat,
                )
            )
            assert summary["task_success"] and summary["observability_pass"]
            assert summary["logical_call_count"] == summary["model_request_count"]
            check(name, root, start, task_success=summary["task_success"])

        root, llm, adapter, role = make("malformed_actionnode")
        start = len(proxy.wire)
        llm.ollama_message.additional_kwargs["options"]["num_predict"] = 128
        node = ActionNode("value", str, "Return OK", "OK")
        node.set_llm(llm)
        # Bound the controlled-failure test only; production policies unchanged.
        from types import MethodType

        node._aask_v1 = MethodType(
            node._aask_v1.__func__.retry_with(stop=stop_after_attempt(2), wait=wait_none()), node
        )
        task = adapter.observe_task("malformed", owner=role)
        counts = observe_actionnode_retries(node, llm, adapter, role, task)
        proxy.malformed_remaining = 2
        try:
            await node._aask_v1(
                'Return [CONTENT]{"value":"OK"}[/CONTENT]',
                "Result",
                {"value": (str, ...)},
                schema="json",
            )
        except Exception:
            pass
        else:
            raise AssertionError("malformed responses unexpectedly parsed")
        assert counts == {"attempts": 2, "retries": 1, "parser_failures": 2}
        assert llm._request_count == llm._response_count == 2 and llm._failure_count == 0
        check(
            "malformed_actionnode",
            root,
            start,
            fault_injection="replace two real responses",
            **counts,
        )

        root, llm, adapter, role = make("recovered_parser_retry")
        start = len(proxy.wire)
        llm.ollama_message.additional_kwargs["options"]["num_predict"] = 128
        node = ActionNode.from_children(
            "result", [ActionNode("value", str, "Return the string OK", "OK")]
        )
        node.set_llm(llm)
        node._aask_v1 = MethodType(
            node._aask_v1.__func__.retry_with(stop=stop_after_attempt(3), wait=wait_none()), node
        )
        task = adapter.observe_task("recovered", owner=role)
        counts = observe_actionnode_retries(node, llm, adapter, role, task)
        proxy.malformed_remaining = 1
        _, parsed = await node._aask_v1(
            node.compile(
                context="Return value OK as a structured object.", schema="json", mode="auto"
            ),
            "Result",
            {"value": (str, ...)},
            schema="json",
        )
        assert parsed.value == "OK"
        assert counts["retries"] >= 1 and counts["parser_failures"] >= 1
        assert llm._failure_count == 0 and llm._request_count == counts["attempts"]
        check(
            "recovered_parser_retry",
            root,
            start,
            task_success=True,
            fault_injection="replace first real response",
            **counts,
        )

        # Image transform test uses the installed provider plus real loopback HTTP,
        # but a mock response because the chosen text model has no image support.
        root, llm, _, _ = make("image_transform")
        start = len(proxy.wire)
        proxy.mock = True
        await llm.acompletion_text(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Image"},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,YWJj"}},
                    ],
                }
            ]
        )
        assert proxy.wire[-1]["payload"]["messages"] == [
            {"role": "user", "content": "Image", "images": ["YWJj"]}
        ]
        check("image_transform", root, start, mock_response=True)
    finally:
        (output / "wire.json").write_text(json.dumps(proxy.wire, indent=2), encoding="utf-8")
        import metagpt.provider.base_llm as base
        import metagpt.provider.ollama_api as provider

        versions = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "metagpt": importlib.metadata.version("metagpt"),
            "model": args.model,
            "execweave_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "source_hashes": {
                Path(m.__file__).name: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
                for m in (base, provider)
            },
        }
        (output / "versions.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")
        proxy.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:12345")
    parser.add_argument("--model", default="llama3.1:8b")
    asyncio.run(verify(parser.parse_args()))
