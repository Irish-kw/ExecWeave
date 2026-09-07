#!/usr/bin/env python3
"""Expose pytest failures as GitHub check annotations without masking failure."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def _workflow_escape(value: str) -> str:
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("junit_xml", type=Path)
    args = parser.parse_args()

    root = ET.parse(args.junit_xml).getroot()
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd())).resolve()
    for case in root.iter("testcase"):
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is None:
            continue
        file_name = case.get("file", "")
        path = Path(file_name)
        if path.is_absolute():
            try:
                path = path.resolve().relative_to(workspace)
            except ValueError:
                pass
        title = f"pytest: {case.get('name', 'unknown test')}"
        message = (problem.get("message") or problem.text or "pytest failure").strip()
        print(
            f"::error file={_workflow_escape(path.as_posix())},"
            f"title={_workflow_escape(title)}::{_workflow_escape(message)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
