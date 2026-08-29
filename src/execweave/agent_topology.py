"""Evidence-scoped agent topology: who is root, who is a child, and how we know.

ExecWeave must never present an agent hierarchy it did not observe. Absence from a
list of known provider display names is not evidence that an agent is a child, so
this module inverts the rule: **an agent is root unless positive provider evidence
establishes a parent.**

Two questions are kept separate because they have different answers:

``topology_state``
    How the parent/child relationship itself was established.

``agent_path_source``
    Whether the ``/root/...`` path string was published by the provider or is an
    ExecWeave canonical rendering of a relationship the provider expressed some
    other way. A provider can report ``parentSessionId``/``sessionId`` without ever
    emitting a path; the relationship is then provider-reported while the path is
    derived, and the two must not be conflated.

Producers declare topology on the agent node with :func:`root_topology` or
:func:`subagent_topology`. Consumers read it back with :func:`resolve_agent_topology`,
which defaults to root and never infers a child from an unfamiliar identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# How the parent/child relationship was established.
TOPOLOGY_OBSERVED = "observed"
"""The provider published the agent path/topology directly."""

TOPOLOGY_PROVIDER_REPORTED = "provider_reported"
"""The provider reported the relationship (parent id ↔ child id) but not a path."""

TOPOLOGY_DERIVED = "derived"
"""ExecWeave rendered this position; the provider expressed no hierarchy."""

TOPOLOGY_UNRESOLVED = "unresolved"
"""Evidence names an agent but does not establish reliable identity or parentage."""

TOPOLOGY_STATES = (
    TOPOLOGY_OBSERVED,
    TOPOLOGY_PROVIDER_REPORTED,
    TOPOLOGY_DERIVED,
    TOPOLOGY_UNRESOLVED,
)

# Where the agent path string itself came from.
PATH_PROVIDER_DECLARED = "provider_declared"
PATH_EXECWEAVE_DERIVED = "execweave_derived"
PATH_LEGACY_UNKNOWN = "legacy_unknown"
"""An artifact written before topology provenance existed. Never upgraded."""

# How much conversational evidence a materialized thread actually rests on. A thread
# assembled only from a parent's routing records must never read as a full transcript.
COMPLETENESS_PROVIDER_TRANSCRIPT = "provider_transcript"
"""The agent's own provider transcript was archived and parsed."""

COMPLETENESS_ROUTING_ONLY = "routing_only"
"""Only cross-agent routing records survive; the agent's own transcript was not captured."""

COMPLETENESS_UNAVAILABLE = "unavailable"
"""The agent is known, but no conversational evidence is available for it."""

CONVERSATION_COMPLETENESS = (
    COMPLETENESS_PROVIDER_TRANSCRIPT,
    COMPLETENESS_ROUTING_ONLY,
    COMPLETENESS_UNAVAILABLE,
)

_COMPLETENESS_RANK = {
    COMPLETENESS_UNAVAILABLE: 0,
    COMPLETENESS_ROUTING_ONLY: 1,
    COMPLETENESS_PROVIDER_TRANSCRIPT: 2,
}


def strongest_completeness(values: list[str]) -> str:
    """Merging threads from several sources keeps the strongest evidence they carry."""
    known = [value for value in values if value in _COMPLETENESS_RANK]
    if not known:
        return COMPLETENESS_UNAVAILABLE
    return max(known, key=lambda value: _COMPLETENESS_RANK[value])


AGENT_ROLE_ROOT = "root"
AGENT_ROLE_SUBAGENT = "subagent"

ROOT_PATH = "/root"

# Node attribute keys. Root and child declarations are deliberately namespaced apart.
#
# Graph nodes merge first-write-wins, and event order is not guaranteed: a session's
# completion evidence can be observed before the task metadata that names its parent.
# If both declarations wrote the same keys, whichever arrived first would decide the
# topology. Keeping them disjoint makes a positive child declaration authoritative
# regardless of arrival order, while absence of one still means root.
ATTR_ROLE = "agent_role"

ATTR_ROOT_PATH = "root_agent_path"
ATTR_ROOT_PATH_SOURCE = "root_agent_path_source"
ATTR_ROOT_EVIDENCE = "root_topology_evidence"

