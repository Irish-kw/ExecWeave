from __future__ import annotations

import argparse

_CALLBACK_PATH = "execweave.litellm_callback.execweave_litellm_callback"
_CONFIG = f"""litellm_settings:
  callbacks: {_CALLBACK_PATH}
"""


def callback_path() -> str:
    return _CALLBACK_PATH


def config_fragment() -> str:
    return _CONFIG


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-litellm-callback",
        description=(
            "Print the LiteLLM Proxy callback configuration for privacy-safe ExecWeave routing telemetry."
        ),
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--print-config", action="store_true")
    action.add_argument("--print-callback", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.print_callback:
        print(callback_path())
    else:
        print(config_fragment(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
