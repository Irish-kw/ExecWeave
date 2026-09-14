"""Stable public API for third-party framework semantic adapters."""

from .autogen import AutoGenAdapter
from .base import (
    CANONICAL_EVENT_TYPES,
    AdapterCapabilities,
    AdapterContext,
    AgentRecord,
    CaptureMode,
    ContentCapturePolicy,
    ContentWriter,
    EntityRef,
    FrameworkAdapter,
    FrameworkCompatibility,
    MessageRecord,
    ModelCallRecord,
    ProcessRef,
    SemanticWriter,
    TaskRecord,
    ToolCallRecord,
    stable_id,
)
from .camel import CAMELAdapter
from .metagpt import MetaGPTAdapter
from .registry import AdapterDescriptor, FrameworkAdapterRegistry, default_registry

__all__ = [
    "AdapterCapabilities", "AdapterContext", "AdapterDescriptor", "AgentRecord",
    "AutoGenAdapter", "CAMELAdapter", "CANONICAL_EVENT_TYPES", "CaptureMode",
    "ContentCapturePolicy", "ContentWriter", "EntityRef", "FrameworkAdapter",
    "FrameworkAdapterRegistry", "FrameworkCompatibility", "MessageRecord",
    "MetaGPTAdapter", "ModelCallRecord", "ProcessRef", "SemanticWriter",
    "TaskRecord", "ToolCallRecord", "default_registry", "stable_id",
]
