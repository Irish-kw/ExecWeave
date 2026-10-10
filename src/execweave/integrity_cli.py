from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .integrity import seal_run_integrity, verify_run_integrity
from .external_anchor import publish_github_anchor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-integrity",
        description="Seal or verify a completed ExecWeave run for local post-seal corruption detection.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    seal = subparsers.add_parser("seal", help="write integrity.json for a completed run")
    seal.add_argument("run_dir", type=Path)
    seal.add_argument(
        "--anchor-github", metavar="OWNER/REPO#ISSUE",
        help="publish digest to a separately controlled GitHub Issue after local seal",
    )
    anchor = subparsers.add_parser("anchor", help="retry external digest publication for a locally sealed run")
    anchor.add_argument("run_dir", type=Path)
    anchor.add_argument(
        "--github-target", required=True, metavar="OWNER/REPO#ISSUE",
        help="target GitHub Issue that the observed workload cannot edit",
    )
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
        report = {
            "status": "sealed",
            "external_anchor_state": "unanchored",
            "run_dir": str(args.run_dir.expanduser().resolve()),
            "sealed_file_count": manifest["sealed_file_count"],
            "manifest_body_sha256": manifest["manifest_body_sha256"],
            "malicious_writer_resistance": False,
        }
        if args.anchor_github:
            try:
                submitted = publish_github_anchor(
                    args.anchor_github, manifest["manifest_body_sha256"]
                )
            except (OSError, TypeError, ValueError) as exc:
                # The local seal already exists; retry with the 'anchor' command.
                report["external_anchor_error"] = str(exc)
                print(json.dumps(report, sort_keys=True))
                return 3
            report["external_anchor_state"] = submitted["state"]
            report["external_anchor_comment_url"] = submitted["comment_url"]
        print(json.dumps(report, sort_keys=True))
        return 0

    if args.command == "anchor":
        checked = verify_run_integrity(args.run_dir)
        if not checked.valid or checked.manifest_body_sha256 is None:
            print(json.dumps({
                "status": "rejected", "external_anchor_state": "unanchored",
                "local_integrity_valid": False, "errors": list(checked.errors),
            }, sort_keys=True))
            return 1
        try:
            submitted = publish_github_anchor(
                args.github_target, checked.manifest_body_sha256
            )
        except (OSError, TypeError, ValueError) as exc:
            print(json.dumps({
                "status": "sealed_locally", "external_anchor_state": "unanchored",
                "external_anchor_error": str(exc),
            }, sort_keys=True))
            return 3
        print(json.dumps({
            "status": "submitted",
            "external_anchor_state": submitted["state"],
            "manifest_body_sha256": checked.manifest_body_sha256,
            "external_anchor_comment_url": submitted["comment_url"],
            "malicious_writer_resistance": False,
        }, sort_keys=True))
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