ATTR_PARENT_PATH = "parent_agent_path"
ATTR_PARENT_SCOPE = "parent_scope_id"
ATTR_PARENT_EVIDENCE = "parent_relation_source"
ATTR_CHILD_PATH = "child_agent_path"

# Pre-provenance artifacts wrote a bare path with no source. Read, never upgraded.
ATTR_LEGACY_PATH = "agent_path"

# Evidence vocabulary. Each value names the provider fact that established the
# relationship, so a reader can audit the claim back to its source.
EVIDENCE_PROVIDER_SESSION_ROOT = "provider_session_root"
EVIDENCE_SUBAGENT_LIFECYCLE_HOOK = "provider_subagent_lifecycle_hook"
EVIDENCE_ROLLOUT_SESSION_META = "provider_rollout_session_meta"
EVIDENCE_PARENT_SESSION_ID = "provider_parent_session_id"
EVIDENCE_VALIDATED_CHILD_TRANSCRIPT = "provider_validated_child_transcript"
EVIDENCE_CROSS_AGENT_ROUTING = "provider_cross_agent_routing_record"
EVIDENCE_NO_PARENT_EVIDENCE = "no_parent_evidence_observed"
EVIDENCE_LEGACY_ARTIFACT = "legacy_artifact_without_provenance"


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def root_topology(
    *,
    evidence: str = EVIDENCE_PROVIDER_SESSION_ROOT,
    agent_path: str | None = None,
    provider_declared_path: bool = False,
) -> dict[str, Any]:
    """Declare an agent node as the root of what was observed.

    ``/root`` is ExecWeave's canonical name for the top of a run. Unless the provider
    literally published that path, ``root_agent_path_source`` stays
    ``execweave_derived`` even though the root position itself is provider-reported.

    This never blocks a later subagent declaration: the keys are disjoint, so evidence
    of a parent always wins over the absence of one.
    """
    return {
        ATTR_ROLE: AGENT_ROLE_ROOT,
        ATTR_ROOT_PATH: _text(agent_path) or ROOT_PATH,
        ATTR_ROOT_PATH_SOURCE: (
            PATH_PROVIDER_DECLARED if provider_declared_path else PATH_EXECWEAVE_DERIVED
        ),
        ATTR_ROOT_EVIDENCE: evidence,
    }


def subagent_topology(
    *,
    evidence: str,
    parent_scope_id: str | None = None,
    agent_path: str | None = None,
    parent_agent_path: str | None = None,
) -> dict[str, Any]:
    """Declare an agent node as a child, naming the evidence that establishes it.

    Call this only where the provider positively identified the agent as a subagent —
    a subagent lifecycle hook, a rollout naming its parent thread, an explicit parent
    session id. Never call it because an identifier looked unfamiliar.

    Keys written here are absent from :func:`root_topology`, so this declaration is
    authoritative however the events interleave. Only what this evidence actually
    established is published; a path the provider never sent is simply omitted rather
    than reserved as ``None``, which the first-write-wins merge would treat as final.
    """
    declared: dict[str, Any] = {
        ATTR_ROLE: AGENT_ROLE_SUBAGENT,
        ATTR_PARENT_PATH: _text(parent_agent_path) or ROOT_PATH,
        ATTR_PARENT_EVIDENCE: evidence,
    }
    path = _text(agent_path)
    if path:
        declared[ATTR_CHILD_PATH] = path
    scope = _text(parent_scope_id)
    if scope:
        declared[ATTR_PARENT_SCOPE] = scope
    return declared


@dataclass(frozen=True)
class AgentTopology:
    """One agent's position in the run, with the provenance of every claim."""

    agent_path: str
    agent_path_source: str
    topology_state: str
    topology_evidence: str | None
    parent_agent_path: str | None
    parent_relation_source: str | None
    provider_native_id: str | None
    is_root: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_path": self.agent_path,
            "agent_path_source": self.agent_path_source,
            "topology_state": self.topology_state,
            "topology_evidence": self.topology_evidence,
            "parent_agent_path": self.parent_agent_path,
            "parent_relation_source": self.parent_relation_source,
            "provider_native_id": self.provider_native_id,
            "is_root": self.is_root,
        }


