from __future__ import annotations

import re
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
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)|<img\b", re.I)


def translated_path(stem: str, lang: str) -> Path:
    if stem == "README":
        return Path(f"README.{lang}.md")
    return Path(f"{stem}.{lang}.md")


def strip_nav(text: str) -> str:
    text = re.sub(r"<!-- i18n-nav:start -->.*?<!-- i18n-nav:end -->\s*", "", text, flags=re.S)
    return text


def signature(text: str) -> dict[str, object]:
    body = strip_nav(text)
    headings = [len(m.group(1)) for m in HEADING_RE.finditer(body)]
    fences = [m.group(1).strip() for m in FENCE_RE.finditer(body)]
    # A well-formed fenced document has opening/closing pairs. Keep only opening languages.
    fence_langs = fences[::2] if len(fences) % 2 == 0 else fences
    table_lines = [line for line in body.splitlines() if line.lstrip().startswith("|")]
    links = [m.group(1) for m in LINK_RE.finditer(body)]
    images = len(IMAGE_RE.findall(body))
    return {
        "bytes": len(body.encode("utf-8")),
        "headings": headings,
        "fence_count": len(fences) // 2,
        "fence_langs": fence_langs,
        "table_lines": len(table_lines),
        "links": len(links),
        "images": images,
    }


def compare(src: dict[str, object], dst: dict[str, object]) -> list[str]:
    issues: list[str] = []
    ratio = dst["bytes"] / max(1, src["bytes"])
    if ratio < 0.62:
        issues.append(f"size ratio {ratio:.2f} < 0.62")
    if dst["headings"] != src["headings"]:
        issues.append(f"heading levels {dst['headings']} != {src['headings']}")
    if dst["fence_count"] != src["fence_count"]:
        issues.append(f"code blocks {dst['fence_count']} != {src['fence_count']}")
    if dst["fence_langs"] != src["fence_langs"]:
        issues.append(f"code block languages {dst['fence_langs']} != {src['fence_langs']}")
    if dst["table_lines"] != src["table_lines"]:
        issues.append(f"table lines {dst['table_lines']} != {src['table_lines']}")
    if dst["images"] != src["images"]:
        issues.append(f"images {dst['images']} != {src['images']}")
    # Links may point to localized siblings, but the count should stay structurally aligned.
    if dst["links"] != src["links"]:
        issues.append(f"links {dst['links']} != {src['links']}")
    return issues


def main() -> int:
    failures = 0
    checked = 0
    for english_path, stem in DOCS:
        if not english_path.exists():
            print(f"MISSING canonical: {english_path}")
            failures += len(LANGS)
            continue
        src_text = english_path.read_text(encoding="utf-8")
        src_sig = signature(src_text)
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
