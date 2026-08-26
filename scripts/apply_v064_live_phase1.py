from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def update_semantic() -> None:
    path = ROOT / "src/execweave/semantic.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    finished_at: datetime,\n",
        "    finished_at: datetime | None,\n",
        label="semantic finished_at type",
    )
    text = replace_once(
        text,
        "    if timestamp < started_at or timestamp > finished_at:\n"
        "        raise ValueError(f\"{context}: timestamp is outside the runtime session interval\")\n",
        "    if timestamp < started_at:\n"
        "        raise ValueError(f\"{context}: timestamp precedes the runtime session start\")\n"
        "    if finished_at is not None and timestamp > finished_at:\n"
        "        raise ValueError(f\"{context}: timestamp is outside the runtime session interval\")\n",
        label="semantic timestamp bounds",
    )

    marker = "\n\ndef merge_semantic_sidecar(\n"
    live_normalizer = '''\n\nclass LiveSemanticNormalizer:\n    \"\"\"Normalize append-only semantic records for disposable live graph state.\n\n    This helper is intentionally conservative. It only resolves process references\n    against process identities already observed in the runtime stream. The canonical\n    final artifact is still rebuilt with :func:`merge_semantic_sidecar`, which sees\n    the complete runtime session and is therefore authoritative.\n    \"\"\"\n\n    def __init__(self, session_id: str) -> None:\n        self.session_id = session_id\n        self._started_at: datetime | None = None\n        self._candidates: dict[int, dict[str, _ProcessCandidate]] = {}\n\n    @property\n    def ready(self) -> bool:\n        return self._started_at is not None\n\n    def reset(self) -> None:\n        self._started_at = None\n        self._candidates.clear()\n\n    def observe_runtime_event(self, event: dict[str, Any]) -> None:\n        if event.get(\"event_type\") == \"session.started\":\n            self._started_at = _parse_timestamp(\n                event.get(\"timestamp\"),\n                context=\"live session.started\",\n            )\n\n        for entity in (event.get(\"source\"), event.get(\"target\")):\n            if not isinstance(entity, dict) or entity.get(\"type\") != \"process\":\n                continue\n            entity_id = entity.get(\"id\")\n            attributes = entity.get(\"attributes\") or {}\n            if not isinstance(entity_id, str) or not isinstance(attributes, dict):\n                continue\n            pid = attributes.get(\"pid\")\n            if not isinstance(pid, int) or isinstance(pid, bool):\n                continue\n            create_time_raw = attributes.get(\"create_time\")\n            create_time = (\n                float(create_time_raw)\n                if isinstance(create_time_raw, (int, float))\n                and not isinstance(create_time_raw, bool)\n                else None\n            )\n            self._candidates.setdefault(pid, {})[entity_id] = _ProcessCandidate(\n                pid=pid,\n                entity=deepcopy(entity),\n                create_time=create_time,\n            )\n\n    def normalize(\n        self,\n        record: dict[str, Any],\n        *,\n        line_number: int,\n    ) -> dict[str, Any] | None:\n        if self._started_at is None:\n            return None\n        candidates = {\n            pid: list(by_id.values()) for pid, by_id in self._candidates.items()\n        }\n        normalized, _, _ = _normalize_semantic_record(\n            record,\n            line_number=line_number,\n            session_id=self.session_id,\n            started_at=self._started_at,\n            finished_at=None,\n            candidates=candidates,\n        )\n        attributes = normalized.get(\"attributes\")\n        if isinstance(attributes, dict):\n            attributes[\"live_normalization_provisional\"] = True\n        return normalized\n'''
    text = replace_once(text, marker, live_normalizer + marker, label="semantic live normalizer")
    path.write_text(text, encoding="utf-8")


