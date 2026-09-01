from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one guarded match, found {count}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    text = read(path)
    left = text.find(start)
    if left < 0:
        raise SystemExit(f"{path}: start marker missing: {start!r}")
    right = text.find(end, left)
    if right < 0:
        raise SystemExit(f"{path}: end marker missing: {end!r}")
    if text.find(start, left + 1) >= 0:
        raise SystemExit(f"{path}: start marker is not unique: {start!r}")
    write(path, text[:left] + replacement + text[right:])


# ---------------------------------------------------------------------------
# Antigravity: parse the live-verified wire instead of treating every MODEL
# record as a user-visible assistant response.
# ---------------------------------------------------------------------------
replace_once(
    "src/execweave/conversation_preview.py",
    "import json\n",
    "import json\nimport re\n",
)

NEW_LINE_TRANSCRIPT = r'''_ANTIGRAVITY_USER_REQUEST_RE = re.compile(
    r"<USER_REQUEST>\\s*(?P<body>.*?)\\s*</USER_REQUEST>",
    re.DOTALL,
)


def _antigravity_user_text(text: str) -> str:
    """Return the actual user request, excluding Antigravity's metadata envelope."""
    match = _ANTIGRAVITY_USER_REQUEST_RE.search(text)
    return match.group("body").strip() if match is not None else text.strip()


def _line_transcript_messages(
    path: Path,
    *,
    timestamp: object,
    ordinal: object,
    agent_path: str,
    antigravity: bool = False,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue

        if antigravity:
            role = str(record.get("source") or "").strip().lower()
            record_type = str(record.get("type") or "").strip().lower()
            text = _text_parts(record.get("content") or record.get("text"))
            record_timestamp = record.get("created_at") or record.get("timestamp") or timestamp
            step_index = record.get("step_index")
            record_ordinal = (
                step_index
                if isinstance(step_index, int) and not isinstance(step_index, bool)
                else (ordinal if isinstance(ordinal, int) else 0) + index
            )

            # Current Antigravity uses USER_EXPLICIT / USER_INPUT for real user turns.
            # Keep the older USER/HUMAN spelling for archived compatibility.
            if role in {"user_explicit", "user", "human"} and record_type in {
                "user_input",
                "user_message",
                "",
            }:
                if text:
                    messages.append(
                        _message(
                            timestamp=record_timestamp,
                            ordinal=record_ordinal,
                            kind="user_message",
                            sender="user",
                            recipient=agent_path,
                            text=_antigravity_user_text(text),
                        )
                    )
                continue

            # PLANNER_RESPONSE is Antigravity's user-visible model surface. GENERIC
            # records are tool/runtime results (define_subagent, manage_subagents,
            # schedule, send_message acknowledgements, ...), so they must never be
            # eligible for the conversation Final response card.
            if role in {"model", "assistant"} and record_type == "planner_response":
                if text:
                    messages.append(
                        _message(
                            timestamp=record_timestamp,
                            ordinal=record_ordinal,
                            kind="assistant_message",
                            sender=agent_path,
                            recipient=None,
                            text=text,
                            phase="planner_response",
                        )
                    )
                continue
            continue

        record_timestamp = record.get("timestamp") or timestamp
        record_ordinal = record.get("ordinal")
        if not isinstance(record_ordinal, int):
            record_ordinal = (ordinal if isinstance(ordinal, int) else 0) + index
        record_type = str(record.get("type") or "").lower()
        payload = record.get("message")
        if isinstance(payload, dict):
            role = str(payload.get("role") or record_type).lower()
            text = _text_parts(payload.get("content"))
        else:
            role = record_type
            text = _text_parts(record.get("content") or record.get("text"))
        if not text:
            continue
        if role in {"user", "human"}:
            messages.append(
                _message(
                    timestamp=record_timestamp,
                    ordinal=record_ordinal,
                    kind="user_message",
                    sender="user",
                    recipient=agent_path,
                    text=text,
                )
            )
        elif role in {"assistant", "model"}:
            messages.append(
                _message(
                    timestamp=record_timestamp,
                    ordinal=record_ordinal,
                    kind="assistant_message",
                    sender=agent_path,
                    recipient=None,
                    text=text,
                    phase="response",
                )
            )
    return messages


'''
replace_between(
    "src/execweave/conversation_preview.py",
    "def _line_transcript_messages(\n",
    "def _response_messages(\n",
    NEW_LINE_TRANSCRIPT,
)
replace_once(
    "src/execweave/conversation_preview.py",
    '''    truncated = len(messages) > _MAX_PREVIEW_MESSAGES\n    if truncated:\n        messages = messages[:10] + messages[-(_MAX_PREVIEW_MESSAGES - 10) :]\n''',
    '''    preserve_history = content_kind.startswith("antigravity.conversation_transcript")\n    truncated = not preserve_history and len(messages) > _MAX_PREVIEW_MESSAGES\n    if truncated:\n        messages = messages[:10] + messages[-(_MAX_PREVIEW_MESSAGES - 10) :]\n''',
)

