from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- litellm-auto-live-v064 -->"

README_STATUS = {
    "README.md": "Yes (configured callback)",
    "README.zh-TW.md": "是（已設定 callback）",
    "README.zh-CN.md": "是（已配置 callback）",
    "README.ja.md": "Yes（設定済み callback）",
    "README.ko.md": "Yes (설정된 callback)",
    "README.fr.md": "Oui (callback configuré)",
    "README.de.md": "Ja (konfigurierter Callback)",
    "README.ru.md": "Да (настроенный callback)",
}

DOC_SECTION = {
    "docs/inference-gateway.md": r'''
{marker}
### Automatic Live Viewer callback

LiteLLM Proxy can load ExecWeave as a custom callback once and then feed routing/usage metadata into the current `execweave live` sidecar automatically. Print the configuration fragment with:

```bash
execweave-litellm-callback --print-config
```

Merge the printed callback into your existing `litellm_settings.callbacks` configuration instead of replacing other callbacks. The callback import path is `execweave.litellm_callback.execweave_litellm_callback`, so ExecWeave must be importable in the Python environment that runs LiteLLM Proxy.

Then launch the configured local proxy under ExecWeave, for example:

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` provides `EXECWEAVE_SEMANTIC_SIDECAR` to the proxy process. If that run-specific variable is absent, the callback is a no-op. `EXECWEAVE_LITELLM_ENDPOINT` can override the stored proxy endpoint identity; otherwise the callback uses `PROXY_BASE_URL` when present and falls back to `http://localhost:4000`.

The callback reads LiteLLM's `standard_logging_object` only through a strict whitelist: call ID, model group, resolved model, deployment model ID, token counts, reported cost, response time, cache-hit state, and call type. It does not persist messages, response content, model parameters, arbitrary metadata, API-key metadata, or provider `api_base`. `model_group` is preserved as the requested model, `model` as the resolved model, and `model_id` as deployment identity. Provider identity is omitted unless authoritative provider evidence is supplied separately; ExecWeave does not infer it from model names or provider URLs.
''',
    "docs/inference-gateway.zh-TW.md": r'''
{marker}
### 自動進入 Live Viewer 的 callback

LiteLLM Proxy 可先設定一次 ExecWeave custom callback，之後在目前的 `execweave live` session 中自動把 routing/usage metadata 寫入 run-specific sidecar。可先印出設定片段：

```bash
execweave-litellm-callback --print-config
```

請把印出的 callback 合併到既有 `litellm_settings.callbacks`，不要覆蓋原本其他 callbacks。callback import path 為 `execweave.litellm_callback.execweave_litellm_callback`，因此執行 LiteLLM Proxy 的 Python environment 必須可以 import ExecWeave。

接著由 ExecWeave 啟動已設定的本機 proxy，例如：

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` 會把 `EXECWEAVE_SEMANTIC_SIDECAR` 傳給 proxy process；若沒有這個 run-specific environment variable，callback 完全 no-op。可用 `EXECWEAVE_LITELLM_ENDPOINT` 覆寫紀錄中的 proxy endpoint identity；否則優先使用 `PROXY_BASE_URL`，最後才 fallback 到 `http://localhost:4000`。

callback 只會從 LiteLLM `standard_logging_object` 白名單擷取 call ID、model group、resolved model、deployment model ID、token counts、reported cost、response time、cache-hit 與 call type。不會保存 messages、response content、model parameters、任意 metadata、API-key metadata 或 provider `api_base`。`model_group` 保留為 requested model、`model` 保留為 resolved model、`model_id` 保留為 deployment identity；沒有權威 provider evidence 時不建立 provider edge，也不從 model name 或 provider URL 猜測。
''',
    "docs/inference-gateway.zh-CN.md": r'''
{marker}
### 自动进入 Live Viewer 的 callback

LiteLLM Proxy 可先配置一次 ExecWeave custom callback，之后在当前 `execweave live` session 中自动把 routing/usage metadata 写入 run-specific sidecar。可先打印配置片段：

```bash
execweave-litellm-callback --print-config
```

请把打印出的 callback 合并到现有 `litellm_settings.callbacks`，不要覆盖已有的其他 callbacks。callback import path 为 `execweave.litellm_callback.execweave_litellm_callback`，因此运行 LiteLLM Proxy 的 Python environment 必须能够 import ExecWeave。

随后由 ExecWeave 启动已配置的本地 proxy，例如：

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` 会把 `EXECWEAVE_SEMANTIC_SIDECAR` 传给 proxy process；若没有这个 run-specific environment variable，callback 完全 no-op。可用 `EXECWEAVE_LITELLM_ENDPOINT` 覆盖记录中的 proxy endpoint identity；否则优先使用 `PROXY_BASE_URL`，最后 fallback 到 `http://localhost:4000`。

callback 只从 LiteLLM `standard_logging_object` 白名单提取 call ID、model group、resolved model、deployment model ID、token counts、reported cost、response time、cache-hit 与 call type。不会保存 messages、response content、model parameters、任意 metadata、API-key metadata 或 provider `api_base`。`model_group` 作为 requested model、`model` 作为 resolved model、`model_id` 作为 deployment identity；没有权威 provider evidence 时不会建立 provider edge，也不会从 model name 或 provider URL 猜测。
''',
    "docs/inference-gateway.ja.md": r'''
{marker}
### Live Viewer への自動 callback

LiteLLM Proxy に ExecWeave custom callback を一度設定すると、現在の `execweave live` session の run-specific sidecar へ routing/usage metadata を自動送信できます。設定断片は次で表示できます：

```bash
execweave-litellm-callback --print-config
```

表示された callback は既存の `litellm_settings.callbacks` に追加し、他の callbacks を上書きしないでください。import path は `execweave.litellm_callback.execweave_litellm_callback` なので、LiteLLM Proxy を実行する Python environment から ExecWeave を import できる必要があります。

設定後のローカル proxy を ExecWeave 配下で起動します：

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` は `EXECWEAVE_SEMANTIC_SIDECAR` を proxy process に渡します。この run-specific variable が無ければ callback は no-op です。endpoint identity は `EXECWEAVE_LITELLM_ENDPOINT` で上書きでき、未設定なら `PROXY_BASE_URL`、最後に `http://localhost:4000` を使います。

callback は LiteLLM `standard_logging_object` から call ID、model group、resolved model、deployment model ID、token counts、reported cost、response time、cache-hit、call type だけを whitelist で取得します。messages、response content、model parameters、任意 metadata、API-key metadata、provider `api_base` は保存しません。`model_group` は requested model、`model` は resolved model、`model_id` は deployment identity として保持し、権威ある provider evidence が無ければ provider を推測しません。
''',
    "docs/inference-gateway.ko.md": r'''
{marker}
### Live Viewer 자동 callback

LiteLLM Proxy에 ExecWeave custom callback을 한 번 설정하면 현재 `execweave live` session의 run-specific sidecar로 routing/usage metadata를 자동 전송할 수 있습니다. 설정 조각은 다음으로 출력합니다:

```bash
execweave-litellm-callback --print-config
```

출력된 callback을 기존 `litellm_settings.callbacks`에 병합하고 다른 callbacks를 덮어쓰지 마십시오. import path는 `execweave.litellm_callback.execweave_litellm_callback`이므로 LiteLLM Proxy를 실행하는 Python environment에서 ExecWeave를 import할 수 있어야 합니다.

설정된 로컬 proxy를 ExecWeave 아래에서 실행합니다:

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live`는 `EXECWEAVE_SEMANTIC_SIDECAR`를 proxy process에 전달합니다. 이 run-specific variable이 없으면 callback은 no-op입니다. `EXECWEAVE_LITELLM_ENDPOINT`로 endpoint identity를 재정의할 수 있고, 없으면 `PROXY_BASE_URL`, 마지막으로 `http://localhost:4000`을 사용합니다.

callback은 LiteLLM `standard_logging_object`에서 call ID, model group, resolved model, deployment model ID, token counts, reported cost, response time, cache-hit, call type만 whitelist로 추출합니다. messages, response content, model parameters, 임의 metadata, API-key metadata, provider `api_base`는 저장하지 않습니다. `model_group`은 requested model, `model`은 resolved model, `model_id`는 deployment identity로 보존하며 권위 있는 provider evidence가 없으면 provider를 추론하지 않습니다.
''',
    "docs/inference-gateway.fr.md": r'''
{marker}
### Callback automatique dans Live Viewer

LiteLLM Proxy peut charger une fois le custom callback ExecWeave puis envoyer automatiquement les métadonnées de routage/usage vers le sidecar du run `execweave live` courant. Affichez le fragment de configuration avec :

```bash
execweave-litellm-callback --print-config
```

Ajoutez le callback imprimé à `litellm_settings.callbacks` sans remplacer les callbacks existants. Son import path est `execweave.litellm_callback.execweave_litellm_callback`; ExecWeave doit donc être importable dans l’environnement Python qui exécute LiteLLM Proxy.

Lancez ensuite le proxy local configuré sous ExecWeave :

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` transmet `EXECWEAVE_SEMANTIC_SIDECAR` au processus proxy. Sans cette variable propre au run, le callback est un no-op. `EXECWEAVE_LITELLM_ENDPOINT` peut remplacer l’identité de l’endpoint ; sinon le callback utilise `PROXY_BASE_URL`, puis `http://localhost:4000`.

Le callback ne lit dans `standard_logging_object` qu’une liste blanche : call ID, model group, resolved model, deployment model ID, token counts, reported cost, response time, cache-hit et call type. Il ne conserve ni messages, ni contenu de réponse, ni paramètres de modèle, ni metadata arbitraire, ni metadata de clé API, ni `api_base` provider. `model_group` reste le requested model, `model` le resolved model et `model_id` l’identité de deployment ; aucun provider n’est déduit sans preuve autoritative.
''',
    "docs/inference-gateway.de.md": r'''
{marker}
### Automatischer Live-Viewer-Callback

LiteLLM Proxy kann den ExecWeave Custom Callback einmal konfigurieren und danach Routing-/Usage-Metadaten automatisch in den run-spezifischen Sidecar der aktuellen `execweave live`-Session schreiben. Das Konfigurationsfragment erhalten Sie mit:

```bash
execweave-litellm-callback --print-config
```

Fügen Sie den ausgegebenen Callback zu `litellm_settings.callbacks` hinzu, ohne bestehende Callbacks zu überschreiben. Der Import-Pfad lautet `execweave.litellm_callback.execweave_litellm_callback`; ExecWeave muss daher in der Python-Umgebung des LiteLLM Proxy importierbar sein.

Starten Sie den konfigurierten lokalen Proxy unter ExecWeave:

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` vererbt `EXECWEAVE_SEMANTIC_SIDECAR` an den Proxy-Prozess. Fehlt diese run-spezifische Variable, ist der Callback ein no-op. `EXECWEAVE_LITELLM_ENDPOINT` kann die Endpoint-Identität überschreiben; sonst werden `PROXY_BASE_URL` und anschließend `http://localhost:4000` verwendet.

Der Callback liest aus LiteLLM `standard_logging_object` ausschließlich eine Whitelist: Call ID, Model Group, resolved model, Deployment Model ID, Token Counts, reported cost, response time, cache-hit und call type. Messages, Response-Inhalt, Model Parameters, beliebige Metadata, API-Key-Metadata und Provider-`api_base` werden nicht gespeichert. `model_group` bleibt requested model, `model` resolved model und `model_id` Deployment-Identität; ohne autoritative Provider-Evidence wird kein Provider abgeleitet.
''',
    "docs/inference-gateway.ru.md": r'''
{marker}
### Автоматический callback для Live Viewer

LiteLLM Proxy можно один раз настроить на custom callback ExecWeave, после чего routing/usage metadata автоматически попадают в run-specific sidecar текущей сессии `execweave live`. Фрагмент конфигурации выводится командой:

```bash
execweave-litellm-callback --print-config
```

Добавьте выведенный callback в существующий `litellm_settings.callbacks`, не заменяя другие callbacks. Import path: `execweave.litellm_callback.execweave_litellm_callback`, поэтому ExecWeave должен быть доступен для import в Python environment, где работает LiteLLM Proxy.

После настройки запускайте локальный proxy под ExecWeave:

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` передаёт `EXECWEAVE_SEMANTIC_SIDECAR` процессу proxy. Без этой run-specific variable callback работает как no-op. `EXECWEAVE_LITELLM_ENDPOINT` может переопределить endpoint identity; иначе используется `PROXY_BASE_URL`, затем `http://localhost:4000`.

Callback извлекает из LiteLLM `standard_logging_object` только whitelist: call ID, model group, resolved model, deployment model ID, token counts, reported cost, response time, cache-hit и call type. Messages, response content, model parameters, произвольная metadata, API-key metadata и provider `api_base` не сохраняются. `model_group` сохраняется как requested model, `model` как resolved model, `model_id` как deployment identity; provider не выводится без авторитетного provider evidence.
''',
}


