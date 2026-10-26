from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CollectionScopeDecision:
    watch_root: Path
    collect_filesystem: bool
    broad_scope: bool
    reason: str | None = None


def _safe_resolve(path: Path) -> Path:
    return path.expanduser().resolve()


def broad_filesystem_roots() -> set[Path]:
    """Return platform-local roots that are unsafe for implicit recursive watching.

    The set intentionally stays small and structural: filesystem root, the user's
    home directory, and the parent that contains user homes. ExecWeave does not
    maintain a broad path-ignore list here because a security/observability tool
    must not silently hide project activity merely for performance.
    """

    home = _safe_resolve(Path.home())
    roots = {home}

    anchor = Path(home.anchor) if home.anchor else None
    if anchor is not None:
        try:
            roots.add(_safe_resolve(anchor))
        except OSError:
            pass

    parent = home.parent
    if parent != home:
        try:
            roots.add(_safe_resolve(parent))
        except OSError:
            pass

    return roots


def protect_filesystem_scope(
    watch_root: str | Path,
    *,
    collect_filesystem: bool,
    allow_broad_scope: bool = False,
    warn: bool = True,
) -> CollectionScopeDecision:
    """Disable recursive filesystem observation for dangerously broad roots.

    Process/network collection is unaffected. This is a resource-safety guard,
    not an evidence reinterpretation: if filesystem collection is suppressed the
    caller is told explicitly. Advanced programmatic callers may opt in with
    ``allow_broad_scope=True`` after making that scope choice deliberately.
    """

    root = _safe_resolve(Path(watch_root))
    broad = root in broad_filesystem_roots()
    if not collect_filesystem or not broad or allow_broad_scope:
        return CollectionScopeDecision(
            watch_root=root,
            collect_filesystem=collect_filesystem,
            broad_scope=broad,
        )

    reason = (
        "ExecWeave disabled recursive filesystem observation because the watch root "
        f"is unusually broad: {root}. Process and network collection remain enabled. "
        "Run from a project directory or pass a narrower --watch-root to collect files."
    )
    if warn:
        warnings.warn(reason, RuntimeWarning, stacklevel=2)
    return CollectionScopeDecision(
        watch_root=root,
        collect_filesystem=False,
        broad_scope=True,
        reason=reason,
    )