# Stable Antigravity message identities must follow the same live-wire filter.
NEW_AG_ORDINALS = r'''def _antigravity_step_ordinals(path: str | Path) -> list[int | None]:
    """Recover stable step indexes for user-visible Antigravity transcript records."""
    source_path = Path(path).expanduser().resolve(strict=False)
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []

    ordinals: list[int | None] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        role = str(record.get("source") or "").strip().lower()
        record_type = str(record.get("type") or "").strip().lower()
        text = _preview_module._text_parts(record.get("content") or record.get("text"))
        visible_user = role in {"user_explicit", "user", "human"} and record_type in {
            "user_input",
            "user_message",
            "",
        }
        visible_assistant = role in {"model", "assistant"} and record_type == "planner_response"
        if not text or not (visible_user or visible_assistant):
            continue
        record_ordinal = record.get("ordinal")
        if isinstance(record_ordinal, int) and not isinstance(record_ordinal, bool):
            ordinals.append(record_ordinal)
            continue
        step_index = record.get("step_index")
        ordinals.append(
            step_index
            if isinstance(step_index, int) and not isinstance(step_index, bool)
            else None
        )
    return ordinals


'''
replace_between(
    "src/execweave/conversation_records.py",
    "def _antigravity_step_ordinals(path: str | Path) -> list[int | None]:\n",
    "def _conversation_preview(\n",
    NEW_AG_ORDINALS,
)

# Restore complete user-facing histories after the legacy 80-message merge cap,
# and make root-only Ollama request records addressable by the actual run root agent.
INSERT_HISTORY = r'''
def _history_message_key(message: dict[str, Any]) -> tuple[object, ...]:
    return (
        message.get("ordinal"),
        message.get("kind"),
        message.get("sender"),
        message.get("recipient"),
        message.get("text"),
        message.get("content_state"),
        message.get("phase"),
        message.get("task_name"),
    )


def _restore_complete_histories(
    entries: list[dict[str, Any]],
    snapshots: list[tuple[dict[str, Any], dict[str, Any]]],
) -> None:
    """Never silently drop middle rounds for providers whose history is user-facing."""
    for entry in entries:
        provider = str(entry.get("provider") or "").lower()
        if provider not in {"antigravity", "ollama"}:
            continue
        merged = entry.get("conversation_preview")
        source_id = entry.get("source_id")
        if not isinstance(merged, dict) or not isinstance(source_id, str) or not source_id:
            continue
        observed: list[dict[str, Any]] = []
        for observed_entry, observed_preview in snapshots:
            if str(observed_entry.get("provider") or "").lower() != provider:
                continue
            if observed_entry.get("source_id") != source_id:
                continue
            for message in observed_preview.get("messages") or []:
                if isinstance(message, dict):
                    observed.append(dict(message))
        if not observed:
            continue
        indexed = list(enumerate(observed))
        indexed.sort(
            key=lambda pair: (
                str(pair[1].get("timestamp") or ""),
                pair[1].get("ordinal")
                if isinstance(pair[1].get("ordinal"), int)
                else 2**63 - 1,
                pair[0],
            )
        )
        seen: set[tuple[object, ...]] = set()
        messages: list[dict[str, Any]] = []
        for _, message in indexed:
            key = _history_message_key(message)
            if key in seen:
                continue
            seen.add(key)
            messages.append(message)
        merged["message_count"] = len(messages)
        merged["messages_truncated"] = False
        merged["messages"] = messages


def _ollama_current_turn(preview: dict[str, Any]) -> None:
    """Reduce a cumulative Ollama chat request to the one turn this request created."""
    messages = [message for message in preview.get("messages") or [] if isinstance(message, dict)]
    users = [message for message in messages if message.get("sender") == "user"]
    assistants = [
        message
        for message in messages
        if message.get("sender") != "user"
        and str(message.get("kind") or "").startswith("assistant")
    ]
    if not users:
        return
    current = [users[-1]]
    if assistants:
        current.append(assistants[-1])
    preview["message_count"] = len(current)
    preview["messages_truncated"] = False
    preview["messages"] = current


def _ollama_root_agent_id(graph: dict[str, Any]) -> str | None:
    candidates = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id.lower() == "agent:ollama":
            candidates.append(node_id)
    return candidates[0] if len(candidates) == 1 else None


'''
replace_once(
    "src/execweave/conversation_records.py",
    "def _merge_conversation_previews(entries: list[dict[str, Any]]) -> None:\n",
    INSERT_HISTORY + "def _merge_conversation_previews(entries: list[dict[str, Any]]) -> None:\n",
)
replace_once(
    "src/execweave/conversation_records.py",
    '''    _core_merge_conversation_previews(entries)\n    _repair_parent_thread_aliases(entries)\n\n    for entry in entries:\n''',
    '''    _core_merge_conversation_previews(entries)\n    _repair_parent_thread_aliases(entries)\n    _restore_complete_histories(entries, snapshots)\n\n    for entry in entries:\n''',
)

