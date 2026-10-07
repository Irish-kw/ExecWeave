"""Fail-closed content-capture policy for observed live runs.

OS/process/file/network evidence remains part of ExecWeave's observation model. This
policy governs provider/model plaintext copied into the content-addressed store.
`execweave live` and `execweave top` set an explicit mode for every observed child;
invalid configured values resolve to metadata-only rather than full plaintext.
Standalone diagnostic integrations retain their historical behavior when no policy
environment is present, so explicit low-level tooling is not silently redefined.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

CONTENT_CAPTURE_ENV = "EXECWEAVE_CONTENT_CAPTURE"
_METADATA_ONLY = "metadata_only"
_FULL = "full"


@dataclass(frozen=True)
class ContentCapturePolicy:
    mode: str
    state: str
    explicitly_configured: bool

    @property
    def full_content_enabled(self) -> bool:
        return self.mode == _FULL


def content_capture_policy() -> ContentCapturePolicy:
    raw = os.environ.get(CONTENT_CAPTURE_ENV)
    if raw is None:
        # This path is for explicit standalone SDK/diagnostic entry points. The
        # user-facing live/top commands always set a policy before launching the
        # observed workload and its hooks.
        return ContentCapturePolicy(_FULL, "standalone_legacy_full", False)
    normalized = raw.strip().lower().replace("-", "_")
    if normalized == _FULL:
        return ContentCapturePolicy(_FULL, "explicit_full", True)
    if normalized == _METADATA_ONLY:
        return ContentCapturePolicy(_METADATA_ONLY, "explicit_metadata_only", True)
    # Never turn an invalid/misconfigured masking/privacy request into plaintext.
    return ContentCapturePolicy(_METADATA_ONLY, "invalid_fail_closed", True)


def full_content_capture_enabled() -> bool:
    return content_capture_policy().full_content_enabled


def require_full_content_capture() -> None:
    policy = content_capture_policy()
    if not policy.full_content_enabled:
        raise PermissionError(
            "provider plaintext capture is disabled by ExecWeave content policy "
            f"({policy.state})"
        )
