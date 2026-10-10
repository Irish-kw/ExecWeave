"""Optional publication of a run digest to an independently administered GitHub Issue.

The remote HTTP acknowledgement is evidence of submission, not proof that the
target is append-only or inaccessible to the observed workload. An external
verifier must retrieve the comment from the trust domain and compare its digest.
Never put the authentication token, run contents, or local paths in the comment.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from typing import Any, Callable

_TARGET = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9_.-]{1,100})#([1-9][0-9]{0,8})$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_ENV = "EXECWEAVE_INTEGRITY_GITHUB_TOKEN"
_MAX_RESPONSE_BYTES = 16 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def parse_github_issue_target(value: str) -> tuple[str, str, int]:
    match = _TARGET.fullmatch(value or "")
    if match is None:
        raise ValueError("GitHub anchor target must be OWNER/REPO#ISSUE")
    return match[1], match[2], int(match[3])


def github_anchor_text(digest: str) -> str:
    if not _DIGEST.fullmatch(digest):
        raise ValueError("anchor digest must be lowercase SHA-256 hex")
    return (
        "ExecWeave external digest record (v1)\n"
        f"manifest_body_sha256: {digest}\n"
        "scope: run-local integrity manifest; independent retrieval required\n"
        "Trust note: this comment acknowledges publication, not task or "
        "observation completeness."
    )


def publish_github_anchor(
    target: str,
    digest: str,
    *,
    token: str | None = None,
    opener: Callable[..., Any] | None = None,
) -> dict[str, object]:
    """Submit only a digest. No fallback from a failed HTTPS post to a local file.

    Acknowledgement is bounded and verified against the exact requested target.
    The returned state is deliberately weaker than independent verification.
    """
    owner, repo, number = parse_github_issue_target(target)
    body = github_anchor_text(digest)
    secret = token if token is not None else os.environ.get(_TOKEN_ENV)
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError(f"GitHub anchoring requires {_TOKEN_ENV}")
    if any(ord(char) < 33 or ord(char) > 126 for char in secret):
        raise ValueError("invalid GitHub token characters")
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments"
    payload = json.dumps({"body": body}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ExecWeave-Integrity-Anchor",
        },
    )
    opener = opener or urllib.request.build_opener(_NoRedirect()).open
    try:
        with opener(request, timeout=15) as response:
            if response.getcode() != 201:
                raise ValueError("GitHub did not acknowledge comment creation")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        # Never echo HTTP response bodies: provider errors might reflect headers.
        raise ValueError("external GitHub digest publication failed") from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("GitHub acknowledgement exceeds size limit")
    try:
        value = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid GitHub anchor acknowledgement") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid GitHub anchor acknowledgement")
    comment_id = value.get("id")
    comment_url = value.get("html_url")
    # GitHub canonicalizes owner/repository casing in URLs. Compare path segments
    # case-insensitively while requiring the exact issue and comment identity.
    if not isinstance(comment_id, int) or isinstance(comment_id, bool) or comment_id < 1:
        raise ValueError("GitHub anchor acknowledgement target/body mismatch")
    parsed = urlsplit(comment_url) if isinstance(comment_url, str) else None
    expected_path = f"/{owner}/{repo}/issues/{number}"
    if (parsed is None or parsed.scheme != "https"
            or parsed.netloc != "github.com"
            or parsed.path.casefold() != expected_path.casefold()
            or parsed.query or parsed.fragment != f"issuecomment-{comment_id}"
            or value.get("body") != body):
        raise ValueError("GitHub anchor acknowledgement target/body mismatch")
    return {
        "state": "submitted_not_independently_verified",
        "target": target,
        "manifest_body_sha256": digest,
        "comment_id": comment_id,
        "comment_url": comment_url,
    }
