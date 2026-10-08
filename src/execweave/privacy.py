"""Fail-closed content-capture policy for observed live runs.

OS/process/file/network evidence remains part of ExecWeave's observation model. This
policy governs provider/model plaintext copied into the content-addressed store.
`execweave live` and `execweave top` set an explicit mode for every observed child:
full capture by default, because the run stays on the user's own machine for the user
to inspect, or metadata-only with `--metadata-only`. Invalid configured values resolve
to metadata-only rather than full plaintext. Standalone diagnostic integrations retain
their historical full-capture behavior when no policy environment is present.
"""
from __future__ import annotations

import argparse
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


def add_content_capture_arguments(parser: argparse.ArgumentParser) -> None:
    """Expose the provider/model plaintext policy shared by `live` and `top`.

    ExecWeave records on the user's own machine for the user to inspect, so full
    provider/model content is the default. `--metadata-only` is the opt-out;
    `--capture-content` remains accepted and selects the default explicitly.
    """
    capture = parser.add_mutually_exclusive_group()
    capture.add_argument(
        "--capture-content",
        action="store_const",
        const=_FULL,
        dest="content_capture",
        help="Record full provider/model plaintext (the default; kept for explicit use)",
    )
    capture.add_argument(
        "--metadata-only",
        action="store_const",
        const=_METADATA_ONLY,
        dest="content_capture",
        help="Record provider/model metadata only; no prompts, responses or tool values are stored",
    )
    parser.set_defaults(content_capture=_FULL)
