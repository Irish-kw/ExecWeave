"""SDK tests need no optional MetaGPT installation; real-source tests live in scripts."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from execweave.framework_adapters import AdapterContext, ContentCapturePolicy, MetaGPTAdapter
from execweave.framework_adapters.metagpt_recording import OllamaRecordingMixin
from execweave.framework_adapters.metagpt_ollama_compat import PreserveOllamaChatHistory


class Session:
    def __init__(self):
        self.wire = []
        self.failures = 0

    async def request(self, **kwargs):
        body = json.loads(kwargs["data"])
        self.wire.append(body)
        await asyncio.sleep(0.002 if body["messages"][0]["content"] == "slow" else 0)
        if self.failures:
            self.failures -= 1
            raise ConnectionError("secret exception text must not be logged")
        return SimpleNamespace(status=200, text=body["messages"][-1]["content"])


class Client:
    def __init__(self):
        self.session = Session()

    async def arequest_raw(self, method, url, session, *, params=None):
        return await session.request(
            method=method,
            url=url,
            data=json.dumps(params),
            headers={"Authorization": "SECRET_HEADER"},
        )

    async def arequest(self, method, url, params, stream=False):
        return await self.arequest_raw(method, url, self.session, params=params)


class Provider:
    def __init__(self, config):
        self.config = config
        self.model = "fixture-model"
        self.client = Client()

    async def aask(
        self, msg, system_msgs=None, format_msgs=None, images=None, timeout=0, stream=None
    ):
        if msg == "invalid":
            raise ValueError("pre-transport")
        messages = [{"role": "user", "content": msg}]
        return await self.acompletion_text(messages, stream=stream, timeout=timeout)

    async def acompletion_text(self, messages, stream=False, timeout=0):
        for attempt in range(3):
            try:
                response = await self.acompletion(messages, timeout)
                return response["text"]
            except ConnectionError:
                if attempt == 2:
                    raise

    async def acompletion(self, messages, timeout=0):
        response = await self.client.arequest(
            "post",
            "/api/chat",
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.3},
            },
        )
        return {"text": response.text}


class Recorded(OllamaRecordingMixin, Provider):
    pass


def make(root, mode="prompt_and_response"):
    adapter = MetaGPTAdapter(
        AdapterContext(
            framework="metagpt",
            run_id="test",
            sidecar=root / "semantic.jsonl",
            content_root=root,
            capture_policy=ContentCapturePolicy(mode),
        )
    )
    return Recorded(None, adapter=adapter, role_ref=adapter.observe_role("role"))


def records(root):
    return [json.loads(line) for line in (root / "semantic.jsonl").read_text().splitlines()]


def stage(root, name):
    return [r for r in records(root) if r["attributes"].get("capture_stage") == name]


def content(root, event):
    return json.loads((root / event["attributes"]["content_ref"]).read_text())


def test_wire_payload_exact_and_logical_counts(tmp_path):
    llm = make(tmp_path)
    assert asyncio.run(llm.aask("hello", stream=True)) == "hello"
    attempt = stage(tmp_path, "http_transport")[0]
    assert content(tmp_path, attempt)["provider_payload"] == llm.client.session.wire[0]
    assert content(tmp_path, attempt)["provider_payload"]["stream"] is False
    assert content(tmp_path, stage(tmp_path, "acompletion_text")[0])["stream"] is True
    assert sum(r["event_type"] == "MODEL_REQUEST" for r in records(tmp_path)) == 1
    assert llm._provider_attempt_count == llm._request_count == llm._response_count == 1


def test_parallel_calls_and_responses_are_correlated(tmp_path):
    llm = make(tmp_path)

    async def run():
        return await asyncio.gather(llm.aask("slow"), llm.aask("fast"))

    assert asyncio.run(run()) == ["slow", "fast"]
    requests = {
        r["attributes"]["logical_call_id"]: content(tmp_path, r)["messages"][0]["content"]
        for r in stage(tmp_path, "aask_entry")
    }
    for event in stage(tmp_path, "http_transport"):
        assert (
            content(tmp_path, event)["provider_payload"]["messages"][0]["content"]
            == requests[event["attributes"]["logical_call_id"]]
        )
    for event in records(tmp_path):
        if event["event_type"] == "MODEL_RESPONSE":
            assert (tmp_path / event["attributes"]["content_ref"]).read_text() == requests[
                event["attributes"]["logical_call_id"]
            ]
    assert llm._call_context.get() is None


@pytest.mark.parametrize("failures,attempts,success", [(1, 2, True), (3, 3, False)])
def test_transport_retries_keep_one_logical_call(tmp_path, failures, attempts, success):
    llm = make(tmp_path)
    llm.client.session.failures = failures
    if success:
        asyncio.run(llm.aask("retry"))
    else:
        with pytest.raises(ConnectionError):
            asyncio.run(llm.aask("retry"))
    sent = stage(tmp_path, "http_transport")
    assert len(sent) == attempts == len(llm.client.session.wire)
    assert len({r["attributes"]["logical_call_id"] for r in sent}) == 1
    assert len({r["attributes"]["provider_attempt_id"] for r in sent}) == attempts
    outcomes = stage(tmp_path, "http_transport_outcome")
    assert [r["attributes"]["transport_status"] for r in outcomes] == ["failed"] * failures + (
        ["response_received"] if success else []
    )
    assert llm._request_count == 1
    assert llm._call_context.get() is None


def test_pretransport_failure_has_no_attempt(tmp_path):
    llm = make(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(llm.aask("invalid"))
    assert not stage(tmp_path, "http_transport")
    failure = next(r for r in records(tmp_path) if r["event_type"] == "MODEL_FAILURE")
    assert failure["attributes"]["transport_status"] == "not_sent"
    assert llm._request_count == llm._failure_count == 1


def test_same_role_multiple_llm_instances_have_unique_calls(tmp_path):
    first = make(tmp_path)
    second = Recorded(None, adapter=first._adapter, role_ref=first._role_ref)

    async def run():
        await asyncio.gather(first.aask("one"), second.aask("two"))

    asyncio.run(run())
    ids = [e["attributes"]["logical_call_id"] for e in stage(tmp_path, "aask_entry")]
    assert len(ids) == len(set(ids)) == 2


@pytest.mark.parametrize("method", ["acompletion_text", "acompletion"])
def test_direct_calls_get_fallback_identity(tmp_path, method):
    llm = make(tmp_path)
    asyncio.run(getattr(llm, method)([{"role": "user", "content": "direct"}]))
    assert llm._request_count == llm._provider_attempt_count == 1
    assert len(stage(tmp_path, method + "_entry")) == 1


@pytest.mark.parametrize(
    "mode", ["metadata_only", "prompt_only", "content_ref_only", "prompt_and_response"]
)
def test_capture_policy_and_no_header_collection(tmp_path, mode):
    llm = make(tmp_path, mode)
    asyncio.run(llm.aask("PROMPT_SENTINEL"))
    text = "\n".join(p.read_text(errors="replace") for p in tmp_path.rglob("*") if p.is_file())
    assert "SECRET_HEADER" not in text
    assert "Authorization" not in text
    if mode == "metadata_only":
        assert "PROMPT_SENTINEL" not in text
        assert all(
            not r["attributes"].get("content_ref") for r in stage(tmp_path, "http_transport")
        )
    else:
        assert "PROMPT_SENTINEL" in text
    if mode == "prompt_only":
        assert not next(r for r in records(tmp_path) if r["event_type"] == "MODEL_RESPONSE")[
            "attributes"
        ]["content_available"]


def test_explicit_compat_preserves_turns_roles_and_images():
    original = SimpleNamespace(
        api_suffix="/chat",
        model="vision",
        additional_kwargs={"stream": True, "options": {"seed": 4}},
    )
    shim = PreserveOllamaChatHistory(original)
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "last"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}},
            ],
        },
    ]
    payload = shim.apply(messages)
    assert payload == {
        "model": "vision",
        "stream": True,
        "options": {"seed": 4},
        "messages": [*messages[:3], {"role": "user", "content": "last", "images": ["YWJj"]}],
    }
    assert isinstance(messages[-1]["content"], list)


def test_compat_rejects_unsupported_images_without_fetching():
    shim = PreserveOllamaChatHistory(SimpleNamespace(api_suffix="/chat"))
    with pytest.raises(ValueError, match="base64"):
        shim.apply(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "https://example.invalid/image"}}
                    ],
                }
            ]
        )
