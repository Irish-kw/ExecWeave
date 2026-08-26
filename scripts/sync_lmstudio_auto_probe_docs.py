from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

README_STATUS = {
    "README.md": "Yes (automatic after successful `lms server start --port <port>`)",
    "README.zh-TW.md": "是（需明確 `--port`，成功啟動後自動 probe）",
    "README.zh-CN.md": "是（需明确 `--port`，成功启动后自动 probe）",
    "README.ja.md": "Yes（明示した `--port` で起動成功後に自動 probe）",
    "README.ko.md": "Yes (명시적 `--port`로 시작 성공 후 자동 probe)",
    "README.fr.md": "Oui (probe auto après démarrage réussi avec `--port`)",
    "README.de.md": "Ja (automatischer Probe nach erfolgreichem Start mit `--port`)",
    "README.ru.md": "Да (автоматический probe после успешного запуска с `--port`)",
}

MODEL_RUNTIME_PARAGRAPH = {
    "docs/model-runtime.md": (
        "For automatic Live Viewer ingestion, launch LM Studio through ExecWeave with an explicit "
        "local port, for example `execweave live --open -- lms server start --port 1234`. ExecWeave "
        "checks that the endpoint was not already serving a compatible API before launch, and only "
        "probes `/v1/models` after the launcher exits successfully. The resulting relation remains "
        "`ADVERTISES_MODEL`; a catalog entry is never upgraded to `LOADED_MODEL`."
    ),
    "docs/model-runtime.zh-TW.md": (
        "若要讓 LM Studio 自動進入 Live Viewer，請由 ExecWeave 以明確的本機 port 啟動，例如 "
        "`execweave live --open -- lms server start --port 1234`。ExecWeave 會先確認 launch 前該 endpoint "
        "尚未提供相容 API，且只有 launcher 成功結束後才 probe `/v1/models`。產生的 relation 仍是 "
        "`ADVERTISES_MODEL`；catalog entry 不會被提升成 `LOADED_MODEL`。"
    ),
    "docs/model-runtime.zh-CN.md": (
        "若要让 LM Studio 自动进入 Live Viewer，请由 ExecWeave 使用明确的本地 port 启动，例如 "
        "`execweave live --open -- lms server start --port 1234`。ExecWeave 会先确认 launch 前该 endpoint "
        "尚未提供兼容 API，并且只有 launcher 成功结束后才 probe `/v1/models`。生成的 relation 仍为 "
        "`ADVERTISES_MODEL`；catalog entry 不会被提升为 `LOADED_MODEL`。"
    ),
    "docs/model-runtime.ja.md": (
        "LM Studio を Live Viewer に自動取り込みするには、明示的なローカル port を指定して ExecWeave "
        "配下で起動します。例: `execweave live --open -- lms server start --port 1234`。ExecWeave は起動前に "
        "その endpoint で互換 API が既に動作していないことを確認し、launcher が成功終了した場合にだけ "
        "`/v1/models` を probe します。relation は `ADVERTISES_MODEL` のままで、catalog entry を "
        "`LOADED_MODEL` に昇格させません。"
    ),
    "docs/model-runtime.ko.md": (
        "LM Studio를 Live Viewer에 자동으로 넣으려면 명시적인 로컬 port로 ExecWeave 아래에서 실행합니다. "
        "예: `execweave live --open -- lms server start --port 1234`. ExecWeave는 launch 전에 해당 endpoint에 "
        "호환 API가 이미 존재하지 않는지 확인하고 launcher가 성공한 경우에만 `/v1/models`를 probe합니다. "
        "relation은 `ADVERTISES_MODEL`로 유지되며 catalog entry를 `LOADED_MODEL`로 승격하지 않습니다."
    ),
    "docs/model-runtime.fr.md": (
        "Pour l’ingestion automatique dans Live Viewer, lancez LM Studio sous ExecWeave avec un port local "
        "explicite, par exemple `execweave live --open -- lms server start --port 1234`. ExecWeave vérifie "
        "qu’aucune API compatible n’était déjà présente sur cet endpoint avant le lancement, puis ne probe "
        "`/v1/models` qu’après un démarrage réussi. La relation reste `ADVERTISES_MODEL` et n’est jamais "
        "promue en `LOADED_MODEL`."
    ),
    "docs/model-runtime.de.md": (
        "Für die automatische Aufnahme in den Live Viewer starten Sie LM Studio unter ExecWeave mit einem "
        "expliziten lokalen Port, z. B. `execweave live --open -- lms server start --port 1234`. ExecWeave "
        "prüft vor dem Start, dass an diesem Endpoint noch keine kompatible API läuft, und probt `/v1/models` "
        "erst nach einem erfolgreichen Launcher-Exit. Die Relation bleibt `ADVERTISES_MODEL` und wird nicht zu "
        "`LOADED_MODEL` hochgestuft."
    ),
    "docs/model-runtime.ru.md": (
        "Для автоматического попадания LM Studio в Live Viewer запускайте его под ExecWeave с явно указанным "
        "локальным port, например `execweave live --open -- lms server start --port 1234`. Перед launch ExecWeave "
        "проверяет, что на endpoint ещё нет совместимого API, и probe `/v1/models` выполняется только после "
        "успешного завершения launcher. Relation остаётся `ADVERTISES_MODEL` и не повышается до `LOADED_MODEL`."
    ),
}

MARKER = "<!-- lmstudio-auto-live-v064 -->"


def update_readme(path: Path, status: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    for index, line in enumerate(lines):
        if not line.startswith("| LM Studio |"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            raise RuntimeError(f"{path}: malformed LM Studio capability row")
        cells[3] = status
        lines[index] = "| " + " | ".join(cells) + " |"
        found = True
        break
    if not found:
        raise RuntimeError(f"{path}: LM Studio capability row not found")

    text = "\n".join(lines) + "\n"
    if path.name == "README.md":
        old = (
            "Ollama, llama.cpp, and vLLM rows marked **Yes** use automatic loopback model-catalog probes "
            "only when ExecWeave launches the corresponding local server. LM Studio and inference-gateway "
            "rows remain **No** until their specialized metadata can be observed automatically without "
            "inventing evidence."
        )
        new = (
            "Ollama, llama.cpp, and vLLM rows marked **Yes** use automatic loopback model-catalog probes "
            "only when ExecWeave launches the corresponding local server. LM Studio is also automatic for "
            "`lms server start` when an explicit `--port` is supplied, the compatible endpoint was absent "
            "before launch, and the launcher exits successfully. Inference-gateway rows remain **No** until "
            "their specialized routing metadata can be observed automatically without inventing evidence."
        )
        if old not in text:
            raise RuntimeError("README.md: capability note anchor not found")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def update_model_runtime_doc(path: Path, paragraph: str) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return
    heading = "## LM Studio\n"
    if heading not in text:
        raise RuntimeError(f"{path}: LM Studio heading not found")
    insertion = f"{heading}\n{MARKER}\n{paragraph}\n"
    path.write_text(text.replace(heading, insertion, 1), encoding="utf-8")


def main() -> int:
    for filename, status in README_STATUS.items():
        update_readme(ROOT / filename, status)
    for filename, paragraph in MODEL_RUNTIME_PARAGRAPH.items():
        update_model_runtime_doc(ROOT / filename, paragraph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
