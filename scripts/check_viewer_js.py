from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path


def extract_viewer_script(html_path: Path, output_path: Path) -> Path:
    html = html_path.read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
    if not scripts:
        raise ValueError(f"no inline script found in {html_path}")
    output_path.write_text(scripts[-1], encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Syntax-check ExecWeave standalone viewer JavaScript")
    parser.add_argument("html", type=Path)
    parser.add_argument("--output", type=Path, default=Path("viewer.inline.js"))
    args = parser.parse_args()

    node = shutil.which("node")
    if node is None:
        raise RuntimeError("node executable is required for viewer JavaScript syntax validation")

    script = extract_viewer_script(args.html, args.output)
    result = subprocess.run([node, "--check", str(script)], check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
