from __future__ import annotations


_DIRECT_ASSIGN = "    ['ASSIGNED_AGENT_TASK','assign_agent_task'],\n"
_DIRECT_SUBTASK = "    ['REQUESTED_SUBTASK','assign_agent_task'],\n"
_ASSIGN_TARGET = "    ['assign_agent_task','ASSIGNED_AGENT_TASK'],"
_SAFE_ASSIGN_TARGET = "    ['assign_agent_task','TARGETED_AGENT'],"


def harden_execution_flow_projection(html: str) -> str:
    """Keep ambiguous provider subtask/profile evidence out of agent assignment.

    Some providers expose a subtask/profile concept without identifying a real child
    agent.  The execution-flow viewer may show an assignment action only when an
    explicit tool/action occurrence resolves a concrete target agent identity; generic
    ASSIGNED_AGENT_TASK / REQUESTED_SUBTASK relations must never synthesize that link.
    """

    for unsafe in (_DIRECT_ASSIGN, _DIRECT_SUBTASK):
        if unsafe not in html:
            raise RuntimeError("execution-flow assignment safety seam changed")
        html = html.replace(unsafe, "", 1)
    if _ASSIGN_TARGET not in html:
        raise RuntimeError("execution-flow assignment target seam changed")
    return html.replace(_ASSIGN_TARGET, _SAFE_ASSIGN_TARGET, 1)
