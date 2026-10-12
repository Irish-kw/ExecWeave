from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .integrity import seal_run_integrity, verify_run_integrity
from .reader_identity import reader_identity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-integrity",
        description="Seal or verify completed ExecWeave run files for local consistency only.",
    )
    subs = parser.add_subparsers(dest="command", required=True)
    seal = subs.add_parser("seal", help="create a local integrity manifest")
    seal.add_argument("run_dir", type=Path)
    verify = subs.add_parser("verify", help="check local manifest and sealed files")
    verify.add_argument("run_dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seal":
        try:
            manifest = seal_run_integrity(args.run_dir)
        except (FileExistsError, OSError, TypeError, ValueError) as exc:
            print(f"ExecWeave integrity error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({
            "status": "sealed",
            "run_dir": str(args.run_dir.expanduser().resolve()),
            "sealed_file_count": manifest["sealed_file_count"],
            "manifest_body_sha256": manifest["manifest_body_sha256"],
            "local_integrity_valid": True,
            "malicious_writer_resistance": False,
            "reader": reader_identity(),
        }, sort_keys=True))
        return 0

    result = verify_run_integrity(args.run_dir)
    report = result.to_dict()
    report["status"] = "locally_valid" if result.valid else "local_integrity_failed"
    report["local_integrity_valid"] = result.valid
    report["malicious_writer_resistance"] = False
    report["reader"] = reader_identity()
    print(json.dumps(report, sort_keys=True))
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
