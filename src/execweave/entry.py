from __future__ import annotations

import sys

from . import cli


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "top":
        from .top_cli import main as top_main

        return top_main(args[1:])
    if args and args[0] == "view":
        from .view_cli import main as view_main

        return view_main(args[1:])
    return cli.main(args)
