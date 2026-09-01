from pathlib import Path

# Keep parent_scope_id in raw graph topology, not in the published preview schema.
path = Path("src/execweave/conversation_preview.py")
text = path.read_text(encoding="utf-8")
added = '''        "agent_nickname": (
            attrs.get("agent_nickname")
            if isinstance(attrs.get("agent_nickname"), str)
            else None
        ),
        "parent_scope_id": (
            attrs.get("parent_scope_id")
            if isinstance(attrs.get("parent_scope_id"), str)
            else None
        ),
        **topology.to_dict(),
'''
original = '''        "agent_nickname": (
            attrs.get("agent_nickname")
            if isinstance(attrs.get("agent_nickname"), str)
            else None
        ),
        **topology.to_dict(),
'''
if text.count(added) != 1:
    raise SystemExit("expected temporary parent_scope preview patch")
path.write_text(text.replace(added, original, 1), encoding="utf-8")

path = Path("src/execweave/conversation_records.py")
text = path.read_text(encoding="utf-8")
start = text.index("def _project_antigravity_addressed_tasks(")
end = text.index("def _restore_complete_histories(", start)
helper = '''def _project_antigravity_addressed_tasks(
    entries: list[dict[str, Any]],
    graph: dict[str, Any],
) -> None:
    """Project exact parent-addressed send_message text into the child timeline.

    Raw Antigravity topology already carries positive ``parent_scope_id`` evidence on
    each validated child node. Raw send_message conversation evidence carries exact
    provider sender and recipient conversation IDs. Join those two facts only for
    presentation: an addressed parent message becomes a child task opener, while raw
    evidence remains unchanged and delivery/consumption remain explicitly unobserved.
    """
    prefix = "agent:antigravity:conversation:"
    topology: dict[str, tuple[str, str]] = {}
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        node_id = node.get("id")
        attrs = node.get("attributes")
        attrs = attrs if isinstance(attrs, dict) else {}
        if not isinstance(node_id, str) or not node_id.startswith(prefix):
            continue
        if str(attrs.get("provider") or "").lower() != "antigravity":
            continue
        parent_path = attrs.get("parent_agent_path")
        parent_scope = attrs.get("parent_scope_id")
        if not isinstance(parent_path, str) or not parent_path:
            continue
        if not isinstance(parent_scope, str) or not parent_scope:
            continue
        topology[node_id.removeprefix(prefix)] = (parent_scope, parent_path)

    children: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "antigravity":
            continue
        source_id = entry.get("source_id")
        preview = entry.get("conversation_preview")
        if not isinstance(source_id, str) or not source_id.startswith(prefix):
            continue
        child_id = source_id.removeprefix(prefix)
        if child_id not in topology or not isinstance(preview, dict):
            continue
        children[child_id] = entry

    additions: dict[str, list[dict[str, Any]]] = {child_id: [] for child_id in children}
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "antigravity":
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        for message in preview.get("messages") or []:
            if not isinstance(message, dict) or message.get("kind") != "send_message":
                continue
            sender = message.get("sender")
            recipient = message.get("recipient")
            if not isinstance(sender, str) or not sender.startswith("antigravity:"):
                continue
            if not isinstance(recipient, str) or not recipient.startswith("antigravity:"):
                continue
            sender_id = sender.removeprefix("antigravity:")
            child_id = recipient.removeprefix("antigravity:")
            child_entry = children.get(child_id)
            if child_entry is None:
                continue
            parent_scope, parent_path = topology[child_id]
            if sender_id != parent_scope:
                # Exact sibling/other-agent messages are messages, not parent tasks.
                continue
            child_preview = child_entry["conversation_preview"]
            task = dict(message)
            task.update(
                {
                    "kind": "task",
                    "phase": "assignment",
                    "sender": parent_path,
                    "recipient": str(child_preview.get("agent_path") or ""),
                    "content_role": "antigravity_addressed_task",
                    "provider_sender_id": sender_id,
                    "provider_recipient_id": child_id,
                    "delivery_observed": False,
                    "consumption_observed": False,
                }
            )
            additions[child_id].append(task)

    for child_id, tasks in additions.items():
        if not tasks:
            continue
        preview = children[child_id]["conversation_preview"]
        combined = [
            dict(message)
            for message in preview.get("messages") or []
            if isinstance(message, dict)
        ] + tasks
        combined.sort(
            key=lambda message: (
                str(message.get("timestamp") or ""),
                message.get("ordinal")
                if isinstance(message.get("ordinal"), int)
                else 2**63 - 1,
            )
        )
        seen: set[tuple[object, ...]] = set()
        messages: list[dict[str, Any]] = []
        for message in combined:
            key = _history_message_key(message)
            if key in seen:
                continue
            seen.add(key)
            messages.append(message)
        preview["message_count"] = len(messages)
        preview["messages_truncated"] = False
        preview["messages"] = messages


'''
text = text[:start] + helper + text[end:]
old_merge_call = "    _project_antigravity_addressed_tasks(entries, snapshots)\n"
if text.count(old_merge_call) != 1:
    raise SystemExit("temporary merge projection call not found")
text = text.replace(old_merge_call, "", 1)
old_wrapper = '''    entries = _core_conversation_record_entries(graph, run_root)
    root_id = _ollama_root_agent_id(graph)
'''
new_wrapper = '''    entries = _core_conversation_record_entries(graph, run_root)
    _project_antigravity_addressed_tasks(entries, graph)
    root_id = _ollama_root_agent_id(graph)
'''
if text.count(old_wrapper) != 1:
    raise SystemExit("public conversation_record_entries insertion point changed")
text = text.replace(old_wrapper, new_wrapper, 1)
path.write_text(text, encoding="utf-8")
