from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_FILES = (
    "README.md",
    "README.zh-TW.md",
    "README.zh-CN.md",
    "README.ja.md",
    "README.ko.md",
    "README.fr.md",
    "README.de.md",
    "README.ru.md",
)

LANG = {
    "README.md": {
        "yes_agent": "Yes (configured hook/plugin)",
        "yes_runtime": "Yes (automatic local probe)",
        "intro": (
            "`execweave live` streams process, file, and network evidence for the command tree "
            "it launches. In v0.6.4, configured Claude/Codex/Gemini/Cursor hooks and the "
            "OpenCode plugin automatically feed the per-run live sidecar. Ollama, llama.cpp, "
            "and vLLM server launches also receive automatic local model-catalog probes."
        ),
    },
    "README.zh-TW.md": {
        "yes_agent": "是（已設定 hook/plugin）",
        "yes_runtime": "是（自動本機 probe）",
        "intro": (
            "`execweave live` 即時呈現所啟動 command tree 的 process、file、network evidence。"
            "從 v0.6.4 起，已設定的 Claude/Codex/Gemini/Cursor hooks 與 OpenCode plugin "
            "會自動寫入本次 run 的 live sidecar；由 ExecWeave 啟動的 Ollama、llama.cpp、"
            "vLLM server 也會自動進行本機 model-catalog probe。"
        ),
        "section": """<!-- v0.6.4-live -->
### v0.6.4 即時可觀測性

`top` 會讓 Agent 保持在原本 Terminal 內互動，並在另一個 Terminal 視窗開啟 dashboard：

```bash
execweave top -- codex
execweave top --open -- codex
```

Live 更新採用增量 snapshot/delta 與有界歷史，Live 與 standalone Viewer 支援持久化 Dark/Light theme。Linux 的大型 recursive filesystem scope 會先做資源預檢，必要時由 inotify 自動降級為 polling。

v0.6.4 為每個 live run 建立共享 specialized-evidence sidecar。已設定的 Claude/Codex/Gemini/Cursor hooks 與 OpenCode plugin 會自動進入同一張 Live Graph；由 ExecWeave 啟動的 Ollama、llama.cpp、vLLM server 會自動以 loopback API probe model catalog。這些 live specialized events 是 provisional；command 結束後仍以 canonical runtime + semantic merge 重建 final graph。缺少的 evidence 不會被推測或補造。

可用 `execweave-scalability` 重現 graph scalability benchmark；CI 覆蓋 10k、100k 與 1M synthetic events。
""",
    },
    "README.zh-CN.md": {
        "yes_agent": "是（已配置 hook/plugin）",
        "yes_runtime": "是（自动本地 probe）",
        "intro": (
            "`execweave live` 实时呈现所启动 command tree 的 process、file、network evidence。"
            "从 v0.6.4 起，已配置的 Claude/Codex/Gemini/Cursor hooks 与 OpenCode plugin "
            "会自动写入本次 run 的 live sidecar；由 ExecWeave 启动的 Ollama、llama.cpp、"
            "vLLM server 也会自动执行本地 model-catalog probe。"
        ),
        "section": """<!-- v0.6.4-live -->
### v0.6.4 实时可观测性

`top` 会让 Agent 保持在原 Terminal 内交互，并在另一个 Terminal 窗口打开 dashboard：

```bash
execweave top -- codex
execweave top --open -- codex
```

Live 更新使用增量 snapshot/delta 与有界历史，Live 和 standalone Viewer 支持持久化 Dark/Light theme。Linux 的大型 recursive filesystem scope 会先进行资源预检，必要时从 inotify 自动降级为 polling。

v0.6.4 为每个 live run 建立共享 specialized-evidence sidecar。已配置的 Claude/Codex/Gemini/Cursor hooks 与 OpenCode plugin 会自动进入同一张 Live Graph；由 ExecWeave 启动的 Ollama、llama.cpp、vLLM server 会自动通过 loopback API probe model catalog。这些 live specialized events 是 provisional；command 结束后仍通过 canonical runtime + semantic merge 重建 final graph。缺失的 evidence 不会被推测或补造。

可用 `execweave-scalability` 重现 graph scalability benchmark；CI 覆盖 10k、100k 和 1M synthetic events。
""",
    },
    "README.ja.md": {
        "yes_agent": "Yes（設定済み hook/plugin）",
        "yes_runtime": "Yes（自動ローカル probe）",
        "intro": (
            "`execweave live` は起動した command tree の process/file/network evidence を"
            "リアルタイム表示します。v0.6.4 では設定済み Claude/Codex/Gemini/Cursor hooks "
            "と OpenCode plugin が run 固有の live sidecar へ自動送信され、ExecWeave 配下で"
            "起動した Ollama、llama.cpp、vLLM server にはローカル model-catalog probe が"
            "自動実行されます。"
        ),
        "section": """<!-- v0.6.4-live -->
### v0.6.4 ライブ可観測性

`top` は Agent を元の Terminal で対話可能なままにし、dashboard を別の Terminal ウィンドウで開きます：

```bash
execweave top -- codex
execweave top --open -- codex
```

Live 更新は増分 snapshot/delta と有界履歴を使用し、Live/standalone Viewer は永続的な Dark/Light theme をサポートします。Linux の大規模 recursive filesystem scope は事前確認され、必要なら inotify から polling へ自動フォールバックします。

v0.6.4 では各 live run に共有 specialized-evidence sidecar があります。設定済み Claude/Codex/Gemini/Cursor hooks と OpenCode plugin は同じ Live Graph に自動反映され、ExecWeave 配下で起動した Ollama、llama.cpp、vLLM server は loopback API から model catalog を自動 probe します。live specialized events は provisional であり、command 終了後は canonical runtime + semantic merge から final graph を再構築します。存在しない evidence は推測しません。

`execweave-scalability` で graph scalability benchmark を再現でき、CI は 10k、100k、1M synthetic events を検証します。
""",
    },
    "README.ko.md": {
        "yes_agent": "Yes (설정된 hook/plugin)",
        "yes_runtime": "Yes (자동 로컬 probe)",
        "intro": (
            "`execweave live`는 실행한 command tree의 process/file/network evidence를 실시간으로 "
            "표시합니다. v0.6.4부터 설정된 Claude/Codex/Gemini/Cursor hooks와 OpenCode plugin은 "
            "run 전용 live sidecar로 자동 전송되며, ExecWeave 아래에서 실행한 Ollama, llama.cpp, "
            "vLLM server에는 로컬 model-catalog probe가 자동 적용됩니다."
        ),
        "section": """<!-- v0.6.4-live -->
### v0.6.4 라이브 관측성

`top`은 Agent를 기존 Terminal에서 계속 대화형으로 유지하고 dashboard를 별도 Terminal 창에서 엽니다:

```bash
execweave top -- codex
execweave top --open -- codex
```

Live 업데이트는 증분 snapshot/delta와 제한된 이력을 사용하며 Live/standalone Viewer는 지속되는 Dark/Light theme를 지원합니다. Linux의 매우 큰 recursive filesystem scope는 사전 점검 후 필요하면 inotify에서 polling으로 자동 전환됩니다.

v0.6.4에서는 각 live run에 공유 specialized-evidence sidecar가 생성됩니다. 설정된 Claude/Codex/Gemini/Cursor hooks와 OpenCode plugin은 같은 Live Graph로 자동 유입되고, ExecWeave 아래에서 실행한 Ollama, llama.cpp, vLLM server는 loopback API로 model catalog를 자동 probe합니다. live specialized events는 provisional이며 command 종료 후 canonical runtime + semantic merge에서 final graph를 다시 만듭니다. 관찰되지 않은 evidence는 추측하지 않습니다.

`execweave-scalability`로 graph scalability benchmark를 재현할 수 있으며 CI는 10k, 100k, 1M synthetic events를 검증합니다.
""",
    },
    "README.fr.md": {
        "yes_agent": "Oui (hook/plugin configuré)",
        "yes_runtime": "Oui (probe local automatique)",
        "intro": (
            "`execweave live` diffuse les preuves process, file et network de l’arbre de commandes "
            "qu’il lance. Depuis v0.6.4, les hooks Claude/Codex/Gemini/Cursor configurés et le plugin "
            "OpenCode alimentent automatiquement le live sidecar du run ; les serveurs Ollama, "
            "llama.cpp et vLLM lancés sous ExecWeave reçoivent aussi un probe local automatique "
            "du catalogue de modèles."
        ),
        "section": """<!-- v0.6.4-live -->
### Observabilité Live v0.6.4

`top` garde l’Agent interactif dans le Terminal d’origine et ouvre le dashboard dans une fenêtre Terminal séparée :

```bash
execweave top -- codex
execweave top --open -- codex
```

Les mises à jour Live utilisent des snapshots/deltas incrémentaux avec un historique borné. Les Viewers Live et standalone conservent le choix Dark/Light. Sous Linux, les très grands scopes filesystem récursifs sont pré-évalués et basculent automatiquement d’inotify vers le polling si nécessaire.

v0.6.4 crée un specialized-evidence sidecar partagé pour chaque run live. Les hooks Claude/Codex/Gemini/Cursor configurés et le plugin OpenCode arrivent automatiquement dans le même Live Graph ; les serveurs Ollama, llama.cpp et vLLM lancés sous ExecWeave sont interrogés automatiquement via leur API loopback pour le catalogue de modèles. Ces événements spécialisés live sont provisoires ; après la fin de la commande, le graphe final est reconstruit depuis le merge canonical runtime + semantic. Aucune preuve absente n’est inventée.

Lancez `execweave-scalability` pour reproduire le benchmark de scalabilité ; la CI couvre 10k, 100k et 1M événements synthétiques.
""",
    },
    "README.de.md": {
        "yes_agent": "Ja (konfigurierter Hook/Plugin)",
        "yes_runtime": "Ja (automatischer lokaler Probe)",
        "intro": (
            "`execweave live` streamt Process-, File- und Network-Evidence für den gestarteten "
            "Command Tree. Seit v0.6.4 speisen konfigurierte Claude/Codex/Gemini/Cursor-Hooks und "
            "das OpenCode-Plugin automatisch den run-spezifischen Live-Sidecar; unter ExecWeave "
            "gestartete Ollama-, llama.cpp- und vLLM-Server erhalten zusätzlich einen automatischen "
            "lokalen Model-Catalog-Probe."
        ),
        "section": """<!-- v0.6.4-live -->
### v0.6.4 Live-Observability

`top` lässt den Agent im ursprünglichen Terminal interaktiv und öffnet das Dashboard in einem separaten Terminalfenster:

```bash
execweave top -- codex
execweave top --open -- codex
```

Live-Updates verwenden inkrementelle Snapshots/Deltas mit begrenzter History. Live- und Standalone-Viewer behalten die Dark/Light-Auswahl. Unter Linux werden sehr große rekursive Filesystem-Scopes vorab geprüft und bei Bedarf automatisch von inotify auf Polling zurückgestuft.

v0.6.4 erstellt für jeden Live-Run einen gemeinsamen Specialized-Evidence-Sidecar. Konfigurierte Claude/Codex/Gemini/Cursor-Hooks und das OpenCode-Plugin erscheinen automatisch im selben Live Graph; unter ExecWeave gestartete Ollama-, llama.cpp- und vLLM-Server werden automatisch über ihre Loopback-API nach dem Model Catalog abgefragt. Diese spezialisierten Live-Events sind provisional; nach Ende des Befehls wird der finale Graph aus dem canonical Runtime+Semantic-Merge neu aufgebaut. Fehlende Evidence wird nicht erfunden.

Mit `execweave-scalability` lässt sich der Graph-Scalability-Benchmark reproduzieren; CI deckt 10k, 100k und 1M synthetische Events ab.
""",
    },
    "README.ru.md": {
        "yes_agent": "Да (настроенный hook/plugin)",
        "yes_runtime": "Да (автоматический локальный probe)",
        "intro": (
            "`execweave live` передаёт process-, file- и network-evidence для запущенного command tree. "
            "Начиная с v0.6.4, настроенные Claude/Codex/Gemini/Cursor hooks и OpenCode plugin "
            "автоматически пишут в live sidecar текущего run; для Ollama, llama.cpp и vLLM server, "
            "запущенных под ExecWeave, также выполняется автоматический локальный probe каталога моделей."
        ),
        "section": """<!-- v0.6.4-live -->
### Live-наблюдаемость v0.6.4

`top` оставляет Agent интерактивным в исходном Terminal и открывает dashboard в отдельном окне Terminal:

```bash
execweave top -- codex
execweave top --open -- codex
```

Live-обновления используют инкрементальные snapshots/deltas с ограниченной историей. Live и standalone Viewer сохраняют выбор Dark/Light. В Linux очень большие recursive filesystem scopes проходят предварительную проверку и при необходимости автоматически переключаются с inotify на polling.

v0.6.4 создаёт общий specialized-evidence sidecar для каждого live run. Настроенные Claude/Codex/Gemini/Cursor hooks и OpenCode plugin автоматически попадают в тот же Live Graph; Ollama, llama.cpp и vLLM server, запущенные под ExecWeave, автоматически опрашиваются через loopback API для получения model catalog. Эти specialized live events являются provisional; после завершения команды финальный graph заново строится из canonical runtime + semantic merge. Отсутствующие evidence не выдумываются.

`execweave-scalability` воспроизводит benchmark масштабируемости graph; CI покрывает 10k, 100k и 1M synthetic events.
""",
    },
}

