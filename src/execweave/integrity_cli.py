from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .integrity import seal_run_integrity, verify_run_integrity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-integrity",
        description="Seal or verify a completed ExecWeave run for local post-seal corruption detection.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    seal = subparsers.add_parser("seal", help="write integrity.json for a completed run")
    seal.add_argument("run_dir", type=Path)
    verify = subparsers.add_parser("verify", help="verify a sealed run")
    verify.add_argument("run_dir", type=Path)
    verify.add_argument(
        "--expected-manifest-body-sha256",
        default=None,
        help=(
            "Expected digest supplied from an external trust domain (for example CI/GitHub); "
            "never read this value from the run directory being verified"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seal":
        try:
            manifest = seal_run_integrity(args.run_dir)
        except (FileExistsError, OSError, TypeError, ValueError) as exc:
            print(f"ExecWeave integrity error: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "status": "sealed",
                    "external_anchor_state": "unanchored",
                    "run_dir": str(args.run_dir.expanduser().resolve()),
                    "sealed_file_count": manifest["sealed_file_count"],
                    "manifest_body_sha256": manifest["manifest_body_sha256"],
                    "malicious_writer_resistance": False,
                },
                sort_keys=True,
            )
        )
        return 0

    result = verify_run_integrity(
        args.run_dir,
        expected_manifest_body_sha256=args.expected_manifest_body_sha256,
    )
    report = result.to_dict()
    report["external_anchor_state"] = (
        "unanchored" if not result.external_anchor_checked
        else "external_digest_match" if result.external_anchor_match is True
        else "external_digest_mismatch_or_invalid"
    )
    # Local consistency verification is not proof against a malicious writer.
    report["malicious_writer_resistance"] = False
    print(json.dumps(report, sort_keys=True))
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