def update_live() -> None:
    path = ROOT / "src/execweave/live.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "import json\n", "import json\nimport os\n", label="live os import")
    text = replace_once(
        text,
        "from .live_view import LIVE_HTML as _LIVE_HTML\nfrom .sink import JsonlSink\n",
        "from .live_view import LIVE_HTML as _LIVE_HTML\n"
        "from .semantic import LiveSemanticNormalizer, merge_semantic_sidecar\n"
        "from .sink import JsonlSink\n",
        label="live semantic imports",
    )
    text = replace_once(
        text,
        "LIVE_DELTA_HISTORY_BYTES = 8 * 1024 * 1024\n",
        "LIVE_DELTA_HISTORY_BYTES = 8 * 1024 * 1024\n"
        "_SEMANTIC_ENV = \"EXECWEAVE_SEMANTIC_SIDECAR\"\n",
        label="live semantic env",
    )
    text = replace_once(
        text,
        "    event_stream: Path\n    graph: Path\n    viewer: Path\n",
        "    event_stream: Path\n"
        "    semantic_sidecar: Path\n"
        "    materialized_event_stream: Path\n"
        "    graph: Path\n"
        "    viewer: Path\n",
        label="LiveResult fields",
    )
    text = replace_once(
        text,
        '            "event_stream": str(self.event_stream),\n'
        '            "graph": str(self.graph),\n',
        '            "event_stream": str(self.event_stream),\n'
        '            "semantic_sidecar": str(self.semantic_sidecar),\n'
        '            "materialized_event_stream": str(self.materialized_event_stream),\n'
        '            "graph": str(self.graph),\n',
        label="LiveResult serialization",
    )

    marker = "\n\nclass _LiveState:\n"
    tail_type = '''\n\n@dataclass\nclass _JsonlTail:\n    path: Path\n    offset: int = 0\n    pending_bytes: bytes = b\"\"\n    records_seen: int = 0\n'''
    text = replace_once(text, marker, tail_type + marker, label="live tail cursor")

    old_init = '''class _LiveState:\n    def __init__(self, session_id: str, event_path: Path) -> None:\n        self.session_id = session_id\n        self.event_path = event_path\n        self._lock = threading.Lock()\n        self._accumulator = GraphAccumulator(\n            session_id=session_id,\n            source_path=event_path,\n            retain_event_ids=False,\n        )\n        self._read_offset = 0\n        self._pending_bytes = b\"\"\n        self._finished = False\n'''
    new_init = '''class _LiveState:\n    def __init__(\n        self,\n        session_id: str,\n        event_path: Path,\n        semantic_path: Path | None = None,\n    ) -> None:\n        self.session_id = session_id\n        self.event_path = event_path\n        self.semantic_path = semantic_path\n        self._lock = threading.Lock()\n        self._accumulator = GraphAccumulator(\n            session_id=session_id,\n            source_path=event_path,\n            retain_event_ids=False,\n        )\n        self._runtime_tail = _JsonlTail(event_path)\n        self._semantic_tail = _JsonlTail(semantic_path) if semantic_path is not None else None\n        self._semantic_normalizer = LiveSemanticNormalizer(session_id)\n        self._runtime_event_count = 0\n        self._specialized_event_count = 0\n        self._finished = False\n'''
    text = replace_once(text, old_init, new_init, label="LiveState init")

    old_reset = '''    def _reset_incremental_state_locked(self) -> None:\n        self._accumulator = GraphAccumulator(\n            session_id=self.session_id,\n            source_path=self.event_path,\n            retain_event_ids=False,\n        )\n        self._read_offset = 0\n        self._pending_bytes = b\"\"\n        self._clear_update_history_locked()\n        self._update_sequence += 1\n        self._resync_floor = self._update_sequence\n'''
    new_reset = '''    def _reset_incremental_state_locked(self) -> None:\n        self._accumulator = GraphAccumulator(\n            session_id=self.session_id,\n            source_path=self.event_path,\n            retain_event_ids=False,\n        )\n        tails = [self._runtime_tail]\n        if self._semantic_tail is not None:\n            tails.append(self._semantic_tail)\n        for tail in tails:\n            tail.offset = 0\n            tail.pending_bytes = b\"\"\n            tail.records_seen = 0\n        self._semantic_normalizer.reset()\n        self._runtime_event_count = 0\n        self._specialized_event_count = 0\n        self._clear_update_history_locked()\n        self._update_sequence += 1\n        self._resync_floor = self._update_sequence\n'''
    text = replace_once(text, old_reset, new_reset, label="LiveState reset")

    start = text.index("    def _refresh_incremental_locked(self) -> None:\n")
    end = text.index("    def snapshot(self) -> dict[str, object]:\n", start)
    new_refresh = '''    def _tail_truncated_locked(self, tail: _JsonlTail) -> bool:\n        try:\n            return tail.path.stat().st_size < tail.offset\n        except OSError:\n            return False\n\n    def _read_tail_records_locked(\n        self,\n        tail: _JsonlTail,\n    ) -> list[tuple[int, dict[str, object]]]:\n        try:\n            file_size = tail.path.stat().st_size\n        except OSError:\n            return []\n        if file_size <= tail.offset:\n            return []\n        try:\n            with tail.path.open(\"rb\") as handle:\n                handle.seek(tail.offset)\n                chunk = handle.read()\n        except OSError:\n            return []\n        if not chunk:\n            return []\n        tail.offset += len(chunk)\n        buffered = tail.pending_bytes + chunk\n        lines = buffered.split(b\"\\n\")\n        tail.pending_bytes = lines.pop()\n        records: list[tuple[int, dict[str, object]]] = []\n        for raw_line in lines:\n            if not raw_line.strip():\n                continue\n            tail.records_seen += 1\n            try:\n                payload = json.loads(raw_line.decode(\"utf-8\"))\n            except (UnicodeDecodeError, json.JSONDecodeError):\n                continue\n            if isinstance(payload, dict):\n                records.append((tail.records_seen, payload))\n        return records\n\n    def _apply_live_event_locked(\n        self,\n        event: dict[str, object],\n        *,\n        added_nodes: set[str],\n        updated_nodes: set[str],\n        added_edges: set[tuple[str, str, str]],\n        updated_edges: set[tuple[str, str, str]],\n    ) -> bool:\n        source_id = _entity_id(event.get(\"source\"))\n        target_id = _entity_id(event.get(\"target\"))\n        node_ids = {value for value in (source_id, target_id) if value}\n        existing_nodes = {\n            node_id for node_id in node_ids if node_id in self._accumulator.nodes\n        }\n        edge_key = _event_edge_key(event)\n        edge_existed = edge_key in self._accumulator.edges if edge_key is not None else False\n        try:\n            self._accumulator.apply(event)\n        except (TypeError, ValueError):\n            return False\n\n        for node_id in node_ids:\n            if node_id in existing_nodes and node_id not in added_nodes:\n                updated_nodes.add(node_id)\n            else:\n                added_nodes.add(node_id)\n                updated_nodes.discard(node_id)\n        if edge_key is not None and edge_key in self._accumulator.edges:\n            if edge_existed and edge_key not in added_edges:\n                updated_edges.add(edge_key)\n            else:\n                added_edges.add(edge_key)\n                updated_edges.discard(edge_key)\n        return True\n\n    def _refresh_incremental_locked(self) -> None:\n        tails = [self._runtime_tail]\n        if self._semantic_tail is not None:\n            tails.append(self._semantic_tail)\n        if any(self._tail_truncated_locked(tail) for tail in tails):\n            self._reset_incremental_state_locked()\n\n        added_nodes: set[str] = set()\n        updated_nodes: set[str] = set()\n        added_edges: set[tuple[str, str, str]] = set()\n        updated_edges: set[tuple[str, str, str]] = set()\n        runtime_applied = 0\n        specialized_applied = 0\n\n        for _, event in self._read_tail_records_locked(self._runtime_tail):\n            if not self._apply_live_event_locked(\n                event,\n                added_nodes=added_nodes,\n                updated_nodes=updated_nodes,\n                added_edges=added_edges,\n                updated_edges=updated_edges,\n            ):\n                continue\n            self._semantic_normalizer.observe_runtime_event(event)\n            self._runtime_event_count += 1\n            runtime_applied += 1\n\n        if self._semantic_tail is not None and self._semantic_normalizer.ready:\n            for line_number, record in self._read_tail_records_locked(self._semantic_tail):\n                try:\n                    normalized = self._semantic_normalizer.normalize(\n                        record,\n                        line_number=line_number,\n                    )\n                except ValueError:\n                    continue\n                if normalized is None:\n                    continue\n                if not self._apply_live_event_locked(\n                    normalized,\n                    added_nodes=added_nodes,\n                    updated_nodes=updated_nodes,\n                    added_edges=added_edges,\n                    updated_edges=updated_edges,\n                ):\n                    continue\n                self._specialized_event_count += 1\n                specialized_applied += 1\n\n        applied_count = runtime_applied + specialized_applied\n        if not applied_count:\n            return\n\n        counts = self._counts_locked()\n        node_count = int(counts[\"node_count\"])\n        edge_count = int(counts[\"edge_count\"])\n        compact = not _within_live_payload_budget(node_count, edge_count)\n        update: dict[str, object] = {\n            **counts,\n            \"event_count_delta\": applied_count,\n            \"evidence_event_count_delta\": {\n                \"os_runtime\": runtime_applied,\n                \"specialized\": specialized_applied,\n            },\n            \"nodes_added\": [],\n            \"nodes_updated\": [],\n            \"edges_added\": [],\n            \"edges_updated\": [],\n        }\n        if compact:\n            update[\"live_payload_compact\"] = True\n        else:\n            update[\"nodes_added\"] = [\n                self._accumulator.nodes[node_id].to_dict()\n                for node_id in sorted(added_nodes)\n                if node_id in self._accumulator.nodes\n            ]\n            update[\"nodes_updated\"] = [\n                self._accumulator.nodes[node_id].to_dict()\n                for node_id in sorted(updated_nodes - added_nodes)\n                if node_id in self._accumulator.nodes\n            ]\n            update[\"edges_added\"] = [\n                self._accumulator.edges[key].to_dict()\n                for key in sorted(added_edges)\n                if key in self._accumulator.edges\n            ]\n            update[\"edges_updated\"] = [\n                self._accumulator.edges[key].to_dict()\n                for key in sorted(updated_edges - added_edges)\n                if key in self._accumulator.edges\n            ]\n        self._append_update_locked(update)\n\n'''
    text = text[:start] + new_refresh + text[end:]

    old_snapshot = '''            payload = self._snapshot_from_accumulator_locked()\n            payload[\"live_finished\"] = self._finished\n            return payload\n'''
    new_snapshot = '''            payload = self._snapshot_from_accumulator_locked()\n            payload[\"live_finished\"] = self._finished\n            payload[\"live_evidence_counts\"] = {\n                \"os_runtime\": self._runtime_event_count,\n                \"specialized\": self._specialized_event_count,\n            }\n            payload[\"live_specialized_provisional\"] = (\n                self._specialized_event_count > 0 and not self._finished\n            )\n            return payload\n'''
    text = replace_once(text, old_snapshot, new_snapshot, label="live snapshot evidence counts")

    text = replace_once(
        text,
        '    event_path = run_dir / "events.jsonl"\n'
        '    graph_path = run_dir / "graph.json"\n'
        '    viewer_path = run_dir / "viewer.html"\n'
        '    for artifact in (event_path, graph_path, viewer_path):\n',
        '    event_path = run_dir / "events.jsonl"\n'
        '    semantic_path = run_dir / "semantic.jsonl"\n'
        '    merged_event_path = run_dir / "events.semantic.jsonl"\n'
        '    graph_path = run_dir / "graph.json"\n'
        '    viewer_path = run_dir / "viewer.html"\n'
        '    for artifact in (event_path, semantic_path, merged_event_path, graph_path, viewer_path):\n',
        label="live artifact paths",
    )
    text = replace_once(
        text,
        "    state = _LiveState(session_id, event_path)\n",
        "    state = _LiveState(session_id, event_path, semantic_path)\n",
        label="LiveState semantic path",
    )
    text = replace_once(
        text,
        "    return_code = 1\n"
        "    try:\n"
        "        return_code = collector.run(command)\n"
        "        validation = validate_event_stream(event_path)\n",
        "    return_code = 1\n"
        "    previous_semantic_sidecar = os.environ.get(_SEMANTIC_ENV)\n"
        "    os.environ[_SEMANTIC_ENV] = str(semantic_path)\n"
        "    try:\n"
        "        try:\n"
        "            return_code = collector.run(command)\n"
        "        finally:\n"
        "            if previous_semantic_sidecar is None:\n"
        "                os.environ.pop(_SEMANTIC_ENV, None)\n"
        "            else:\n"
        "                os.environ[_SEMANTIC_ENV] = previous_semantic_sidecar\n"
        "        validation = validate_event_stream(event_path)\n",
        label="live semantic env lifecycle",
    )
    text = replace_once(
        text,
        "        execution_graph = build_execution_graph(event_path)\n"
        "        graph_payload = execution_graph.to_dict()\n",
        "        materialized_event_path = event_path\n"
        "        if semantic_path.exists() and semantic_path.stat().st_size > 0:\n"
        "            merge_semantic_sidecar(event_path, semantic_path, merged_event_path)\n"
        "            materialized_event_path = merged_event_path\n\n"
        "        execution_graph = build_execution_graph(materialized_event_path)\n"
        "        graph_payload = execution_graph.to_dict()\n",
        label="live final semantic merge",
    )
    text = replace_once(
        text,
        "            event_stream=event_path,\n"
        "            graph=graph_path,\n",
        "            event_stream=event_path,\n"
        "            semantic_sidecar=semantic_path,\n"
        "            materialized_event_stream=materialized_event_path,\n"
        "            graph=graph_path,\n",
        label="LiveResult construction",
    )
    path.write_text(text, encoding="utf-8")