INSERT_RECORD_WRAPPER = r'''
_core_conversation_record_entries = _core.conversation_record_entries


def conversation_record_entries(
    graph: dict[str, Any],
    run_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Publish root-only Ollama turns under the one run root without changing raw evidence."""
    entries = _core_conversation_record_entries(graph, run_root)
    root_id = _ollama_root_agent_id(graph)
    if root_id is None:
        return entries

    normalized = False
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "ollama":
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict) or preview.get("is_root") is not True:
            continue
        if entry.get("source_type") != "inference_request":
            continue
        _ollama_current_turn(preview)
        original_source_id = entry.get("source_id")
        if isinstance(original_source_id, str) and original_source_id != root_id:
            entry["evidence_source_id"] = original_source_id
            entry["evidence_source_type"] = entry.get("source_type")
        entry["source_id"] = root_id
        entry["source_name"] = "Ollama"
        entry["source_type"] = "agent"
        normalized = True

    if normalized:
        _merge_conversation_previews(entries)
    return entries


'''
replace_once(
    "src/execweave/conversation_records.py",
    "# Functions defined in the core module resolve these globals at call time. Rebinding\n",
    INSERT_RECORD_WRAPPER + "# Functions defined in the core module resolve these globals at call time. Rebinding\n",
)
replace_once(
    "src/execweave/conversation_records.py",
    '''_core._merge_conversation_previews = _merge_conversation_previews\n''',
    '''_core._merge_conversation_previews = _merge_conversation_previews\n_core.conversation_record_entries = conversation_record_entries\n''',
)

# Antigravity full-fidelity hook-owned content must use the conversation-local identity.
replace_once(
    "src/execweave/antigravity_full_fidelity_base.py",
    '''def _agent() -> dict[str, Any]:\n    return {\n        "type": "agent",\n        "id": "agent:Antigravity",\n        "name": "Antigravity",\n        "attributes": {},\n    }\n''',
    '''def _agent(payload: dict[str, Any]) -> dict[str, Any]:\n    conversation_id = payload.get("conversationId")\n    if isinstance(conversation_id, str) and conversation_id:\n        return {\n            "type": "agent",\n            "id": f"agent:antigravity:conversation:{conversation_id}",\n            "name": "Antigravity conversation",\n            "attributes": {\n                "provider": "antigravity",\n                "conversation_id": conversation_id,\n                "identity_semantics": "provider_conversation_id",\n            },\n        }\n    return {\n        "type": "agent",\n        "id": "agent:Antigravity",\n        "name": "Antigravity",\n        "attributes": {"provider": "antigravity"},\n    }\n''',
)
text = read("src/execweave/antigravity_full_fidelity_base.py")
if text.count("source=_agent(),") != 3:
    raise SystemExit("antigravity_full_fidelity_base.py: expected three _agent() source calls")
write("src/execweave/antigravity_full_fidelity_base.py", text.replace("source=_agent(),", "source=_agent(payload),"))

# Ollama: canonicalize loopback aliases so localhost and 127.0.0.1 are one runtime.
replace_once(
    "src/execweave/model_runtime.py",
    '''    host = split.hostname\n    if ":" in host and not host.startswith("["):\n        host = f"[{host}]"\n''',
    '''    host = split.hostname\n    if host.lower() == "localhost" or host == "::1":\n        host = "127.0.0.1"\n    if ":" in host and not host.startswith("["):\n        host = f"[{host}]"\n''',
)

