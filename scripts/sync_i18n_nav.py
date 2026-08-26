from __future__ import annotations

import argparse
import re
from pathlib import Path


LANGUAGES = [
    ("en", "English", ""),
    ("zh-TW", "繁體中文", ".zh-TW"),
    ("zh-CN", "简体中文", ".zh-CN"),
    ("ja", "日本語", ".ja"),
    ("ko", "한국어", ".ko"),
    ("fr", "Français", ".fr"),
    ("de", "Deutsch", ".de"),
    ("ru", "Русский", ".ru"),
]

DOC_BASE_NAMES = [
    "phase-1-runtime-collection.md",
    "phase-2-execution-graph.md",
    "live-graph.md",
    "semantic-telemetry.md",
    "claude-code-hooks.md",
    "codex-hooks.md",
    "gemini-hooks.md",
    "cursor-hooks.md",
    "opencode-plugin.md",
    "inference-gateway.md",
    "model-runtime.md",
    "security-analysis.md",
]

START = "<!-- i18n-nav:start -->"
END = "<!-- i18n-nav:end -->"


def variant_name(base_name: str, suffix: str) -> str:
    if not base_name.endswith(".md"):
        raise ValueError(base_name)
    stem = base_name[:-3]
    return f"{stem}{suffix}.md"


def language_for_path(path: Path, base_name: str) -> str:
    if path.name == base_name:
        return "en"
    stem = base_name[:-3]
    for code, _label, suffix in LANGUAGES[1:]:
        if path.name == f"{stem}{suffix}.md":
            return code
    raise ValueError(f"cannot determine language for {path}")


def render_nav(base_name: str, current_language: str) -> str:
    rows: list[str] = [START, '<p align="center">']
    for index, (code, label, suffix) in enumerate(LANGUAGES):
        target = variant_name(base_name, suffix)
        if code == current_language:
            item = f"  <strong>{label}</strong>"
        else:
            item = f'  <a href="{target}">{label}</a>'
        if index != len(LANGUAGES) - 1:
            item += " |"
        rows.append(item)
    rows.extend(["</p>", END])
    return "\n".join(rows)


def replace_nav(text: str, nav: str) -> str:
    marker_pattern = re.compile(
        rf"{re.escape(START)}.*?{re.escape(END)}",
        flags=re.DOTALL,
    )
    if marker_pattern.search(text):
        return marker_pattern.sub(nav, text, count=1)

    centered_nav_pattern = re.compile(
        r'<p align="center">(?:(?!</p>).)*English(?:(?!</p>).)*</p>',
        flags=re.DOTALL,
    )
    if centered_nav_pattern.search(text):
        return centered_nav_pattern.sub(nav, text, count=1)

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            insertion = index + 1
            lines[insertion:insertion] = ["", nav, ""]
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    return nav + "\n\n" + text


def families(root: Path) -> list[tuple[Path, str]]:
    docs = root / "docs"
    return [(root, "README.md"), *[(docs, name) for name in DOC_BASE_NAMES]]


def sync(root: Path, check: bool) -> int:
    changed: list[Path] = []
    errors: list[str] = []

    for directory, base_name in families(root):
        paths = [directory / variant_name(base_name, suffix) for _code, _label, suffix in LANGUAGES]
        missing = [path for path in paths if not path.exists()]
        if missing:
            errors.append(f"{base_name}: missing variants: {', '.join(str(p) for p in missing)}")
            continue

        for path in paths:
            current_language = language_for_path(path, base_name)
            old = path.read_text(encoding="utf-8")
            new = replace_nav(old, render_nav(base_name, current_language))
            if new != old:
                changed.append(path)
                if not check:
                    path.write_text(new, encoding="utf-8")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2

    if changed:
        mode = "would update" if check else "updated"
        for path in changed:
            print(f"{mode}: {path.relative_to(root)}")
        return 1 if check else 0

    print("i18n navigation is synchronized")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize eight-language Markdown navigation blocks.")
    parser.add_argument("--check", action="store_true", help="report drift without modifying files")
    args = parser.parse_args()
    return sync(Path(__file__).resolve().parents[1], args.check)


if __name__ == "__main__":
    raise SystemExit(main())
