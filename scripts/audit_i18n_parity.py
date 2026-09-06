from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

ALL_LANGS = ["zh-TW", "zh-CN", "ja", "ko", "fr", "de", "ru"]
DEFAULT_STRICT_LANGS = ["fr", "de", "ru"]
ALL_LANGUAGE_STRICT_STEMS = {
    "docs/live-graph",
    "docs/evidence-grades",
    "docs/rule-packs",
    "docs/run-integrity",
}
DOCS = [
    (Path("README.md"), "README"),
    (Path("docs/phase-1-runtime-collection.md"), "docs/phase-1-runtime-collection"),
    (Path("docs/phase-2-execution-graph.md"), "docs/phase-2-execution-graph"),
    (Path("docs/live-graph.md"), "docs/live-graph"),
    (Path("docs/semantic-telemetry.md"), "docs/semantic-telemetry"),
    (Path("docs/claude-code-hooks.md"), "docs/claude-code-hooks"),
    (Path("docs/codex-hooks.md"), "docs/codex-hooks"),
    (Path("docs/cursor-hooks.md"), "docs/cursor-hooks"),
    (Path("docs/opencode-plugin.md"), "docs/opencode-plugin"),
    (Path("docs/inference-gateway.md"), "docs/inference-gateway"),
    (Path("docs/model-runtime.md"), "docs/model-runtime"),
    (Path("docs/security-analysis.md"), "docs/security-analysis"),
    (Path("docs/evidence-grades.md"), "docs/evidence-grades"),
    (Path("docs/rule-packs.md"), "docs/rule-packs"),
    (Path("docs/run-integrity.md"), "docs/run-integrity"),
]

README_REQUIRED_SNIPPETS = [
    "python -m pip install -U execweave",
    "execweave live --open -- cursor",
    "execweave live --open -- opencode",
    "execweave live --open -- ollama serve",
    "execweave top -- codex",
    "conversations.json",
    "LM Studio",
    "LiteLLM Proxy",
    "complete_from_source: true",
    "PolyForm Noncommercial License 1.0.0",
]

HEADING_RE = re.compile(r"^(#{1,6})\s+.+$", re.M)
FENCED_BLOCK_RE = re.compile(r"```[^\n`]*\n(.*?)\n```", re.S)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)|<img\b", re.I)


def translated_path(stem: str, lang: str) -> Path:
    if stem == "README":
        return Path(f"README.{lang}.md")
    return Path(f"{stem}.{lang}.md")


def strip_nav(text: str) -> str:
    return re.sub(
        r"<!-- i18n-nav:start -->.*?<!-- i18n-nav:end -->\s*",
        "",
        text,
        flags=re.S,
    )


def signature(text: str) -> dict[str, object]:
    body = strip_nav(text)
    heading_counts = Counter(len(match.group(1)) for match in HEADING_RE.finditer(body))
    code_blocks = FENCED_BLOCK_RE.findall(body)
    table_lines = [line for line in body.splitlines() if line.lstrip().startswith("|")]
    images = len(IMAGE_RE.findall(body))
    return {
        "bytes": len(body.encode("utf-8")),
        "heading_counts": heading_counts,
        "code_block_count": len(code_blocks),
        "table_lines": len(table_lines),
        "images": images,
    }


def compare_structure(src: dict[str, object], dst: dict[str, object]) -> list[str]:
    issues: list[str] = []
    ratio = int(dst["bytes"]) / max(1, int(src["bytes"]))
    if ratio < 0.62:
        issues.append(f"size ratio {ratio:.2f} < 0.62")

    src_headings: Counter[int] = src["heading_counts"]  # type: ignore[assignment]
    dst_headings: Counter[int] = dst["heading_counts"]  # type: ignore[assignment]
    missing_headings = {
        level: count - dst_headings[level]
        for level, count in src_headings.items()
        if dst_headings[level] < count
    }
    if missing_headings:
        issues.append(f"missing canonical heading levels/counts: {missing_headings}")

    if int(dst["code_block_count"]) < int(src["code_block_count"]):
        issues.append(
            f"code blocks {dst['code_block_count']} < canonical {src['code_block_count']}"
        )
    if int(dst["table_lines"]) < int(src["table_lines"]):
        issues.append(f"table lines {dst['table_lines']} < canonical {src['table_lines']}")
    if int(dst["images"]) < int(src["images"]):
        issues.append(f"images {dst['images']} < canonical {src['images']}")
    return issues


def audit_coverage() -> int:
    failures = 0
    for english_path, stem in DOCS:
        if not english_path.exists():
            print(f"FAIL canonical missing: {english_path}")
            failures += 1
            continue
        for lang in ALL_LANGS:
            path = translated_path(stem, lang)
            if not path.exists():
                print(f"FAIL missing {lang:5}: {path}")
                failures += 1

    readmes = [("en", Path("README.md"))]
    readmes.extend((lang, Path(f"README.{lang}.md")) for lang in ALL_LANGS)
    for lang, path in readmes:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        missing = [snippet for snippet in README_REQUIRED_SNIPPETS if snippet not in text]
        if missing:
            print(f"FAIL {lang:5} {path}: missing stable README anchors {missing}")
            failures += 1
    return failures


def languages_for_stem(stem: str, requested: list[str]) -> list[str]:
    languages = list(requested)
    if stem in ALL_LANGUAGE_STRICT_STEMS:
        languages.extend(ALL_LANGS)
    return list(dict.fromkeys(languages))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit eight-language documentation coverage and structural translation parity. "
            "Natural-language text inside fenced diagrams may be translated."
        )
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=ALL_LANGS,
        default=DEFAULT_STRICT_LANGS,
        help=(
            "languages to check structurally against English across the documentation set; "
            "selected high-risk documents are always checked across all seven translations"
        ),
    )
    args = parser.parse_args()

    failures = audit_coverage()
    checked = 0
    for english_path, stem in DOCS:
        if not english_path.exists():
            continue
        src_sig = signature(english_path.read_text(encoding="utf-8"))
        print(f"\n[{english_path}] canonical bytes={src_sig['bytes']}")
        for lang in languages_for_stem(stem, args.languages):
            path = translated_path(stem, lang)
            if not path.exists():
                continue
            checked += 1
            dst_sig = signature(path.read_text(encoding="utf-8"))
            issues = compare_structure(src_sig, dst_sig)
            ratio = int(dst_sig["bytes"]) / max(1, int(src_sig["bytes"]))
            if issues:
                failures += 1
                print(f"  FAIL {lang:5} ratio={ratio:.2f} {path}")
                for issue in issues:
                    print(f"       - {issue}")
            else:
                print(f"  PASS {lang:5} ratio={ratio:.2f} {path}")

    print(f"\nstrict_checked={checked} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
