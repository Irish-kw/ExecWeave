"""Flow-ordered viewer layout: fold per-event bookkeeping, then layer by execution order.

Two things happen here, both provider-neutral. Nothing below reads a provider name, an
adapter, or an event type; the rules are written against node type, edge direction and
the relation vocabulary every adapter already emits.

**Folding** removes nodes that carry no flow of their own. A content leaf is evidence
about the entity it hangs off, not a step; a ``tool_call`` is one occurrence of the tool
that defines it; a file the OS watcher merely saw change was never read or written by an
actor. Every folded node keeps its identity in ``viewer_member_ids`` and its span in
``viewer_folded_members``, the same contract the existing endpoint and file clusters use,
so raw-log inspection, conversation ownership and time ranges all still resolve.

**Layering** replaces lane-by-node-type with longest-path layering over the graph itself.
Because a node's column is one past its furthest predecessor, every edge points right by
construction: there is no arrangement of a layered DAG that produces a backward edge.
Feedback edges are reversed before layering so the layering is defined even on a cyclic
graph. A previously assigned column acts as a floor, which is what keeps a live run from
ever pulling a node that is already on screen back to the left.

Raw evidence is never touched. This is a view over the graph, and the graph is itself a
materialized view over events.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from copy import deepcopy
from typing import Any

from ._conversation_records_core import _safe_content_reference

# A content node is evidence about something else. It has no flow of its own.
CONTENT_TYPES = frozenset({"observed_content"})

# One occurrence of an entity that exists independently of the occurrence. Folding these
# turns "six calls to list_dir" from six boxes into one box that says six.
OCCURRENCE_TYPES = frozenset({
    "tool_call",
    "tool_call_observation",
    "agent_execution",
    "agent_turn",
    "agent_turn_interrupt",
    "agent_message",
    "agent_message_transport_diagnostic",
    "command",
    "context_compaction",
    "conversation_item",
    "inference_request",
    # the remainder of the set the dashboard display filter already withholds, kept here
    # so the layout is computed over precisely the nodes a canvas ends up drawing
    "provider_session",
    "permission_request",
    "agent_turn_stop",
    "compaction",
    "compaction_request",
    "terminal_operation",
})

# The relation an occurrence uses to name the entity that defines it.
DEFINING_RELATIONS = frozenset({
    "USES_TOOL",
    "EXECUTED_TOOL_CALL",
    "SERVED_BY_MODEL",
    "ROUTED_TO_MODEL",
    "USED_MODEL",
    "REQUESTED_MODEL",
    "VIA_MCP",
})

# Something that can perform a read or a write. A session is a container, not an actor:
# an edge from the session is the OS watcher reporting what it saw, not the agent acting.
ACTOR_TYPES = frozenset({
    "agent",
    "agent_execution",
    "agent_operation",
    "agent_turn",
    "command",
    "model",
    "process",
    "provider_session",
    "subtask",
    "tool",
    "tool_call",
})

PATH_TYPES = frozenset({"file", "directory", "file_cluster"})

# Types the dashboard withholds from its canvas. Anything left here after folding is
# still a node of the graph and still reachable from every panel, but it takes no column,
# and edges route through it, so the ordering is solved against the set that is really
# drawn. Keeping the list here rather than only in the browser is what stops the two
# from disagreeing about which nodes exist to be ordered.
NOT_DRAWN_TYPES = frozenset({
    "agent_execution",
    "agent_turn",
    "agent_turn_stop",
    "compaction",
    "compaction_request",
    "context_compaction",
    "conversation_item",
    "observed_content",
    "permission_request",
    "provider_session",
    "terminal_operation",
    "tool_call",
    "tool_call_observation",
})

# Only these can stand in for an occurrence. A file, endpoint or content node is a thing
# the occurrence acted on, never the thing that defines it.
DEFINER_TYPES = frozenset({
    "agent",
    "model",
    "subtask",
    "tool",
})

# Attribute keys that name an entity, used to rejoin an observation that lost its edges.
IDENTITY_NAME_KEYS = ("tool_name", "native_name", "model_name")
IDENTITY_SCOPE_KEYS = ("provider",)

MIN_TWIN_GROUP = 3
DEFAULT_ORDER_SWEEPS = 16


# --------------------------------------------------------------------------- helpers


def _attrs(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("attributes")
    return value if isinstance(value, dict) else {}


def _relation(edge: dict[str, Any]) -> str:
    return str(edge.get("relation") or "").upper()


def _min_stamp(*values: Any) -> str | None:
    present = sorted(str(v) for v in values if isinstance(v, str) and v)
    return present[0] if present else None


def _max_stamp(*values: Any) -> str | None:
    present = sorted(str(v) for v in values if isinstance(v, str) and v)
    return present[-1] if present else None


def _min_int(*values: Any) -> int | None:
    present = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
    return min(present) if present else None


def _max_int(*values: Any) -> int | None:
    present = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
    return max(present) if present else None


def _merge_lists(a: Any, b: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for source in (a, b):
        if not isinstance(source, list):
            continue
        for value in source:
            text = str(value)
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


class _Folder:
    """Accumulates folds while preserving identity, span and provenance."""

    def __init__(self, graph: dict[str, Any]) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        for node in graph.get("nodes", []) or []:
            if isinstance(node, dict) and isinstance(node.get("id"), str) and node["id"]:
                self.nodes[node["id"]] = deepcopy(node)
        self.edges: list[dict[str, Any]] = [
            deepcopy(edge)
            for edge in (graph.get("edges", []) or [])
            if isinstance(edge, dict)
            and isinstance(edge.get("source"), str)
            and isinstance(edge.get("target"), str)
        ]
        self.removed: Counter[str] = Counter()

    # -- adjacency -------------------------------------------------------------

    def outgoing(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in self.edges:
            out[edge["source"]].append(edge)
        return out

    def incoming(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in self.edges:
            out[edge["target"]].append(edge)
        return out

    def degree(self) -> Counter[str]:
        deg: Counter[str] = Counter()
        for edge in self.edges:
            deg[edge["source"]] += 1
            deg[edge["target"]] += 1
        return deg

    # -- protection ------------------------------------------------------------

    def conversation_sources(self) -> set[str]:
        """Nodes a conversation entry names as its owner.

        ``conversation_record_entries`` walks every edge whose target passes
        ``_safe_content_reference`` and reports the *source* as ``source_id``. The agent
        panel then selects content by that id, so folding such a node away would leave an
        entry no box can open. The same predicate is used deliberately: a looser one
        freezes nodes that own nothing, a tighter one drops an owner the panel needs.
        """
        protected: set[str] = set()
        for edge in self.edges:
            target = self.nodes.get(edge["target"])
            if target is not None and _safe_content_reference(target) is not None:
                protected.add(edge["source"])
        return protected

    # -- mutation --------------------------------------------------------------

    def absorb(self, survivor_id: str, victim_id: str, reason: str) -> None:
        survivor = self.nodes.get(survivor_id)
        victim = self.nodes.get(victim_id)
        if survivor is None or victim is None or survivor_id == victim_id:
            return
        attributes = dict(_attrs(survivor))
        victim_attrs = _attrs(victim)

        members = list(attributes.get("viewer_folded_members") or [])
        members.append({
            "id": victim_id,
            "type": victim.get("type"),
            "name": victim.get("name") or victim_id,
            "first_seen": victim.get("first_seen"),
            "last_seen": victim.get("last_seen"),
            "reason": reason,
        })
        # a victim that had already absorbed others hands those on, so nothing is lost
        members.extend(victim_attrs.get("viewer_folded_members") or [])

        member_ids = _merge_lists(
            attributes.get("viewer_member_ids"),
            [victim_id, *(victim_attrs.get("viewer_member_ids") or [])],
        )
        attributes["viewer_member_ids"] = member_ids
        attributes["viewer_folded"] = True
        attributes["viewer_folded_members"] = members
        attributes["viewer_folded_count"] = len(members)
        attributes["viewer_folded_type"] = victim.get("type")
        reasons = Counter(attributes.get("viewer_fold_reasons") or {})
        reasons[reason] += 1
        for key, value in Counter(victim_attrs.get("viewer_fold_reasons") or {}).items():
            reasons[key] += value
        attributes["viewer_fold_reasons"] = dict(reasons)

        # an agent-shaped victim also aliases conversation ownership onto the survivor
        if victim.get("type") in {"agent", "agent_execution", "subtask", "provider_session"}:
            attributes["viewer_agent_member_ids"] = _merge_lists(
                attributes.get("viewer_agent_member_ids"),
                [victim_id, *(victim_attrs.get("viewer_agent_member_ids") or [])],
            )

        survivor["attributes"] = attributes
        survivor["first_seen"] = _min_stamp(survivor.get("first_seen"), victim.get("first_seen"))
        survivor["last_seen"] = _max_stamp(survivor.get("last_seen"), victim.get("last_seen"))
        self.removed[reason] += 1

    def drop(self, victim_ids: set[str], reason: str) -> None:
        for victim_id in victim_ids:
            if self.nodes.pop(victim_id, None) is not None:
                self.removed[reason] += 1
        self._rewrite({})

    def _rewrite(self, remap: dict[str, str]) -> None:
        """Apply a remap, then merge edges that became parallel."""
        resolved: dict[str, str] = {}
        for key in remap:
            seen: set[str] = set()
            value = key
            while value in remap and remap[value] not in seen:
                seen.add(remap[value])
                value = remap[value]
            resolved[key] = value

        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for edge in self.edges:
            source = resolved.get(edge["source"], edge["source"])
            target = resolved.get(edge["target"], edge["target"])
            if source not in self.nodes or target not in self.nodes or source == target:
                continue
            key = (source, _relation(edge), target)
            candidate = dict(edge)
            candidate["source"] = source
            candidate["target"] = target
            existing = merged.get(key)
            if existing is None:
                merged[key] = candidate
                continue
            existing["first_seen"] = _min_stamp(
                existing.get("first_seen"), candidate.get("first_seen")
            )
            existing["last_seen"] = _max_stamp(
                existing.get("last_seen"), candidate.get("last_seen")
            )
            existing["first_sequence"] = _min_int(
                existing.get("first_sequence"), candidate.get("first_sequence")
            )
            existing["last_sequence"] = _max_int(
                existing.get("last_sequence"), candidate.get("last_sequence")
            )
            for key_name in ("event_ids", "event_types", "backends", "attributions"):
                combined = _merge_lists(existing.get(key_name), candidate.get(key_name))
                if combined:
                    existing[key_name] = combined
        self.edges = list(merged.values())

    def collapse(self, remap: dict[str, str], reason: str) -> None:
        for victim_id, survivor_id in remap.items():
            self.absorb(survivor_id, victim_id, reason)
        for victim_id in remap:
            self.nodes.pop(victim_id, None)
        self._rewrite(remap)


# ----------------------------------------------------------------------- the rules


def _rule_os_only_paths(folder: _Folder, protected: set[str]) -> None:
    """A path node earns a box only when an actor is on one end of one of its edges.

    A file the OS watcher merely saw change was not read, written, created or deleted by
    the agent: the session reporting it is a container, not an actor. Rather than being
    discarded, such a file folds into whatever observed it, so it stays off the canvas
    but remains listed, with its span, on that observer's detail panel.
    """
    out, inc = folder.outgoing(), folder.incoming()
    remap: dict[str, str] = {}
    for node_id, node in folder.nodes.items():
        if node_id in protected or node.get("type") not in PATH_TYPES:
            continue
        edges = (*out[node_id], *inc[node_id])
        observers: list[str] = []
        touched_by_actor = False
        for edge in edges:
            other = edge["target"] if edge["source"] == node_id else edge["source"]
            peer = folder.nodes.get(other)
            if peer is None or other == node_id:
                continue
            if peer.get("type") in ACTOR_TYPES:
                touched_by_actor = True
                break
            observers.append(other)
        if touched_by_actor or not observers:
            continue
        remap[node_id] = sorted(observers)[0]
    if remap:
        folder.collapse(remap, "os_only_path")


def _rule_content_leaves(folder: _Folder, protected: set[str]) -> None:
    """A content node holding a single edge folds into the entity it describes."""
    out, inc = folder.outgoing(), folder.incoming()
    deg = folder.degree()
    remap: dict[str, str] = {}
    for node_id, node in folder.nodes.items():
        if node_id in protected or node.get("type") not in CONTENT_TYPES:
            continue
        if deg[node_id] != 1:
            continue
        edge = (out[node_id] + inc[node_id])[0]
        anchor = edge["target"] if edge["source"] == node_id else edge["source"]
        if anchor != node_id and anchor in folder.nodes:
            remap[node_id] = anchor
    if remap:
        folder.collapse(remap, "content_leaf")


def _rule_occurrences(folder: _Folder, protected: set[str]) -> None:
    """An occurrence folds into the entity that defines it, repeatedly until stable."""
    while True:
        out, inc = folder.outgoing(), folder.incoming()
        remap: dict[str, str] = {}
        for node_id, node in folder.nodes.items():
            if node_id in protected or node.get("type") not in OCCURRENCE_TYPES:
                continue
            owner: str | None = None
            for edge in out[node_id]:
                if _relation(edge) in DEFINING_RELATIONS and edge["target"] in folder.nodes:
                    owner = edge["target"]
                    break
            if owner is None:
                peers = {
                    (edge["target"] if edge["source"] == node_id else edge["source"])
                    for edge in (*out[node_id], *inc[node_id])
                }
                peers.discard(node_id)
                peers = {
                    peer for peer in peers
                    if peer in folder.nodes
                    and folder.nodes[peer].get("type") in DEFINER_TYPES
                }
                if len(peers) == 1:
                    owner = peers.pop()
            if owner and owner != node_id and owner not in remap:
                remap[node_id] = owner
        if not remap:
            return
        folder.collapse(remap, "occurrence")


def _identity(node: dict[str, Any]) -> tuple[tuple[str, ...], str]:
    a = _attrs(node)
    name = next(
        (str(a[key]).lower() for key in IDENTITY_NAME_KEYS if isinstance(a.get(key), str) and a[key]),
        str(node.get("name") or "").lower(),
    )
    scope = tuple(str(a.get(key) or "").lower() for key in IDENTITY_SCOPE_KEYS)
    return scope, name


def _rule_mirror_identity(folder: _Folder, protected: set[str]) -> None:
    """An observation left with no edges rejoins the entity sharing its scope and name.

    This is the presentation half of ``mirrorWitness``: a mirrored observation is not a
    second invocation, so it must not sit on the canvas as an unattached twin of the call
    it mirrors. A node with no identity to match keeps its own box.
    """
    out, inc = folder.outgoing(), folder.incoming()
    attached: dict[tuple[tuple[str, ...], str], list[str]] = defaultdict(list)
    for node_id, node in folder.nodes.items():
        if out[node_id] or inc[node_id]:
            attached[_identity(node)].append(node_id)
    remap: dict[str, str] = {}
    for node_id, node in folder.nodes.items():
        if node_id in protected or out[node_id] or inc[node_id]:
            continue
        candidates = [c for c in attached.get(_identity(node), []) if c != node_id]
        if candidates:
            remap[node_id] = sorted(candidates)[0]
    if remap:
        folder.collapse(remap, "mirror_identity")


def _rule_structural_twins(folder: _Folder, protected: set[str]) -> None:
    """Same type, same neighbours, same relations: one box instead of many."""
    out, inc = folder.outgoing(), folder.incoming()
    groups: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for node_id, node in folder.nodes.items():
        if node_id in protected:
            continue
        edges = (*out[node_id], *inc[node_id])
        if not edges:
            continue
        peers = tuple(sorted(
            {(e["target"] if e["source"] == node_id else e["source"]) for e in edges} - {node_id}
        ))
        relations = tuple(sorted({_relation(e) for e in edges}))
        if peers:
            groups[(node.get("type"), peers, relations)].append(node_id)
    remap: dict[str, str] = {}
    renames: dict[str, tuple[str, str, int]] = {}
    for (node_type, _peers, _relations), group in groups.items():
        if len(group) < MIN_TWIN_GROUP:
            continue
        group.sort()
        keep = group[0]
        base = str(node_type or "node")
        renames[keep] = (
            base if base.endswith("_cluster") else base + "_cluster",
            f"{len(group)} {base.replace('_', ' ')}s",
            len(group),
        )
        for victim in group[1:]:
            remap[victim] = keep
    if not remap:
        return
    folder.collapse(remap, "structural_twin")
    for keep, (node_type, name, count) in renames.items():
        node = folder.nodes.get(keep)
        if node is None:
            continue
        node["type"] = node_type
        node["name"] = name
        attributes = dict(_attrs(node))
        attributes["viewer_cluster"] = True
        attributes["member_count"] = count
        node["attributes"] = attributes


def _rule_bypass_undrawn(folder: _Folder) -> None:
    """Route edges through the types a canvas withholds, so they take no column.

    These are not folded into anything: no single node stands in for them, and each keeps
    its own entry in the graph and its own panel. They simply stop being an obstacle the
    ordering has to place, and their neighbours are joined directly so the flow through
    them survives. Solving the order against any other set is what leaves a drawn edge
    crossing another for no reason a reader can see.
    """
    for _ in range(len(NOT_DRAWN_TYPES) + 1):
        out, inc = folder.outgoing(), folder.incoming()
        victims = [
            node_id for node_id, node in folder.nodes.items()
            if node.get("type") in NOT_DRAWN_TYPES
        ]
        if not victims:
            return
        bridged: list[dict[str, Any]] = []
        for node_id in victims:
            for before in inc[node_id]:
                for after in out[node_id]:
                    source, target = before["source"], after["target"]
                    if source == node_id or target == node_id or source == target:
                        continue
                    bridged.append({
                        "source": source,
                        "target": target,
                        # the bridged edge describes what the bypassed node did next, so
                        # it carries the outgoing relation. Taking the incoming one made an
                        # agent's INVOKES_MODEL edge read as OBSERVED_PROVIDER_SESSION.
                        "relation": after.get("relation") or before.get("relation"),
                        "first_seen": _min_stamp(before.get("first_seen"), after.get("first_seen")),
                        "last_seen": _max_stamp(before.get("last_seen"), after.get("last_seen")),
                        "viewer_bridged_through": node_id,
                    })
        for node_id in victims:
            folder.nodes.pop(node_id, None)
        folder.edges.extend(bridged)
        folder._rewrite({})
        folder.removed["not_drawn"] += len(victims)


# -------------------------------------------------------------------------- layering


def _feedback_edges(node_ids: list[str], adjacency: dict[str, list[str]]) -> set[tuple[str, str]]:
    """Edges that close a cycle, found by an iterative colouring DFS."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(node_ids, WHITE)
    feedback: set[tuple[str, str]] = set()
    for root in node_ids:
        if colour[root] != WHITE:
            continue
        colour[root] = GREY
        stack: list[tuple[str, Any]] = [(root, iter(adjacency.get(root, ())))]
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if colour.get(child) == GREY:
                    feedback.add((node, child))
                    continue
                if colour.get(child) == WHITE:
                    colour[child] = GREY
                    stack.append((child, iter(adjacency.get(child, ()))))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()
    return feedback