def update_version() -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'version = "0.6.3"',
        'version = "0.6.4"',
        label="project version",
    )
    path.write_text(text, encoding="utf-8")


def write_tests() -> None:
    path = ROOT / "tests/test_v064_live_evidence.py"
    if path.exists():
        raise RuntimeError(f"test file already exists: {path}")
    path.write_text(
        '''from __future__ import annotations\n\nimport json\nimport sys\nfrom pathlib import Path\n\nfrom execweave.live import _LiveState, run_live\n\n\ndef _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:\n    path.write_text(\n        \"\".join(json.dumps(record, sort_keys=True) + \"\\n\" for record in records),\n        encoding=\"utf-8\",\n    )\n\n\ndef test_live_state_incrementally_ingests_specialized_sidecar(tmp_path: Path) -> None:\n    runtime = tmp_path / \"events.jsonl\"\n    semantic = tmp_path / \"semantic.jsonl\"\n    _write_jsonl(\n        runtime,\n        [\n            {\n                \"schema_version\": \"0.2\",\n                \"event_id\": \"start\",\n                \"session_id\": \"s1\",\n                \"timestamp\": \"2026-08-26T00:00:00Z\",\n                \"sequence\": 1,\n                \"event_type\": \"session.started\",\n                \"relation\": \"STARTED\",\n                \"source\": {\"id\": \"session:s1\", \"type\": \"session\", \"name\": \"s1\"},\n                \"target\": None,\n                \"attributes\": {\"backend\": \"portable\", \"causal\": True},\n            },\n            {\n                \"schema_version\": \"0.2\",\n                \"event_id\": \"proc\",\n                \"session_id\": \"s1\",\n                \"timestamp\": \"2026-08-26T00:00:01Z\",\n                \"sequence\": 2,\n                \"event_type\": \"process.started\",\n                \"relation\": \"LAUNCHED\",\n                \"source\": {\"id\": \"session:s1\", \"type\": \"session\", \"name\": \"s1\"},\n                \"target\": {\n                    \"id\": \"process:s1:123\",\n                    \"type\": \"process\",\n                    \"name\": \"python\",\n                    \"attributes\": {\"pid\": 123, \"create_time\": 1787702400.5},\n                },\n                \"attributes\": {\"backend\": \"portable\", \"causal\": True},\n            },\n        ],\n    )\n    _write_jsonl(\n        semantic,\n        [\n            {\n                \"event_id\": \"semantic-1\",\n                \"timestamp\": \"2026-08-26T00:00:02Z\",\n                \"event_type\": \"agent.tool.requested\",\n                \"relation\": \"REQUESTED_TOOL_CALL\",\n                \"source\": {\"id\": \"tool-call:1\", \"type\": \"tool_call\", \"name\": \"shell\"},\n                \"target\": {\n                    \"id\": \"process-ref:123\",\n                    \"type\": \"process_reference\",\n                    \"attributes\": {\"pid\": 123},\n                },\n                \"attributes\": {\"causal\": False},\n            }\n        ],\n    )\n\n    state = _LiveState(\"s1\", runtime, semantic)\n    payload = state.snapshot()\n\n    assert payload[\"event_count\"] == 3\n    assert payload[\"live_evidence_counts\"] == {\"os_runtime\": 2, \"specialized\": 1}\n    assert payload[\"live_specialized_provisional\"] is True\n    assert any(\n        edge[\"relation\"] == \"REQUESTED_TOOL_CALL\"\n        and edge[\"target\"] == \"process:s1:123\"\n        for edge in payload[\"edges\"]\n    )\n    assert all(edge[\"event_ids\"] == [] for edge in payload[\"edges\"])\n\n\ndef test_run_live_exports_sidecar_and_rebuilds_final_graph_from_canonical_merge(\n    tmp_path: Path,\n) -> None:\n    code = r'''import datetime\nimport json\nimport os\nimport pathlib\nimport time\n\ntime.sleep(0.1)\npath = pathlib.Path(os.environ[\"EXECWEAVE_SEMANTIC_SIDECAR\"])\nrecord = {\n    \"event_id\": \"semantic-child-1\",\n    \"timestamp\": datetime.datetime.now(datetime.timezone.utc).isoformat().replace(\"+00:00\", \"Z\"),\n    \"event_type\": \"agent.tool.requested\",\n    \"relation\": \"REQUESTED_TOOL_CALL\",\n    \"source\": {\"id\": \"tool-call:child\", \"type\": \"tool_call\", \"name\": \"demo\"},\n    \"target\": {\"id\": \"resource:child\", \"type\": \"resource\", \"name\": \"demo-resource\"},\n    \"attributes\": {\"causal\": False},\n}\npath.write_text(json.dumps(record) + \"\\n\", encoding=\"utf-8\")\ntime.sleep(0.15)\n'''\n    result = run_live(\n        [sys.executable, \"-c\", code],\n        watch_root=tmp_path,\n        output_dir=tmp_path / \"live-v064\",\n        poll_interval=0.05,\n        collect_filesystem=False,\n        collect_network=False,\n        port=0,\n        open_browser=False,\n        linger_seconds=0,\n    )\n\n    assert result.return_code == 0\n    assert result.event_stream.name == \"events.jsonl\"\n    assert result.semantic_sidecar.name == \"semantic.jsonl\"\n    assert result.semantic_sidecar.exists()\n    assert result.materialized_event_stream.name == \"events.semantic.jsonl\"\n    assert result.materialized_event_stream.exists()\n\n    graph = json.loads(result.graph.read_text(encoding=\"utf-8\"))\n    assert graph[\"source_path\"].endswith(\"events.semantic.jsonl\")\n    assert any(edge[\"relation\"] == \"REQUESTED_TOOL_CALL\" for edge in graph[\"edges\"])\n\n\ndef test_run_live_restores_existing_semantic_sidecar_environment(\n    monkeypatch,\n    tmp_path: Path,\n) -> None:\n    monkeypatch.setenv(\"EXECWEAVE_SEMANTIC_SIDECAR\", \"keep-me\")\n    result = run_live(\n        [sys.executable, \"-c\", \"pass\"],\n        watch_root=tmp_path,\n        output_dir=tmp_path / \"live-env\",\n        collect_filesystem=False,\n        collect_network=False,\n        port=0,\n        open_browser=False,\n        linger_seconds=0,\n    )\n    assert result.return_code == 0\n    assert result.materialized_event_stream == result.event_stream\n    assert not result.semantic_sidecar.exists()\n    assert __import__(\"os\").environ[\"EXECWEAVE_SEMANTIC_SIDECAR\"] == \"keep-me\"\n''',
        encoding="utf-8",
    )


def main() -> None:
    update_semantic()
    update_live()
    update_version()
    write_tests()


if __name__ == "__main__":
    main()