# Native Ollama generate responses use `response`, not chat `message.content`.
replace_once(
    "src/execweave/model_runtime_full_fidelity.py",
    '''    native = response.get("message")\n    if isinstance(native, dict):\n        messages.append(native)\n''',
    '''    native = response.get("message")\n    if isinstance(native, dict):\n        messages.append(native)\n    generated = response.get("response")\n    if isinstance(generated, str) and generated:\n        messages.append({"role": "assistant", "content": generated})\n''',
)

# Start the existing loopback-only Ollama relay before `ollama run` and pass the
# relay address only to the child environment. Remote endpoints and `ollama serve`
# remain untouched.
replace_once(
    "src/execweave/auto_specialized.py",
    '''def _is_ollama_serve(command: list[str]) -> bool:\n    return (\n        len(command) >= 2\n        and _command_name(command[0]) == "ollama"\n        and command[1].lower() == "serve"\n    )\n\n\n''',
    '''def _is_ollama_serve(command: list[str]) -> bool:\n    return (\n        len(command) >= 2\n        and _command_name(command[0]) == "ollama"\n        and command[1].lower() == "serve"\n    )\n\n\ndef _is_ollama_run(command: list[str]) -> bool:\n    return (\n        len(command) >= 2\n        and _command_name(command[0]) == "ollama"\n        and command[1].lower() == "run"\n    )\n\n\n''',
)

AUTO_LAUNCH = r'''
@contextmanager
def auto_specialized_launch(command: list[str]) -> Iterator[dict[str, str]]:
    """Prepare child-only launch wiring for supported transparent local integrations."""
    environment = dict(os.environ)
    configured_sidecar = os.environ.get(_SEMANTIC_ENV)
    if not configured_sidecar or not _is_ollama_run(command):
        yield environment
        return
    upstream = _ollama_endpoint_from_environment()
    if upstream is None:
        yield environment
        return

    from .http_proxy import ExecWeaveHTTPProxyServer, ProxyConfig

    sidecar = Path(configured_sidecar).expanduser().resolve()
    try:
        server = ExecWeaveHTTPProxyServer(
            ("127.0.0.1", 0),
            ProxyConfig(upstream=upstream, sidecar=sidecar, mode="ollama"),
        )
    except OSError:
        yield environment
        return
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name="execweave-ollama-run-relay",
        daemon=True,
    )
    thread.start()
    host, port = server.server_address[:2]
    environment["OLLAMA_HOST"] = f"http://{host}:{port}"
    try:
        yield environment
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


'''
replace_once(
    "src/execweave/auto_specialized.py",
    "@contextmanager\ndef auto_specialized_probe(command: list[str]) -> Iterator[None]:\n",
    AUTO_LAUNCH + "@contextmanager\ndef auto_specialized_probe(command: list[str]) -> Iterator[None]:\n",
)

# Portable collector launch path.
replace_once(
    "src/execweave/collector.py",
    '''from .auto_specialized import (\n    auto_specialized_probe,\n''',
    '''from .auto_specialized import (\n    auto_specialized_launch,\n    auto_specialized_probe,\n''',
)
replace_once(
    "src/execweave/collector.py",
    '''        "opencode": "OpenCode",\n''',
    '''        "opencode": "OpenCode",\n        "ollama": "Ollama",\n''',
)
OLD_PORTABLE = '''            process = subprocess.Popen(launch_command, cwd=str(self.watch_root))\n            root = psutil.Process(process.pid)\n            snapshot = _safe_process_snapshot(root)\n            if snapshot is not None:\n                self._record_process_start(snapshot, parent=session, relation="LAUNCHED")\n\n            with auto_specialized_probe(command):\n                while process.poll() is None:\n                    self._sample_process_tree(root)\n                    time.sleep(self.poll_interval)\n\n                self._sample_process_tree(root)\n                self._mark_disappeared_processes(set())\n            return_code = int(process.returncode or 0)\n'''
NEW_PORTABLE = '''            with auto_specialized_launch(command) as launch_environment:\n                process = subprocess.Popen(\n                    launch_command,\n                    cwd=str(self.watch_root),\n                    env=launch_environment,\n                )\n                root = psutil.Process(process.pid)\n                snapshot = _safe_process_snapshot(root)\n                if snapshot is not None:\n                    self._record_process_start(snapshot, parent=session, relation="LAUNCHED")\n\n                with auto_specialized_probe(command):\n                    while process.poll() is None:\n                        self._sample_process_tree(root)\n                        time.sleep(self.poll_interval)\n\n                    self._sample_process_tree(root)\n                    self._mark_disappeared_processes(set())\n                return_code = int(process.returncode or 0)\n'''
replace_once("src/execweave/collector.py", OLD_PORTABLE, NEW_PORTABLE)

