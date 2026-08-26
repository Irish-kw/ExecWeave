from __future__ import annotations

from pathlib import Path

MARKER = "<!-- v0.6.3-live -->"
FILES = {
    "README.md": {
        "title": "### v0.6.3 live observability",
        "body": """Use the same live session in either the browser or terminal:\n\n```bash\nexecweave top -- codex          # Terminal dashboard\nexecweave top --open -- codex   # Terminal + Web Viewer\n```\n\nLive updates use incremental snapshots/deltas with bounded history instead of repeatedly rebuilding and transferring the full graph. Live and standalone viewers support a persistent Dark/Light theme switch. On Linux, very large recursive filesystem scopes are preflighted and automatically fall back from inotify to polling when needed, so an exhausted inotify watch pool does not abort the session.\n\n`execweave live --open -- cursor` is supported for generic runtime telemetry. For Cursor semantic hooks and conservative tool/process correlation, use `execweave-cursor-record --open -- cursor`.\n\nRun the reproducible graph scalability benchmark with `execweave-scalability`; CI covers 10k, 100k, and 1M synthetic events.\n""",
    },
    "README.zh-TW.md": {
        "title": "### v0.6.3 即時可觀測性",
        "body": """同一個 live session 可以用瀏覽器或 Terminal 查看：\n\n```bash\nexecweave top -- codex          # Terminal dashboard\nexecweave top --open -- codex   # Terminal + Web Viewer\n```\n\nLive 更新改用增量 snapshot/delta 與有界歷史，不再反覆重建並傳送整張 graph。Live 與 standalone Viewer 都支援會記住偏好的 Dark/Light 切換。在 Linux 上，超大型 recursive filesystem scope 會先做資源預檢；若 inotify watch 空間不足，會自動降級為 polling，因此不會因 inotify watch exhaustion 直接中止 session。\n\n`execweave live --open -- cursor` 可用於通用 runtime telemetry；若需要 Cursor semantic hooks 與保守的 tool/process correlation，請使用 `execweave-cursor-record --open -- cursor`。\n\n可用 `execweave-scalability` 重現 graph scalability benchmark；CI 覆蓋 10k、100k 與 1M synthetic events。\n""",
    },
    "README.zh-CN.md": {
        "title": "### v0.6.3 实时可观测性",
        "body": """同一个 live session 可以使用浏览器或 Terminal 查看：\n\n```bash\nexecweave top -- codex          # Terminal dashboard\nexecweave top --open -- codex   # Terminal + Web Viewer\n```\n\nLive 更新改用增量 snapshot/delta 与有界历史，不再反复重建并传输整张 graph。Live 与 standalone Viewer 都支持会记住偏好的 Dark/Light 切换。在 Linux 上，超大型 recursive filesystem scope 会先进行资源预检；如果 inotify watch 空间不足，会自动降级为 polling，因此不会因 inotify watch exhaustion 直接终止 session。\n\n`execweave live --open -- cursor` 可用于通用 runtime telemetry；如需 Cursor semantic hooks 与保守的 tool/process correlation，请使用 `execweave-cursor-record --open -- cursor`。\n\n可用 `execweave-scalability` 重现 graph scalability benchmark；CI 覆盖 10k、100k 和 1M synthetic events。\n""",
    },
    "README.ja.md": {
        "title": "### v0.6.3 ライブ可観測性",
        "body": """同じ live session をブラウザまたは Terminal で確認できます：\n\n```bash\nexecweave top -- codex          # Terminal dashboard\nexecweave top --open -- codex   # Terminal + Web Viewer\n```\n\nLive 更新は増分 snapshot/delta と有界履歴を使用し、graph 全体の再構築・再送を繰り返しません。Live と standalone Viewer は、設定を保持する Dark/Light 切り替えに対応します。Linux では非常に大きな recursive filesystem scope を事前に確認し、inotify watch 容量が不足する場合は自動的に polling へフォールバックするため、inotify watch exhaustion で session 全体が停止しません。\n\n`execweave live --open -- cursor` は汎用 runtime telemetry に対応します。Cursor semantic hooks と保守的な tool/process correlation が必要な場合は `execweave-cursor-record --open -- cursor` を使用してください。\n\n`execweave-scalability` で graph scalability benchmark を再現でき、CI は 10k、100k、1M synthetic events を検証します。\n""",
    },
    "README.ko.md": {
        "title": "### v0.6.3 라이브 관측성",
        "body": """동일한 live session을 브라우저 또는 Terminal에서 확인할 수 있습니다:\n\n```bash\nexecweave top -- codex          # Terminal dashboard\nexecweave top --open -- codex   # Terminal + Web Viewer\n```\n\nLive 업데이트는 증분 snapshot/delta와 제한된 이력을 사용하므로 전체 graph를 반복해서 재구성하고 전송하지 않습니다. Live 및 standalone Viewer는 선택을 기억하는 Dark/Light 전환을 지원합니다. Linux에서는 매우 큰 recursive filesystem scope를 사전 점검하고 inotify watch 용량이 부족하면 자동으로 polling으로 전환하므로 inotify watch exhaustion 때문에 session 전체가 중단되지 않습니다.\n\n`execweave live --open -- cursor`는 일반 runtime telemetry에 사용할 수 있습니다. Cursor semantic hooks와 보수적인 tool/process correlation이 필요하면 `execweave-cursor-record --open -- cursor`를 사용하세요.\n\n`execweave-scalability`로 graph scalability benchmark를 재현할 수 있으며 CI는 10k, 100k, 1M synthetic events를 검증합니다.\n""",
    },
}


def update(path: Path, title: str, body: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("v0.6.2", "v0.6.3")
    if "execweave live --open -- cursor" not in text:
        needle = "execweave live --open -- gemini"
        start = text.find(needle)
        if start < 0:
            raise RuntimeError(f"{path}: live Gemini example not found")
        fence = text.find("\n```", start)
        if fence < 0:
            raise RuntimeError(f"{path}: closing live example fence not found")
        text = text[:fence] + "\n\n# Cursor\nexecweave live --open -- cursor" + text[fence:]
    if MARKER not in text:
        needle = "execweave live --open -- cursor"
        start = text.find(needle)
        fence = text.find("\n```", start)
        if start < 0 or fence < 0:
            raise RuntimeError(f"{path}: Cursor live example block not found")
        insert_at = fence + len("\n```")
        block = f"\n\n{MARKER}\n{title}\n\n{body.strip()}\n"
        text = text[:insert_at] + block + text[insert_at:]
    path.write_text(text, encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    for filename, config in FILES.items():
        update(root / filename, config["title"], config["body"])
        print(filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