def assign_layers(
    node_ids: list[str],
    edges: list[dict[str, Any]],
    previous: dict[str, int] | None = None,
) -> dict[str, int]:
    """Longest-path layering with a per-node floor.

    Every edge of the resulting layering points strictly right. ``previous`` supplies the
    floor that makes a live run monotonic: a node already placed can be pushed further
    right by new evidence, never pulled back.
    """
    present = set(node_ids)
    adjacency: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in present and target in present and source != target:
            if (source, target) not in seen:
                seen.add((source, target))
                adjacency[source].append(target)

    feedback = _feedback_edges(node_ids, adjacency)
    forward: dict[str, list[str]] = defaultdict(list)
    indegree: Counter[str] = Counter(dict.fromkeys(node_ids, 0))
    for source, targets in adjacency.items():
        for target in targets:
            a, b = (target, source) if (source, target) in feedback else (source, target)
            if a == b:
                continue
            forward[a].append(b)
            indegree[b] += 1

    floor = previous or {}
    layer = {node_id: max(0, int(floor.get(node_id, 0))) for node_id in node_ids}
    queue = deque(sorted(n for n in node_ids if indegree[n] == 0))
    settled = 0
    while queue:
        node = queue.popleft()
        settled += 1
        for child in forward[node]:
            if layer[child] < layer[node] + 1:
                layer[child] = layer[node] + 1
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if settled < len(node_ids):
        # a cycle the reversal missed; park the remainder to the right of everything placed
        rest = max(layer.values(), default=0) + 1
        for node_id in node_ids:
            if indegree[node_id] > 0:
                layer[node_id] = max(layer[node_id], rest)
    return layer


