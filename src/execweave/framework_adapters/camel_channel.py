"""Observe an explicitly supplied CAMEL TaskChannel instance, not global classes."""
from __future__ import annotations

from typing import Any, Mapping

from .base import EntityRef


def observe_task_channel(adapter: Any, channel: Any, publishers: Mapping[str, EntityRef]) -> Any:
    if getattr(channel, "_execweave_channel_adapter", None) is adapter:
        return channel
    names = ("post_task", "get_assigned_task_by_assignee", "return_task", "get_returned_task_by_publisher")
    originals = {name: getattr(channel, name, None) for name in names}
    if not all(callable(method) for method in originals.values()):
        raise TypeError("CAMEL channel does not expose the supported task delivery boundaries")
    routes: dict[str, dict[str, Any]] = {}
    counter = 0

    def record(route, *, reply=False, received=False):
        source, target = route["publisher"], route["assignee"]
        task = route["task"]
        content = str(getattr(task, "result", "") or "") if reply else str(getattr(task, "content", "") or "")
        if reply:
            source, target = target, source
        message = adapter.message(
            route["id"] + (":reply" if reply else ":dispatch"), source, target,
            content=content, role="agent", received=received,
            routing_source="camel_task_channel_delivery" if received else "camel_task_channel_post",
            native_task_id=str(task.id),
        )
        if source is None or target is None:
            adapter.message_unrouted(message, callback_name="TaskChannel", missing_sender=source is None, missing_recipient=target is None)

    async def post_task(task, publisher_id, assignee_id):
        nonlocal counter
        result = await originals["post_task"](task, publisher_id, assignee_id)
        counter += 1
        route = {"id": f"channel:{task.id}:{counter}", "task": task,
                 "publisher": publishers.get(str(publisher_id)) or adapter._agents.get(str(publisher_id)),
                 "assignee": adapter._agents.get(str(assignee_id))}
        routes[str(task.id)] = route
        record(route)
        return result

    async def assigned(assignee_id):
        task = await originals["get_assigned_task_by_assignee"](assignee_id)
        route = routes.get(str(task.id))
        if route:
            record(route, received=True)
        return task

    async def return_task(task_id):
        result = await originals["return_task"](task_id)
        route = routes.get(str(task_id))
        if route:
            record(route, reply=True)
        return result

    async def returned(publisher_id):
        task = await originals["get_returned_task_by_publisher"](publisher_id)
        route = routes.pop(str(task.id), None)
        if route:
            record(route, reply=True, received=True)
        return task

    channel.post_task = post_task
    channel.get_assigned_task_by_assignee = assigned
    channel.return_task = return_task
    channel.get_returned_task_by_publisher = returned
    channel._execweave_channel_adapter = adapter
    return channel