# Linux strace launch path must pass the same child-only relay environment.
replace_once(
    "src/execweave/strace_backend.py",
    "from .collector import infer_agent_name\n",
    "from .auto_specialized import auto_specialized_launch\nfrom .collector import infer_agent_name\n",
)
replace_once(
    "src/execweave/strace_backend.py",
    '''            completed = subprocess.run(strace_command, cwd=str(self.watch_root), check=False)\n''',
    '''            with auto_specialized_launch(command) as launch_environment:\n                completed = subprocess.run(\n                    strace_command,\n                    cwd=str(self.watch_root),\n                    env=launch_environment,\n                    check=False,\n                )\n''',
)

# Dashboard presentation: keep raw evidence separate, but show one owner node when the
# alias is unambiguous. The edge remap is presentation-only.
replace_once(
    "src/execweave/viewer_dashboard_focus.py",
    "const providerRootIds=new Set(['agent:Claude Code','agent:OpenAI Codex','agent:Codex','agent:Cursor','agent:OpenCode','agent:Gemini CLI','agent:Antigravity']);",
    "const providerRootIds=new Set(['agent:Claude Code','agent:OpenAI Codex','agent:Codex','agent:Cursor','agent:OpenCode','agent:Gemini CLI','agent:Antigravity','agent:Ollama','agent:ollama']);",
)
replace_once(
    "src/execweave/viewer_dashboard_focus.py",
    "  const prepared=before.filter(node=>node&&!hiddenTypes.has(String(node.type||''))).map(node=>{\n",
    "  let prepared=before.filter(node=>node&&!hiddenTypes.has(String(node.type||''))).map(node=>{\n",
)
ALIAS_JS = r'''  const presentationAlias=new Map();
  const antigravityRoot=prepared.find(node=>String(node?.id||'')==='agent:Antigravity');
  const antigravityMains=prepared.filter(node=>{
    const attrs=node?.attributes||{};
    return node?.type==='agent'&&String(attrs.provider||'').toLowerCase()==='antigravity'&&
      String(node.id||'').startsWith('agent:antigravity:conversation:')&&!String(attrs.parent_agent_path||'').trim();
  });
  if(antigravityRoot&&antigravityMains.length===1){
    const main=antigravityMains[0];presentationAlias.set(antigravityRoot.id,main.id);
    prepared=prepared.filter(node=>node.id!==antigravityRoot.id).map(node=>node.id===main.id?{...node,name:'/root'}:node);
  }
  const ollamaRoots=prepared.filter(node=>node?.type==='agent'&&['agent:Ollama','agent:ollama'].includes(String(node.id||'')));
  const ollamaRuntimes=prepared.filter(node=>node?.type==='model_runtime'&&String(node?.attributes?.provider||'').toLowerCase()==='ollama');
  if(ollamaRoots.length===1&&ollamaRuntimes.length===1){
    const root=ollamaRoots[0],runtime=ollamaRuntimes[0];presentationAlias.set(runtime.id,root.id);
    prepared=prepared.filter(node=>node.id!==runtime.id).map(node=>node.id===root.id?{...node,name:'/root'}:node);
  }
'''
replace_once(
    "src/execweave/viewer_dashboard_focus.py",
    "  });\n  const normalized=value=>String(value||'').trim().replaceAll('\\\\\\\\','/').replace(/\\/+$/,'').toLowerCase();\n",
    "  });\n" + ALIAS_JS + "  const normalized=value=>String(value||'').trim().replaceAll('\\\\\\\\','/').replace(/\\/+$/,'').toLowerCase();\n",
)
replace_once(
    "src/execweave/viewer_dashboard_focus.py",
    "  const canonicalId=new Map(),nodes=[];let mergedContextNodeCount=0;\n",
    "  const canonicalId=new Map(presentationAlias),nodes=[];let mergedContextNodeCount=0;\n",
)

replace_once(
    "src/execweave/viewer_agent_panel.py",
    "const ROOT_NODE_IDS=new Set(['agent:Claude Code','agent:OpenAI Codex','agent:Codex','agent:Cursor','agent:OpenCode','agent:Gemini CLI','agent:Antigravity']);",
    "const ROOT_NODE_IDS=new Set(['agent:Claude Code','agent:OpenAI Codex','agent:Codex','agent:Cursor','agent:OpenCode','agent:Gemini CLI','agent:Antigravity','agent:Ollama','agent:ollama']);",
)