def _count_crossings(
    edges: list[dict[str, Any]],
    layer: dict[str, int],
    order: dict[str, int],
) -> int:
    by_layer: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in layer and target in layer and layer[target] == layer[source] + 1:
            by_layer[layer[source]].append((order[source], order[target]))
    total = 0
    for pairs in by_layer.values():
        for i in range(len(pairs)):
            a = pairs[i]
            for j in range(i + 1, len(pairs)):
                b = pairs[j]
                if (a[0] - b[0]) * (a[1] - b[1]) < 0:
                    total += 1
    return total


def _with_virtual_chain(
    edges: list[dict[str, Any]],
    layer: dict[str, int],
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Break every edge into single-column steps, inventing a node for each one crossed.

    An edge spanning three columns occupies a row in the two columns between its ends,
    but with nothing standing in those columns the ordering cannot see it and places
    other nodes straight through its path. Giving it a placeholder per column is what
    lets a barycentre sweep route around it; the placeholders are discarded afterwards
    and never reach the canvas.
    """
    steps: list[tuple[str, str]] = []
    virtual: dict[str, int] = {}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source not in layer or target not in layer or source == target:
            continue
        start, end = layer[source], layer[target]
        if end <= start:
            continue
        if end == start + 1:
            steps.append((source, target))
            continue
        previous = source
        for column in range(start + 1, end):
            placeholder = f"\0virtual\0{source}\0{target}\0{column}"
            virtual[placeholder] = column
            steps.append((previous, placeholder))
            previous = placeholder
        steps.append((previous, target))
    return steps, virtual


def assign_order(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    layer: dict[str, int],
    sweeps: int = DEFAULT_ORDER_SWEEPS,
) -> dict[str, int]:
    """Barycentre sweeps over the real nodes plus a placeholder per column an edge crosses."""
    steps, virtual = _with_virtual_chain(edges, layer)
    placed = dict(layer)
    placed.update(virtual)

    columns: dict[int, list[str]] = defaultdict(list)
    for node_id in nodes:
        columns[layer[node_id]].append(node_id)
    for node_id, column in virtual.items():
        columns[column].append(node_id)
    for column in columns.values():
        column.sort(key=lambda n: (
            str((nodes.get(n) or {}).get("type") or "~"),
            str((nodes.get(n) or {}).get("name") or "~"),
            n,
        ))
    order = {n: i for column in columns.values() for i, n in enumerate(column)}

    predecessors: dict[str, list[str]] = defaultdict(list)
    successors: dict[str, list[str]] = defaultdict(list)
    for source, target in steps:
        predecessors[target].append(source)
        successors[source].append(target)

    def crossings(current: dict[str, int]) -> int:
        by_layer: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for source, target in steps:
            by_layer[placed[source]].append((current[source], current[target]))
        total = 0
        for pairs in by_layer.values():
            for i in range(len(pairs)):
                a = pairs[i]
                for j in range(i + 1, len(pairs)):
                    b = pairs[j]
                    if (a[0] - b[0]) * (a[1] - b[1]) < 0:
                        total += 1
        return total

    best_score = crossings(order)
    best_order = dict(order)
    for sweep in range(sweeps):
        downward = sweep % 2 == 0
        neighbours = predecessors if downward else successors
        for index in sorted(columns, reverse=not downward):
            column = columns[index]

            def barycentre(node_id: str) -> float:
                positions = [order[n] for n in neighbours[node_id] if n in order]
                return sum(positions) / len(positions) if positions else float(order[node_id])

            column.sort(key=lambda n: (barycentre(n), n))
            for position, node_id in enumerate(column):
                order[node_id] = position
        score = crossings(order)
        if score < best_score:
            best_score = score
            best_order = dict(order)

    # discard the placeholders and close the gaps they left in each column
    final: dict[str, int] = {}
    for index, column in columns.items():
        real = sorted((n for n in column if n in nodes), key=lambda n: best_order[n])
        for position, node_id in enumerate(real):
            final[node_id] = position
    return final


def _isotonic(desired: list[float], separation: float = 1.0) -> list[float]:
    """Closest values to ``desired`` that keep every neighbour ``separation`` apart.

    Substituting ``u_i = y_i - i*separation`` turns the spacing constraint into "u must
    not decrease", which pool-adjacent-violators solves exactly by averaging each run
    that breaks the order. So a column lands as near its preferred rows as the spacing
    allows, rather than being pushed down one slot at a time from the top.
    """
    shifted = [value - index * separation for index, value in enumerate(desired)]
    weights: list[float] = []
    means: list[float] = []
    for value in shifted:
        weights.append(1.0)
        means.append(value)
        while len(means) > 1 and means[-2] > means[-1]:
            weight = weights[-2] + weights[-1]
            mean = (means[-2] * weights[-2] + means[-1] * weights[-1]) / weight
            means[-2:] = [mean]
            weights[-2:] = [weight]
    flat: list[float] = []
    for weight, mean in zip(weights, means):
        flat.extend([mean] * int(round(weight)))
    return [value + index * separation for index, value in enumerate(flat)]


def assign_rows(
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    layer: dict[str, int],
    order: dict[str, int],
    sweeps: int = 8,
) -> dict[str, float]:
    """Turn the column order into actual rows, pulling each node level with its neighbours.

    Ordering decides who is above whom; this decides how far apart they sit. Without it
    every column starts at the top and counts downwards, which leaves a column holding
    one node stranded level with the top of a column holding eight, and makes the edges
    between them long diagonals for no reason in the data.
    """
    columns: dict[int, list[str]] = defaultdict(list)
    for node_id in nodes:
        columns[layer[node_id]].append(node_id)
    for column in columns.values():
        column.sort(key=lambda n: order[n])

    row: dict[str, float] = {n: float(order[n]) for n in nodes}
    predecessors: dict[str, list[str]] = defaultdict(list)
    successors: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in layer and target in layer and layer[target] > layer[source]:
            predecessors[target].append(source)
            successors[source].append(target)

    for sweep in range(sweeps):
        downward = sweep % 2 == 0
        neighbours = predecessors if downward else successors
        for index in sorted(columns, reverse=not downward):
            column = columns[index]
            desired = []
            for node_id in column:
                values = sorted(row[n] for n in neighbours[node_id] if n in row)
                if values:
                    middle = len(values) // 2
                    centre = (values[middle] if len(values) % 2
                              else (values[middle - 1] + values[middle]) / 2)
                else:
                    centre = row[node_id]
                desired.append(centre)
            for node_id, value in zip(column, _isotonic(desired)):
                row[node_id] = value

    lowest = min(row.values(), default=0.0)
    return {node_id: value - lowest for node_id, value in row.items()}


# ------------------------------------------------------------------------ entry point


def flow_layout_graph(
    graph: dict[str, Any],
    previous_layers: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Describe a canvas over the graph without removing anything from the graph.

    ``nodes`` and ``edges`` come back with exactly the members they went in with. The
    node panel, the content inspector, delegation and execution payload lookups,
    conversation ownership and the raw-event log all read those arrays, and every one of
    them is entitled to find a ``tool_call`` or a payload edge that this layout chooses
    not to draw. What is added is a description of the canvas:

    * each node gains ``viewer_layer`` and ``viewer_order``; a node that is drawn in
      another node's place also gains ``viewer_collapsed_into``, naming its stand-in;
    * the stand-in gains the usual ``viewer_member_ids`` / ``viewer_folded_members``, so
      a folded member is still listed, with its span, on the panel that replaced it;
    * ``viewer_flow`` lists exactly what to draw, with folded endpoints already remapped.

    A renderer draws ``viewer_flow``. Everything else keeps reading the full graph.
    """
    if not isinstance(graph, dict):
        return graph
    folder = _Folder(graph)
    if not folder.nodes:
        return graph
    original_ids = list(folder.nodes)

    protected = folder.conversation_sources()
    _rule_os_only_paths(folder, protected)
    _rule_content_leaves(folder, protected)
    _rule_occurrences(folder, protected)
    _rule_mirror_identity(folder, protected)
    _rule_structural_twins(folder, protected)
    _rule_bypass_undrawn(folder)

    drawn_ids = sorted(folder.nodes)
    layer = assign_layers(drawn_ids, folder.edges, previous_layers)
    order = assign_order(folder.nodes, folder.edges, layer)
    row = assign_rows(folder.nodes, folder.edges, layer, order)

    # where each folded node ended up, so an undrawn node can still be pointed at a box
    stand_in: dict[str, str] = {}
    for survivor_id, node in folder.nodes.items():
        for member in _attrs(node).get("viewer_member_ids") or []:
            stand_in[str(member)] = survivor_id

    annotations: dict[str, dict[str, Any]] = {}
    for node_id, node in folder.nodes.items():
        extra = dict(_attrs(node))
        extra["viewer_layer"] = int(layer[node_id])
        extra["viewer_order"] = int(order[node_id])
        extra["viewer_row"] = round(float(row[node_id]), 3)
        annotations[node_id] = extra
    for node_id in original_ids:
        if node_id in annotations:
            continue
        target = stand_in.get(node_id)
        if target is None:
            continue
        annotations[node_id] = {
            "viewer_collapsed_into": target,
            "viewer_layer": int(layer.get(target, 0)),
            "viewer_order": int(order.get(target, 0)),
            "viewer_row": round(float(row.get(target, 0.0)), 3),
        }

    nodes: list[dict[str, Any]] = []
    for node in graph.get("nodes", []) or []:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            nodes.append(node)
            continue
        extra = annotations.get(node["id"])
        if extra is None:
            nodes.append(node)
            continue
        merged = dict(node)
        merged["attributes"] = {**_attrs(node), **extra}
        nodes.append(merged)

    result = dict(graph)
    result["nodes"] = nodes
    result["node_count"] = len(nodes)
    result["viewer_flow"] = {
        "schema_version": "0.1",
        "layer_count": (max(layer.values()) + 1) if layer else 0,
        "nodes": [
            {
                "id": node_id,
                "layer": int(layer[node_id]),
                "order": int(order[node_id]),
                "row": round(float(row[node_id]), 3),
            }
            for node_id in drawn_ids
        ],
        "edges": [
            {
                "source": edge["source"],
                "target": edge["target"],
                "relation": edge.get("relation"),
            }
            for edge in folder.edges
        ],
        "collapsed": {
            member: survivor
            for member, survivor in sorted(stand_in.items())
        },
        "folded": dict(folder.removed),
        "crossings": _count_crossings(folder.edges, layer, order),
    }
    # ``viewer_projection`` is deliberately left alone. live_update reads that key to
    # decide a delta can no longer describe the view, because the projections that set it
    # rewrite node identity. This one does not: every node and edge is still present and
    # still itself. What changed is only which of them a canvas draws, and that travels
    # with a delta as ``viewer_flow`` rather than costing the run its incremental updates.
    return result


def layers_of(graph: dict[str, Any]) -> dict[str, int]:
    """Read back the assigned columns, to feed the next tick's floor."""
    flow = graph.get("viewer_flow")
    if isinstance(flow, dict):
        return {
            str(entry["id"]): int(entry["layer"])
            for entry in (flow.get("nodes") or [])
            if isinstance(entry, dict)
            and isinstance(entry.get("id"), str)
            and isinstance(entry.get("layer"), int)
        }
    return {}
