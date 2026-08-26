from pathlib import Path

REPLACEMENTS = {
    "README.md": (
        "At **1,000,000 events**, the incremental graph retained **0 raw event IDs**. This benchmark measures graph accumulation and snapshot materialization, not end-to-end collector or browser throughput.",
        "At **1,000,000 events**, the incremental in-memory graph did not duplicate raw event IDs; raw evidence remains separate from the materialized graph. This benchmark measures graph accumulation and snapshot materialization, not end-to-end collector or browser throughput.",
    ),
    "README.zh-TW.md": (
        "在 **1,000,000 events** 時，incremental graph 保留的 **raw event IDs 為 0**。這個 benchmark 量測的是 graph accumulation 與 snapshot materialization，不是 end-to-end collector 或 browser throughput。",
        "在 **1,000,000 events** 下，incremental in-memory graph 不會重複保存 raw event IDs；raw evidence 與 materialized graph 維持分離。這個 benchmark 量測的是 graph accumulation 與 snapshot materialization，不是 end-to-end collector 或 browser throughput。",
    ),
    "README.zh-CN.md": (
        "在 **1,000,000 events** 时，incremental graph 保留的 **raw event IDs 为 0**。这个 benchmark 测量的是 graph accumulation 与 snapshot materialization，不是 end-to-end collector 或 browser throughput。",
        "在 **1,000,000 events** 下，incremental in-memory graph 不会重复保存 raw event IDs；raw evidence 与 materialized graph 保持分离。这个 benchmark 测量的是 graph accumulation 与 snapshot materialization，不是 end-to-end collector 或 browser throughput。",
    ),
    "README.ja.md": (
        "**1,000,000 events** 時点で incremental graph が保持する **raw event IDs は 0** です。この benchmark は graph accumulation と snapshot materialization を測定するもので、end-to-end collector や browser throughput の測定ではありません。",
        "**1,000,000 events** 時点で、incremental in-memory graph は raw event IDs を重複保持しません。Raw evidence は materialized graph とは分離されたままです。この benchmark は graph accumulation と snapshot materialization を測定するもので、end-to-end collector や browser throughput の測定ではありません。",
    ),
    "README.ko.md": (
        "**1,000,000 events**에서 incremental graph가 유지한 **raw event IDs는 0개**입니다. 이 benchmark는 graph accumulation과 snapshot materialization을 측정하며 end-to-end collector 또는 browser throughput을 의미하지 않습니다.",
        "**1,000,000 events**에서 incremental in-memory graph는 raw event IDs를 중복 보관하지 않으며, raw evidence는 materialized graph와 분리된 상태로 유지됩니다. 이 benchmark는 graph accumulation과 snapshot materialization을 측정하며 end-to-end collector 또는 browser throughput을 의미하지 않습니다.",
    ),
}

for name, (old, new) in REPLACEMENTS.items():
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected wording not found in {name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
