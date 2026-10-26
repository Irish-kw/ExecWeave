# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a> |
  <a href="model-runtime.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="model-runtime.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Model Runtimes sind von Agent-/IDE-Semantic-Adaptern und Inference Gateways getrennt. Sie beschreiben, was ein lokaler oder selbst gehosteter Inference-Integrationspunkt meldet; sie beweisen nicht, welcher Agent einen Request gestartet hat.

Der aktuelle Baseline unterstützt **Ollama**, **llama.cpp**, **vLLM** und **LM Studio**.

## CLI

Eine gelieferte finale Runtime-Response von stdin erfassen:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Ein vom Aufrufer geliefertes Request+Response-Exchange erfassen:

```bash
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
```

`exchange` unterstützt dieselben vier Runtime-Auswahlen und benötigt JSON-Objekte `request` und `response`. Es zeichnet ausdrücklich caller-supplied evidence auf und ist keine transparente Netzwerkinterzeption.

Runtime-State-/Model-Catalog-Daten bleiben über `probe` verfügbar. Die Standard-Localhost-Endpunkte sind Ollama `11434`, llama.cpp `8080`, vLLM `8000` und LM Studio `1234`.

## Full-Fidelity-Inhalt

v0.6.5 speichert vollständigen Content, den der ausgewählte Model-Runtime-Integrationspunkt offenlegt, in einem lokalen SHA-256-content-addressed Store. `event` bewahrt die vollständige gelieferte finale Response auf, ohne Request-Sichtbarkeit zu behaupten. `exchange` kann sowohl den gelieferten Request als auch die Response bewahren, einschließlich Messages/Prompts, Tool-Definitionen/-Calls/-Results, generiertem Assistant-Content, ausdrücklich vorhandenen Reasoning-/Thinking-Feldern, Request-Generation-Konfiguration und weiteren vom Runtime-Payload unterstützten Provider-Werten.

Der semantische JSONL-Sidecar enthält Referenzen statt großer Inline-Kopien. Kompakte Usage-/Timing-/Model-Metadaten bleiben für Graph-/Query-Zwecke verfügbar.

`content_complete_from_source: true` bedeutet, dass ExecWeave den vollständigen Wert gespeichert hat, der der CLI/dem Integrationspunkt geliefert wurde. Es bedeutet **nicht**, dass die Runtime verborgenen Modellzustand offengelegt hat, dass der Request notwendigerweise der finale post-rewrite Wire-Request des Providers ist oder dass ExecWeave Bytes beobachtet hat, die ihm nicht geliefert wurden.

Sensible anwendungsbezogene Werte im Request-/Response-Content bleiben erhalten. Endpoint-/Path-Sanitization und Provider-Metadata-Filtering sind keine allgemeine Content-Redaction.

## Runtime-spezifische Evidenz

Ollama kann zusätzlich Loaded-Model-State über `/api/ps` melden. llama.cpp kann Timing/Throughput, `/v1/models` und optional aggregierte `/metrics` bereitstellen; gelabelte Prometheus-Zeilen, die sensible lokale Identifikatoren enthalten können, bleiben durch den Metadata-Adapter eingeschränkt. vLLM und LM Studio teilen OpenAI-kompatibles Response-/Model-Catalog-Parsing, behalten aber runtime-spezifische Relationssemantik.

Catalog-Relations bleiben bewusst getrennt: Je nachdem, was der Quell-Endpunkt tatsächlich beweist, kann eine Runtime `LOADED_MODEL`, `SERVES_MODEL` oder `ADVERTISES_MODEL` liefern. LM-Studio-Catalog-Sichtbarkeit bleibt `ADVERTISES_MODEL`; ein Catalog-Eintrag beweist nicht automatisch, dass Gewichte im Speicher resident sind.

## Datenschutz und Evidenzgrenze

Model-Runtime-Content kann vollständige Prompts/Messages, Tool-Daten, generierte Responses, Reasoning-/Thinking-Text, Modellparameter, Konfigurationswerte, Pfade, Identifikatoren und sensible anwendungsbezogene Werte enthalten. Prüfen Sie das gesamte Run-Verzeichnis vor dem Teilen.

Eine Runtime-Response oder ein Exchange beweist nur, was dieser Integrationspunkt geliefert hat. Sie beweisen nicht für sich allein, welcher Agent den Request gestartet, welches Gateway ihn geroutet, welcher OS-Prozess ihn verursacht oder ob Dateibytes zu einem Model-/Network-Endpunkt geflossen sind. Cross-Layer-Identität benötigt explizit geteilte Identifikatoren oder separat markierte konservative Korrelation.