AGENTS = {"Claude Code", "OpenAI Codex", "Gemini CLI", "Cursor", "OpenCode"}
AUTO_RUNTIMES = {"Ollama", "llama.cpp", "vLLM"}


def _replace_intro(text: str, intro: str) -> str:
    table = text.find("\n#### ", text.find("execweave live --open -- ollama serve"))
    if table < 0:
        raise RuntimeError("Live capability heading not found")
    fence = text.rfind("\n```", 0, table)
    if fence < 0:
        raise RuntimeError("Live example closing fence not found")
    after_fence = fence + len("\n```")
    return text[:after_fence] + "\n\n" + intro + "\n" + text[table:]


def _replace_matrix(text: str, yes_agent: str, yes_runtime: str) -> str:
    lines = text.splitlines()
    in_table = False
    seen = set()
    for index, line in enumerate(lines):
        if line.startswith("| Integration |") and "Live Viewer" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        cells = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        integration = cells[0]
        if integration in AGENTS:
            cells[-1] = yes_agent
            seen.add(integration)
        elif integration in AUTO_RUNTIMES:
            cells[-1] = yes_runtime
            seen.add(integration)
        else:
            continue
        lines[index] = "| " + " | ".join(cells) + " |"
    expected = AGENTS | AUTO_RUNTIMES
    if seen != expected:
        raise RuntimeError(f"missing matrix rows: {sorted(expected - seen)}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _replace_live_section(text: str, section: str) -> str:
    markers = ("<!-- v0.6.4-live -->", "<!-- v0.6.3-live -->")
    starts = [text.find(marker) for marker in markers if text.find(marker) >= 0]
    if not starts:
        raise RuntimeError("live version marker not found")
    start = min(starts)
    scale = text.find("#### Scalability", start)
    if scale < 0:
        raise RuntimeError("Scalability heading not found")
    return text[:start] + section.rstrip() + "\n\n" + text[scale:]


def _update_current_status(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "`main`" in line and "v0.6.3" in line:
            lines[index] = line.replace("v0.6.3", "v0.6.4")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def update_file(path: Path) -> None:
    config = LANG[path.name]
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "docs/assets/execweave-live-demo.png",
        "docs/assets/execweave-launch-demo-v5-x.gif",
    )
    text = _replace_intro(text, config["intro"])
    text = _replace_matrix(text, config["yes_agent"], config["yes_runtime"])
    section = config.get("section")
    if section is not None:
        text = _replace_live_section(text, section)
    text = _update_current_status(text)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    for filename in README_FILES:
        update_file(ROOT / filename)
        print(filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