def update_readme(path: Path, status: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    for index, line in enumerate(lines):
        if not line.startswith("| LiteLLM Proxy |"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            raise RuntimeError(f"{path}: malformed LiteLLM capability row")
        cells[2] = "`execweave-inference-gateway event --gateway litellm` / configured callback"
        cells[3] = status
        lines[index] = "| " + " | ".join(cells) + " |"
        found = True
        break
    if not found:
        raise RuntimeError(f"{path}: LiteLLM capability row not found")

    text = "\n".join(lines) + "\n"
    if path.name == "README.md":
        old = (
            "Inference-gateway rows remain **No** until their specialized routing metadata can be "
            "observed automatically without inventing evidence."
        )
        new = (
            "LiteLLM Proxy is **Yes** after its ExecWeave callback has been configured once and the "
            "proxy is launched inside the current `execweave live` environment. OpenRouter remains "
            "**No** because remote routing metadata is not available from OS/network observation alone."
        )
        if old not in text:
            raise RuntimeError("README.md: inference-gateway capability note anchor not found")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def update_doc(path: Path, section_template: str) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return
    heading = "## LiteLLM Proxy\n"
    if heading not in text:
        raise RuntimeError(f"{path}: LiteLLM Proxy heading not found")
    section = section_template.format(marker=MARKER).strip() + "\n\n"
    text = text.replace(heading, heading + "\n" + section, 1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    for filename, status in README_STATUS.items():
        update_readme(ROOT / filename, status)
    for filename, section in DOC_SECTION.items():
        update_doc(ROOT / filename, section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
