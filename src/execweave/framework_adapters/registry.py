"""Framework adapter discovery and compatibility registry."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Callable

from .base import AdapterContext, FrameworkAdapter, FrameworkCompatibility

AdapterFactory = Callable[[AdapterContext], FrameworkAdapter]


@dataclass(frozen=True)
class AdapterDescriptor:
    name: str
    factory: AdapterFactory
    source: str


class FrameworkAdapterRegistry:
    """Registry for built-in and third-party adapters.

    Entry points are loaded lazily; importing ExecWeave never imports a
    framework package.
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, AdapterDescriptor] = {}

    def register(self, name: str, factory: AdapterFactory, *, source: str = "manual") -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("adapter name must not be empty")
        existing = self._descriptors.get(normalized)
        if existing is not None and existing.factory is not factory:
            raise ValueError(f"adapter already registered: {normalized}")
        self._descriptors[normalized] = AdapterDescriptor(normalized, factory, source)

    def discover(self, *, group: str = "execweave.framework_adapters") -> tuple[str, ...]:
        entries = metadata.entry_points()
        selected = entries.select(group=group) if hasattr(entries, "select") else entries.get(group, ())
        for entry in selected:
            name = str(entry.name).strip().lower()
            if not name or name in self._descriptors:
                continue
            loaded = entry.load()
            factory = loaded if callable(loaded) else getattr(loaded, "create", None)
            if not callable(factory):
                raise TypeError(f"adapter entry point {entry.name!r} is not callable")
            self.register(name, factory, source=f"entry_point:{entry.value}")
        return self.names()

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def descriptor(self, name: str) -> AdapterDescriptor:
        try:
            return self._descriptors[name.strip().lower()]
        except KeyError as exc:
            raise KeyError(f"unknown framework adapter: {name}") from exc

    def create(self, name: str, context: AdapterContext) -> FrameworkAdapter:
        adapter = self.descriptor(name).factory(context)
        if not isinstance(adapter, FrameworkAdapter):
            raise TypeError(f"adapter {name!r} did not return FrameworkAdapter")
        return adapter

    def compatibility(self, name: str) -> FrameworkCompatibility:
        factory = self.descriptor(name).factory
        method = getattr(factory, "compatibility", None)
        if callable(method):
            value = method()
            if isinstance(value, FrameworkCompatibility):
                return value
        return self.create(name, AdapterContext(framework=name)).compatibility()


def default_registry(*, discover: bool = True) -> FrameworkAdapterRegistry:
    registry = FrameworkAdapterRegistry()
    from .autogen import AutoGenAdapter
    from .camel import CAMELAdapter
    from .metagpt import MetaGPTAdapter

    registry.register("camel", CAMELAdapter, source="builtin")
    registry.register("autogen", AutoGenAdapter, source="builtin")
    registry.register("metagpt", MetaGPTAdapter, source="builtin")
    if discover:
        registry.discover()
    return registry
