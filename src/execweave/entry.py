from __future__ import annotations

import sys

from . import cli
from .agent_bootstrap import AgentBootstrapResult, bootstrap_supported_agent

_LIVE_VALUE_OPTIONS = {"--watch-root", "--output-dir", "--interval", "--port", "--linger"}
_LIVE_FLAG_OPTIONS = {"--no-files", "--no-network", "--open"}


def _live_command(args: list[str]) -> list[str]:
    if not args or args[0] != "live":
        return []
    tokens = args[1:]
    if "--" in tokens:
        separator = tokens.index("--")
        return tokens[separator + 1 :]

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _LIVE_FLAG_OPTIONS:
            index += 1
            continue
        if token in _LIVE_VALUE_OPTIONS:
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in _LIVE_VALUE_OPTIONS):
            index += 1
            continue
        if token.startswith("-"):
            return []
        return tokens[index:]
    return []


def _announce_bootstrap(result: AgentBootstrapResult) -> None:
    provider = result.provider or "command"
    if result.status == "active":
        action = "updated" if result.changed else "ready"
        print(
            "ExecWeave specialized: active "
            f"({provider}; bootstrap {action}, evidence appears when hooks fire).",
            file=sys.stderr,
            flush=True,
        )
        return
    if result.status == "bootstrap_failed":
        detail = f" {result.detail}" if result.detail else ""
        print(
            "ExecWeave specialized: bootstrap failed "
            f"({provider}); continuing with OS runtime evidence.{detail}",
            file=sys.stderr,
            flush=True,
        )
        return
    detail = f" {result.detail}." if result.detail else ""
    print(
        "ExecWeave specialized: unavailable "
        f"({provider}); collecting OS runtime evidence only.{detail}",
        file=sys.stderr,
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "top":
        from .top_cli import main as top_main

        return top_main(args[1:])
    if args and args[0] in {"view", "graph-view"}:
        from .view_cli import main as view_main

        return view_main(args[1:])
    if args and args[0] == "live":
        command = _live_command(args)
        if command:
            _announce_bootstrap(bootstrap_supported_agent(command))
    return cli.main(args)
