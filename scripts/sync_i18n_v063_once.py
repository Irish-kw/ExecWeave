from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATA = {
    "README.de.md": {
        "start": "Claude Code, OpenAI Codex oder Gemini CLI live beobachten:",
        "end": "## Leistung und Footprint",
        "block": r'''Live-OS-Runtime-Telemetrie funktioniert mit **jedem lokalen Befehl**. Die folgenden Namen sind Beispiele, keine Whitelist:

```bash
# Agent / IDE CLIs
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- cursor
execweave live --open -- opencode

# Any local program
execweave live --open -- python my_agent.py

# A local model runtime launched under ExecWeave
execweave live --open -- ollama serve
```

`execweave live` streamt Process-, File- und Network-Evidence für den von ExecWeave gestarteten Command Tree. Agent-Semantic-Hooks, Model-Runtime-API-Metadaten oder Inference-Gateway-Routing-Metadaten werden **nicht** automatisch in den Live Viewer injiziert.

#### Live-Capability-Matrix

| Integration | Direct OS-runtime live | Specialized metadata | Automatisch im Live Viewer |
| --- | --- | --- | --- |
| Claude Code | Ja | `execweave-claude-record` / hooks | Nein |
| OpenAI Codex | Ja | `execweave-codex-record` / hooks | Nein |
| Gemini CLI | Ja | `execweave-gemini-record` / hooks | Nein |
| Cursor | Ja | `execweave-cursor-record` / hooks | Nein |
| OpenCode | Ja | `execweave-opencode-record` / plugin | Nein |
| Ollama | Ja, wenn es unter ExecWeave gestartet wird, z. B. `ollama serve` | `execweave-model-runtime event/probe --runtime ollama` | Nein |
| llama.cpp | Ja, wenn der lokale Server unter ExecWeave gestartet wird | `execweave-model-runtime event/probe --runtime llamacpp` | Nein |
| vLLM | Ja, wenn der lokale Server unter ExecWeave gestartet wird | `execweave-model-runtime event/probe --runtime vllm` | Nein |
| LM Studio | Nur für einen lokalen Prozess, der unter ExecWeave gestartet wurde; ein bereits laufender Server wird nicht attached | `execweave-model-runtime event/probe --runtime lmstudio` | Nein |
| LiteLLM Proxy | Ja, wenn der lokale Proxy unter ExecWeave gestartet wird | `execweave-inference-gateway event --gateway litellm` | Nein |
| OpenRouter | Kein direkt startbarer Remote-Service-Prozess; stattdessen den lokalen Client/Agent unter `live` ausführen | `execweave-inference-gateway event/generation --gateway openrouter` | Nein |

Für einen bereits laufenden Ollama-Server kann `execweave-model-runtime probe --runtime ollama` den geladenen Modellzustand snapshotten. Bei OpenRouter kann `live` den lokalen Client und dessen Network-Aktivität beobachten; Gateway-Routing-/Usage-Metadaten bleiben eine separate Evidence-Layer.

<!-- v0.6.3-live -->
### v0.6.3 Live-Observability

Dieselbe Live-Session kann im Browser oder Terminal betrachtet werden:

```bash
execweave top -- codex          # Terminal dashboard
execweave top --open -- codex   # Terminal + Web Viewer
```

Live-Updates verwenden inkrementelle Snapshots/Deltas mit begrenzter History, statt den vollständigen Graph wiederholt neu zu bauen und zu übertragen. Live- und Standalone-Viewer unterstützen einen persistenten Dark/Light-Theme-Schalter. Unter Linux werden sehr große rekursive Filesystem-Scopes vorab geprüft und bei Bedarf automatisch von inotify auf Polling zurückgestuft, sodass ein erschöpfter inotify-Watch-Pool die Session nicht abbricht.

`live` ist eine generische OS-Runtime-Ansicht und keine Integrations-Whitelist. Spezialisierte Agent-Semantic-, Model-Runtime- und Gateway-Metadaten bleiben getrennte Evidence-Layer und werden in v0.6.3 nicht automatisch in den Live Viewer injiziert.

Der reproduzierbare Graph-Scalability-Benchmark läuft mit `execweave-scalability`; CI deckt 10k, 100k und 1M synthetische Events ab.

#### Scalability-Benchmark

Referenzergebnis aus GitHub Actions für den inkrementellen `GraphAccumulator`-Synthetic-Workload (`retain_event_ids=False`):

| Events | Apply time | Throughput | Nodes | Edges | Apply RSS Δ | Snapshot |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10k | 0.114 s | 87,681 ev/s | 10,001 | 10,000 | 35.9 MiB | 8.5 MiB |
| 100k | 0.654 s | 152,816 ev/s | 10,001 | 10,000 | 25.8 MiB | 8.6 MiB |
| **1M** | **6.087 s** | **164,273 ev/s** | **10,001** | **10,000** | **23.5 MiB** | **8.6 MiB** |

Bei **1.000.000 Events** duplizierte der inkrementelle In-Memory-Graph keine Raw Event IDs; Raw Evidence bleibt vom materialized graph getrennt. Dieser Benchmark misst Graph-Akkumulation und Snapshot-Materialisierung, nicht den End-to-End-Durchsatz des Collectors oder Browsers.

Oder die vollständige Artifact-Pipeline erzeugen:

```bash
execweave record --open -- python my_agent.py
```
''',
    },
    "README.fr.md": {
        "start": "Observez Claude Code, OpenAI Codex ou Gemini CLI en direct :",
        "end": "## Performances et empreinte",
        "block": r'''La télémétrie OS-runtime Live fonctionne avec **n’importe quelle commande locale**. Les noms ci-dessous sont des exemples, pas une whitelist :

```bash
# Agent / IDE CLIs
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- cursor
execweave live --open -- opencode

# Any local program
execweave live --open -- python my_agent.py

# A local model runtime launched under ExecWeave
execweave live --open -- ollama serve
```

`execweave live` diffuse les preuves process, file et network de l’arbre de commandes qu’il lance. Il **n’injecte pas automatiquement** dans le Live Viewer les hooks sémantiques Agent, les métadonnées API du Model Runtime ni les métadonnées de routage de l’Inference Gateway.

#### Matrice des capacités Live

| Integration | Direct OS-runtime live | Specialized metadata | Automatiquement dans le Live Viewer |
| --- | --- | --- | --- |
| Claude Code | Oui | `execweave-claude-record` / hooks | Non |
| OpenAI Codex | Oui | `execweave-codex-record` / hooks | Non |
| Gemini CLI | Oui | `execweave-gemini-record` / hooks | Non |
| Cursor | Oui | `execweave-cursor-record` / hooks | Non |
| OpenCode | Oui | `execweave-opencode-record` / plugin | Non |
| Ollama | Oui, lorsqu’il est lancé sous ExecWeave, par exemple `ollama serve` | `execweave-model-runtime event/probe --runtime ollama` | Non |
| llama.cpp | Oui, lorsque son serveur local est lancé sous ExecWeave | `execweave-model-runtime event/probe --runtime llamacpp` | Non |
| vLLM | Oui, lorsque son serveur local est lancé sous ExecWeave | `execweave-model-runtime event/probe --runtime vllm` | Non |
| LM Studio | Oui uniquement pour un processus local lancé sous ExecWeave ; un serveur déjà actif n’est pas attaché | `execweave-model-runtime event/probe --runtime lmstudio` | Non |
| LiteLLM Proxy | Oui, lorsque le proxy local est lancé sous ExecWeave | `execweave-inference-gateway event --gateway litellm` | Non |
| OpenRouter | Pas de processus de service distant à lancer directement ; exécutez plutôt le client/Agent local sous `live` | `execweave-inference-gateway event/generation --gateway openrouter` | Non |

Pour un serveur Ollama déjà actif, utilisez `execweave-model-runtime probe --runtime ollama` afin de prendre un snapshot de l’état des modèles chargés. Pour OpenRouter, `live` peut observer le client local et son activité réseau, tandis que les métadonnées de routage/usage du gateway restent une couche de preuve distincte.

<!-- v0.6.3-live -->
### Observabilité Live v0.6.3

Utilisez la même session Live dans le navigateur ou le terminal :

```bash
execweave top -- codex          # Terminal dashboard
execweave top --open -- codex   # Terminal + Web Viewer
```

Les mises à jour Live utilisent des snapshots/deltas incrémentaux avec un historique borné au lieu de reconstruire et retransférer continuellement le graphe complet. Les Viewers Live et standalone proposent un sélecteur Dark/Light persistant. Sous Linux, les très grands scopes filesystem récursifs sont pré-évalués et basculent automatiquement d’inotify vers le polling si nécessaire, afin qu’un pool de watches inotify épuisé n’interrompe pas la session.

`live` est une vue OS-runtime générique et non une whitelist d’intégrations. Les métadonnées spécialisées Agent semantic, Model Runtime et Gateway restent des couches de preuve séparées et ne sont pas automatiquement injectées dans le Live Viewer en v0.6.3.

Lancez le benchmark reproductible de scalabilité du graphe avec `execweave-scalability` ; la CI couvre 10k, 100k et 1M événements synthétiques.

#### Benchmark de scalabilité

Résultat GitHub Actions de référence pour le workload synthétique du `GraphAccumulator` incrémental (`retain_event_ids=False`) :

| Events | Apply time | Throughput | Nodes | Edges | Apply RSS Δ | Snapshot |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10k | 0.114 s | 87,681 ev/s | 10,001 | 10,000 | 35.9 MiB | 8.5 MiB |
| 100k | 0.654 s | 152,816 ev/s | 10,001 | 10,000 | 25.8 MiB | 8.6 MiB |
| **1M** | **6.087 s** | **164,273 ev/s** | **10,001** | **10,000** | **23.5 MiB** | **8.6 MiB** |

À **1 000 000 d’événements**, le graphe incrémental en mémoire ne duplique aucun raw event ID ; les raw evidence restent séparées du materialized graph. Ce benchmark mesure l’accumulation du graphe et la matérialisation des snapshots, et non le débit end-to-end du collector ou du navigateur.

Ou construisez la chaîne complète d’artefacts :

```bash
execweave record --open -- python my_agent.py
```
''',
    },
    "README.ru.md": {
        "start": "Наблюдайте за Claude Code, OpenAI Codex или Gemini CLI в реальном времени:",
        "end": "## Производительность и footprint",
        "block": r'''Live-телеметрия уровня OS runtime работает с **любой локальной командой**. Имена ниже — примеры, а не whitelist:

```bash
# Agent / IDE CLIs
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- cursor
execweave live --open -- opencode

# Any local program
execweave live --open -- python my_agent.py

# A local model runtime launched under ExecWeave
execweave live --open -- ollama serve
```

`execweave live` в реальном времени передаёт process-, file- и network-evidence для дерева команд, которое запускает ExecWeave. Он **не добавляет автоматически** в Live Viewer semantic hooks агента, API-метаданные Model Runtime или routing metadata Inference Gateway.

#### Матрица возможностей Live

| Integration | Direct OS-runtime live | Specialized metadata | Автоматически в Live Viewer |
| --- | --- | --- | --- |
| Claude Code | Да | `execweave-claude-record` / hooks | Нет |
| OpenAI Codex | Да | `execweave-codex-record` / hooks | Нет |
| Gemini CLI | Да | `execweave-gemini-record` / hooks | Нет |
| Cursor | Да | `execweave-cursor-record` / hooks | Нет |
| OpenCode | Да | `execweave-opencode-record` / plugin | Нет |
| Ollama | Да, если запущен под ExecWeave, например `ollama serve` | `execweave-model-runtime event/probe --runtime ollama` | Нет |
| llama.cpp | Да, если локальный сервер запущен под ExecWeave | `execweave-model-runtime event/probe --runtime llamacpp` | Нет |
| vLLM | Да, если локальный сервер запущен под ExecWeave | `execweave-model-runtime event/probe --runtime vllm` | Нет |
| LM Studio | Только для локального процесса, запущенного под ExecWeave; уже работающий сервер автоматически не attached | `execweave-model-runtime event/probe --runtime lmstudio` | Нет |
| LiteLLM Proxy | Да, если локальный proxy запущен под ExecWeave | `execweave-inference-gateway event --gateway litellm` | Нет |
| OpenRouter | Нет локального процесса удалённого сервиса для прямого запуска; вместо этого запускайте локальный client/Agent под `live` | `execweave-inference-gateway event/generation --gateway openrouter` | Нет |

Для уже работающего сервера Ollama используйте `execweave-model-runtime probe --runtime ollama`, чтобы получить snapshot состояния загруженных моделей. Для OpenRouter `live` может наблюдать локальный client и его network activity, а gateway routing/usage metadata остаются отдельным evidence layer.

<!-- v0.6.3-live -->
### Live observability v0.6.3

Одну и ту же Live-сессию можно смотреть в браузере или терминале:

```bash
execweave top -- codex          # Terminal dashboard
execweave top --open -- codex   # Terminal + Web Viewer
```

Live-обновления используют инкрементальные snapshots/deltas с ограниченной history вместо постоянной полной перестройки и передачи всего графа. Live и standalone Viewers поддерживают сохраняемый переключатель Dark/Light. В Linux очень большие рекурсивные filesystem scopes проходят preflight-проверку и при необходимости автоматически переходят с inotify на polling, поэтому исчерпание пула inotify watches не прерывает сессию.

`live` — это универсальная OS-runtime view, а не whitelist интеграций. Специализированные Agent semantic, Model Runtime и Gateway metadata остаются отдельными evidence layers и в v0.6.3 автоматически в Live Viewer не добавляются.

Воспроизводимый benchmark масштабируемости графа запускается через `execweave-scalability`; CI покрывает 10k, 100k и 1M синтетических событий.

#### Benchmark масштабируемости

Референсный результат GitHub Actions для синтетического workload инкрементального `GraphAccumulator` (`retain_event_ids=False`):

| Events | Apply time | Throughput | Nodes | Edges | Apply RSS Δ | Snapshot |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10k | 0.114 s | 87,681 ev/s | 10,001 | 10,000 | 35.9 MiB | 8.5 MiB |
| 100k | 0.654 s | 152,816 ev/s | 10,001 | 10,000 | 25.8 MiB | 8.6 MiB |
| **1M** | **6.087 s** | **164,273 ev/s** | **10,001** | **10,000** | **23.5 MiB** | **8.6 MiB** |

При **1 000 000 событий** инкрементальный in-memory graph не дублировал raw event IDs; raw evidence остаётся отделённым от materialized graph. Этот benchmark измеряет накопление графа и материализацию snapshot, а не end-to-end throughput collector или браузера.

Или соберите полный artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```
''',
    },
}


def update_readme(path: Path, cfg: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.find(cfg["start"])
    end = text.find(cfg["end"])
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(f"cannot locate update anchors in {path}")
    text = text[:start] + cfg["block"].rstrip() + "\n\n" + text[end:]
    text = re.sub(
        r"(?m)^(ExecWeave `main`[^\n]*?\*\*)v0\.6\.2(\*\*[^\n]*)$",
        r"\1v0.6.3\2",
        text,
        count=1,
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    for name, cfg in DATA.items():
        update_readme(ROOT / name, cfg)
        print(f"updated: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
