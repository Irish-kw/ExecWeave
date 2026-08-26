from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

LANGS = ["zh-TW", "zh-CN", "ja", "ko", "fr", "de", "ru"]
DOCS = [
    (Path("README.md"), "README"),
    (Path("docs/phase-1-runtime-collection.md"), "docs/phase-1-runtime-collection"),
    (Path("docs/phase-2-execution-graph.md"), "docs/phase-2-execution-graph"),
    (Path("docs/live-graph.md"), "docs/live-graph"),
    (Path("docs/semantic-telemetry.md"), "docs/semantic-telemetry"),
    (Path("docs/claude-code-hooks.md"), "docs/claude-code-hooks"),
    (Path("docs/codex-hooks.md"), "docs/codex-hooks"),
    (Path("docs/gemini-hooks.md"), "docs/gemini-hooks"),
    (Path("docs/cursor-hooks.md"), "docs/cursor-hooks"),
    (Path("docs/opencode-plugin.md"), "docs/opencode-plugin"),
    (Path("docs/inference-gateway.md"), "docs/inference-gateway"),
    (Path("docs/model-runtime.md"), "docs/model-runtime"),
    (Path("docs/security-analysis.md"), "docs/security-analysis"),
]

FENCE_RE = re.compile(r"^```([^\n`]*)$", re.M)
HEADING_RE = re.compile(r"^(#{1,6})\s+.+$", re.M)
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
    headings = [len(m.group(1)) for m in HEADING_RE.finditer(body)]
    fences = [m.group(1).strip() for m in FENCE_RE.finditer(body)]
    fence_langs = fences[::2] if len(fences) % 2 == 0 else fences
    table_lines = [line for line in body.splitlines() if line.lstrip().startswith("|")]
    images = len(IMAGE_RE.findall(body))
    return {
        "bytes": len(body.encode("utf-8")),
        "headings": headings,
        "fence_count": len(fences) // 2,
        "fence_langs": fence_langs,
        "table_lines": len(table_lines),
        "images": images,
    }


def is_subsequence(needed: list[int], available: list[int]) -> bool:
    it = iter(available)
    return all(any(value == item for value in it) for item in needed)


def compare(src: dict[str, object], dst: dict[str, object]) -> list[str]:
    issues: list[str] = []
    ratio = dst["bytes"] / max(1, src["bytes"])
    if ratio < 0.62:
        issues.append(f"size ratio {ratio:.2f} < 0.62")

    src_headings = src["headings"]
    dst_headings = dst["headings"]
    if not is_subsequence(src_headings, dst_headings):
        issues.append(
            f"canonical heading-level sequence {src_headings} is not contained in {dst_headings}"
        )

    if dst["fence_count"] < src["fence_count"]:
        issues.append(f"code blocks {dst['fence_count']} < canonical {src['fence_count']}")

    src_langs = Counter(src["fence_langs"])
    dst_langs = Counter(dst["fence_langs"])
    missing_langs = {
        lang: count - dst_langs[lang]
        for lang, count in src_langs.items()
        if dst_langs[lang] < count
    }
    if missing_langs:
        issues.append(f"missing canonical code-block languages/counts: {missing_langs}")

    if dst["table_lines"] < src["table_lines"]:
        issues.append(f"table lines {dst['table_lines']} < canonical {src['table_lines']}")
    if dst["images"] < src["images"]:
        issues.append(f"images {dst['images']} < canonical {src['images']}")
    return issues


def main() -> int:
    failures = 0
    checked = 0
    for english_path, stem in DOCS:
        if not english_path.exists():
            print(f"MISSING canonical: {english_path}")
            failures += len(LANGS)
            continue
        src_sig = signature(english_path.read_text(encoding="utf-8"))
        print(f"\n[{english_path}] canonical bytes={src_sig['bytes']}")
        for lang in LANGS:
            path = translated_path(stem, lang)
            checked += 1
            if not path.exists():
                failures += 1
                print(f"  FAIL {lang:5} {path}: missing file")
                continue
            dst_sig = signature(path.read_text(encoding="utf-8"))
            issues = compare(src_sig, dst_sig)
            ratio = dst_sig["bytes"] / max(1, src_sig["bytes"])
            if issues:
                failures += 1
                print(f"  FAIL {lang:5} ratio={ratio:.2f} {path}")
                for issue in issues:
                    print(f"       - {issue}")
            else:
                print(f"  PASS {lang:5} ratio={ratio:.2f} {path}")

    print(f"\nchecked={checked} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