# New additive regression file: do not mutate the repository's historical test nodes.
TESTS = r'''from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from execweave.auto_specialized import auto_specialized_launch
from execweave.content_evidence import content_observation_event
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import conversation_record_entries
from execweave.graph import GraphAccumulator
from execweave.model_runtime import sanitize_endpoint
from execweave.model_runtime_full_fidelity import runtime_exchange_to_content_events
from execweave.viewer_projection import write_graph_html


def _agent(conversation_id: str) -> dict[str, object]:
    return {
        "type": "agent",
        "id": f"agent:antigravity:conversation:{conversation_id}",
        "name": "Antigravity conversation",
        "attributes": {"provider": "antigravity", "conversation_id": conversation_id},
    }


def _agy_records(rounds: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    step = 0
    for index in range(rounds):
        rows.append({
            "step_index": step,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": f"2026-09-01T01:{index:02d}:00Z",
            "content": f"<USER_REQUEST>\\nquestion {index}\\n</USER_REQUEST>\\n<ADDITIONAL_METADATA>hidden {index}</ADDITIONAL_METADATA>",
        })
        step += 1
        rows.append({
            "step_index": step,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": f"2026-09-01T01:{index:02d}:01Z",
            "content": f"answer {index}",
        })
        step += 1
        rows.append({
            "step_index": step,
            "source": "MODEL",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": f"2026-09-01T01:{index:02d}:02Z",
            "content": f"TOOL RESULT MUST NOT BE FINAL {index}",
        })
        step += 1
    return rows


def _agy_graph(tmp_path: Path, rounds: int) -> tuple[dict[str, object], Path]:
    run_root = tmp_path / "run"
    store = FullFidelityContentStore(run_root)
    transcript = tmp_path / "transcript_full.jsonl"
    transcript.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\\n" for row in _agy_records(rounds)),
        encoding="utf-8",
    )
    reference = store.put_file(
        transcript,
        content_kind="antigravity.conversation_transcript",
        media_type="text/plain; charset=utf-8",
        representation="provider_transcript_jsonl_snapshot",
    )
    event = content_observation_event(
        timestamp="2026-09-01T02:00:00Z",
        provider="antigravity",
        source=_agent("main-real-wire"),
        reference=reference,
        relation="HAS_CONVERSATION_TRANSCRIPT",
        observed_field="transcriptPath",
        evidence_source="provider_transcript",
        attribution="antigravity_hook",
    )
    graph = GraphAccumulator(session_id="agy-real-wire", source_path=run_root / "events.jsonl")
    graph.apply(event)
    materialized = graph.to_dict()
    materialized["nodes"].append({
        "id": "agent:Antigravity",
        "type": "agent",
        "name": "Antigravity",
        "attributes": {"provider": "antigravity"},
    })
    return materialized, run_root


def _preview(entries: list[dict[str, object]], provider: str) -> dict[str, object]:
    previews = [
        entry["conversation_preview"]
        for entry in entries
        if entry.get("provider") == provider and isinstance(entry.get("conversation_preview"), dict)
    ]
    assert len(previews) == 1
    return previews[0]


def test_antigravity_real_wire_uses_user_explicit_and_rejects_generic_tool_results(tmp_path: Path) -> None:
    graph, run_root = _agy_graph(tmp_path, 3)
    preview = _preview(conversation_record_entries(graph, run_root), "antigravity")
    messages = preview["messages"]
    assert [message["text"] for message in messages] == [
        "question 0", "answer 0", "question 1", "answer 1", "question 2", "answer 2"
    ]
    assert [message["ordinal"] for message in messages] == [0, 1, 3, 4, 6, 7]
    assert all("ADDITIONAL_METADATA" not in str(message["text"]) for message in messages)
    assert all("TOOL RESULT MUST NOT BE FINAL" not in str(message["text"]) for message in messages)


def test_antigravity_middle_rounds_survive_more_than_eighty_visible_messages(tmp_path: Path) -> None:
    graph, run_root = _agy_graph(tmp_path, 50)
    preview = _preview(conversation_record_entries(graph, run_root), "antigravity")
    texts = [message["text"] for message in preview["messages"]]
    assert len(texts) == 100
    assert "question 25" in texts and "answer 25" in texts
    assert preview["messages_truncated"] is False


def test_loopback_ollama_endpoint_aliases_have_one_identity() -> None:
    assert sanitize_endpoint("http://localhost:11434") == "http://127.0.0.1:11434"
    assert sanitize_endpoint("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert sanitize_endpoint("http://[::1]:11434") == "http://127.0.0.1:11434"


def _ollama_graph(tmp_path: Path, rounds: int = 3) -> tuple[dict[str, object], Path]:
    run_root = tmp_path / "ollama-run"
    store = FullFidelityContentStore(run_root)
    graph = GraphAccumulator(session_id="ollama-history", source_path=run_root / "events.jsonl")
    history: list[dict[str, str]] = []
    for index in range(rounds):
        history.append({"role": "user", "content": f"ollama question {index}"})
        request_history = [dict(message) for message in history]
        response = {"model": "tiny", "message": {"role": "assistant", "content": f"ollama answer {index}"}, "done": True}
        for event in runtime_exchange_to_content_events(
            {"request": {"model": "tiny", "messages": request_history}, "response": response},
            store=store,
            runtime="ollama",
            endpoint="http://localhost:11434",
            request_id=f"turn-{index}",
            timestamp=f"2026-09-01T03:0{index}:00Z",
        ):
            graph.apply(event)
        history.append({"role": "assistant", "content": f"ollama answer {index}"})
    materialized = graph.to_dict()
    materialized["nodes"].extend([
        {"id": "agent:Ollama", "type": "agent", "name": "Ollama", "attributes": {"provider": "ollama"}},
        {"id": "model-runtime:ollama:viewer-duplicate", "type": "model_runtime", "name": "ollama", "attributes": {"provider": "ollama", "endpoint": "http://127.0.0.1:11434"}},
        {"id": "model:ollama:tiny", "type": "model", "name": "tiny", "attributes": {"provider": "ollama"}},
    ])
    materialized["edges"].append({
        "id": "runtime-model",
        "source": "model-runtime:ollama:viewer-duplicate",
        "target": "model:ollama:tiny",
        "relation": "LOADED_MODEL",
        "count": 1,
    })
    return materialized, run_root


def test_ollama_cumulative_chat_requests_publish_one_new_round_each(tmp_path: Path) -> None:
    graph, run_root = _ollama_graph(tmp_path)
    entries = conversation_record_entries(graph, run_root)
    preview = _preview(entries, "ollama")
    texts = [message["text"] for message in preview["messages"]]
    assert texts == [
        "ollama question 0", "ollama answer 0",
        "ollama question 1", "ollama answer 1",
        "ollama question 2", "ollama answer 2",
    ]
    owner = next(entry for entry in entries if isinstance(entry.get("conversation_preview"), dict))
    assert owner["source_id"] == "agent:Ollama"


def test_ollama_generate_response_becomes_assistant_message(tmp_path: Path) -> None:
    run_root = tmp_path / "generate"
    store = FullFidelityContentStore(run_root)
    graph = GraphAccumulator(session_id="ollama-generate", source_path=run_root / "events.jsonl")
    for event in runtime_exchange_to_content_events(
        {"request": {"model": "tiny", "prompt": "generate prompt"}, "response": {"model": "tiny", "response": "generate answer", "done": True}},
        store=store,
        runtime="ollama",
        endpoint="http://localhost:11434",
        request_id="generate-1",
        timestamp="2026-09-01T04:00:00Z",
    ):
        graph.apply(event)
    materialized = graph.to_dict()
    materialized["nodes"].append({"id": "agent:Ollama", "type": "agent", "name": "Ollama", "attributes": {"provider": "ollama"}})
    preview = _preview(conversation_record_entries(materialized, run_root), "ollama")
    assert [message["text"] for message in preview["messages"]] == ["generate prompt", "generate answer"]


class _OllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        payload = {
            "model": body.get("model", "tiny"),
            "message": {"role": "assistant", "content": "relay answer"},
            "done": True,
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def test_ollama_run_launch_uses_loopback_relay_and_records_exchange(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaHandler)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    sidecar = tmp_path / "events.semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{upstream.server_port}")
    try:
        with auto_specialized_launch(["ollama", "run", "tiny"]) as environment:
            assert environment["OLLAMA_HOST"] != os.environ["OLLAMA_HOST"]
            request = Request(
                environment["OLLAMA_HOST"] + "/api/chat",
                data=json.dumps({"model": "tiny", "messages": [{"role": "user", "content": "relay prompt"}]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                assert json.loads(response.read().decode("utf-8"))["message"]["content"] == "relay answer"
        rows = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines() if line.strip()]
        kinds = {
            (row.get("target", {}).get("attributes") or {}).get("content_kind")
            for row in rows
            if isinstance(row, dict)
        }
        assert "model_runtime.ollama.request_messages" in kinds
        assert "model_runtime.ollama.assistant_messages" in kinds
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=2)


def test_ollama_serve_and_remote_hosts_are_not_relayed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    original = dict(os.environ)
    with auto_specialized_launch(["ollama", "serve"]) as environment:
        assert environment.get("OLLAMA_HOST") == original.get("OLLAMA_HOST")
    monkeypatch.setenv("OLLAMA_HOST", "http://192.0.2.10:11434")
    with auto_specialized_launch(["ollama", "run", "tiny"]) as environment:
        assert environment["OLLAMA_HOST"] == "http://192.0.2.10:11434"


def _required_browser(playwright: object):
    try:
        return playwright.chromium.launch()
    except Exception as error:  # noqa: BLE001
        if os.environ.get("EXECWEAVE_E2E_REQUIRED", "").lower() not in {"", "0", "false"}:
            pytest.fail(f"Chromium required for conversation-integrity gate: {error}")
        pytest.skip(f"Chromium unavailable: {error}")


@pytest.mark.viewer_e2e
def test_antigravity_real_wire_dashboard_has_one_main_node_and_folded_history(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    graph, run_root = _agy_graph(tmp_path, 3)
    viewer = run_root / "viewer.html"
    write_graph_html(graph, viewer)
    with sync_api.sync_playwright() as playwright:
        browser = _required_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node")
            visible_ids = page.eval_on_selector_all(".node", "nodes=>nodes.map(node=>node.dataset.id)")
            assert "agent:Antigravity" not in visible_ids
            assert "agent:antigravity:conversation:main-real-wire" in visible_ids
            page.eval_on_selector(
                '.node[data-id="agent:antigravity:conversation:main-real-wire"]',
                "node=>node.dispatchEvent(new MouseEvent('click',{bubbles:true}))",
            )
            page.wait_for_function("()=>(document.getElementById('details')?.innerText||'').includes('question 2')")
            details = page.locator("#details")
            assert details.locator(".execweave-agent-older").count() == 2
            text = details.inner_text()
            assert "answer 2" in text
            assert "TOOL RESULT MUST NOT BE FINAL" not in text
            first = details.locator(".execweave-agent-older").first
            first.locator("summary").click()
            assert first.evaluate("node=>node.open")
            page.evaluate("entries=>window.__execweaveAgentPanel.setEntries(entries)", conversation_record_entries(graph, run_root))
            assert details.locator(".execweave-agent-older").first.evaluate("node=>node.open")
        finally:
            browser.close()


@pytest.mark.viewer_e2e
def test_ollama_dashboard_has_one_owner_node_and_folded_history(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    graph, run_root = _ollama_graph(tmp_path)
    viewer = run_root / "viewer.html"
    write_graph_html(graph, viewer)
    with sync_api.sync_playwright() as playwright:
        browser = _required_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node")
            visible_ids = page.eval_on_selector_all(".node", "nodes=>nodes.map(node=>node.dataset.id)")
            assert "model-runtime:ollama:viewer-duplicate" not in visible_ids
            assert "agent:Ollama" in visible_ids
            page.eval_on_selector(
                '.node[data-id="agent:Ollama"]',
                "node=>node.dispatchEvent(new MouseEvent('click',{bubbles:true}))",
            )
            page.wait_for_function("()=>(document.getElementById('details')?.innerText||'').includes('ollama question 2')")
            details = page.locator("#details")
            assert details.locator(".execweave-agent-older").count() == 2
            assert "ollama answer 2" in details.inner_text()
        finally:
            browser.close()
'''
write("tests/test_provider_conversation_history_integrity.py", TESTS)

# Static safety checks on the staged patch itself.
for path in (
    "src/execweave/conversation_preview.py",
    "src/execweave/conversation_records.py",
    "src/execweave/antigravity_full_fidelity_base.py",
    "src/execweave/model_runtime.py",
    "src/execweave/model_runtime_full_fidelity.py",
    "src/execweave/auto_specialized.py",
    "src/execweave/collector.py",
    "src/execweave/strace_backend.py",
    "src/execweave/viewer_dashboard_focus.py",
    "src/execweave/viewer_agent_panel.py",
    "tests/test_provider_conversation_history_integrity.py",
):
    compile(read(path), path, "exec")

print("conversation-integrity patch applied")