def _native_id(attributes: dict[str, Any], source: dict[str, Any]) -> str | None:
    for key in ("agent_id", "subagent_id", "conversation_id", "thread_id", "session_id"):
        value = _text(attributes.get(key))
        if value:
            return value
    return _text(source.get("id"))


def _derived_child_path(native_id: str | None, parent_path: str) -> str:
    """Render a canonical path for a child whose provider exposed no path of its own."""
    leaf = (native_id or "agent").replace("/", "-")
    base = parent_path.rstrip("/") or ROOT_PATH
    return f"{base}/{leaf}"


def resolve_agent_topology(source: dict[str, Any] | None) -> AgentTopology:
    """Read an agent node's topology, defaulting to root without parent evidence.

    The one rule that matters: this never returns a child unless the node carries a
    positive subagent declaration, or a legacy artifact already recorded a child path.
    An unfamiliar id, a bare session id, a nickname, or a source type of ``agent`` are
    all insufficient on their own.
    """
    source = source if isinstance(source, dict) else {}
    attributes = source.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    native_id = _native_id(attributes, source)

    parent_path = _text(attributes.get(ATTR_PARENT_PATH))
    if parent_path:
        child_path = _text(attributes.get(ATTR_CHILD_PATH))
        evidence = _text(attributes.get(ATTR_PARENT_EVIDENCE))
        return AgentTopology(
            agent_path=child_path or _derived_child_path(native_id, parent_path),
            agent_path_source=(
                PATH_PROVIDER_DECLARED if child_path else PATH_EXECWEAVE_DERIVED
            ),
            topology_state=(
                TOPOLOGY_OBSERVED if child_path else TOPOLOGY_PROVIDER_REPORTED
            ),
            topology_evidence=evidence,
            parent_agent_path=parent_path,
            parent_relation_source=evidence,
            provider_native_id=native_id,
            is_root=False,
        )

    legacy_path = _text(attributes.get(ATTR_LEGACY_PATH))
    if legacy_path and legacy_path != ROOT_PATH:
        # A pre-provenance artifact. Preserve what it recorded, but never upgrade an
        # unlabelled path into a provider-observed claim.
        return AgentTopology(
            agent_path=legacy_path,
            agent_path_source=PATH_LEGACY_UNKNOWN,
            topology_state=TOPOLOGY_UNRESOLVED,
            topology_evidence=EVIDENCE_LEGACY_ARTIFACT,
            parent_agent_path=ROOT_PATH,
            parent_relation_source=EVIDENCE_LEGACY_ARTIFACT,
            provider_native_id=native_id,
            is_root=False,
        )

    root_path = _text(attributes.get(ATTR_ROOT_PATH))
    if root_path:
        return AgentTopology(
            agent_path=root_path,
            agent_path_source=(
                _text(attributes.get(ATTR_ROOT_PATH_SOURCE)) or PATH_EXECWEAVE_DERIVED
            ),
            topology_state=(
                TOPOLOGY_OBSERVED
                if attributes.get(ATTR_ROOT_PATH_SOURCE) == PATH_PROVIDER_DECLARED
                else TOPOLOGY_PROVIDER_REPORTED
            ),
            topology_evidence=(
                _text(attributes.get(ATTR_ROOT_EVIDENCE)) or EVIDENCE_PROVIDER_SESSION_ROOT
            ),
            parent_agent_path=None,
            parent_relation_source=None,
            provider_native_id=native_id,
            is_root=True,
        )

    # No positive child evidence anywhere: this agent is the root of what we observed.
    return AgentTopology(
        agent_path=ROOT_PATH,
        agent_path_source=PATH_EXECWEAVE_DERIVED,
        topology_state=TOPOLOGY_DERIVED,
        topology_evidence=EVIDENCE_NO_PARENT_EVIDENCE,
        parent_agent_path=None,
        parent_relation_source=None,
        provider_native_id=native_id,
        is_root=True,
    )
