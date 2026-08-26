# Model-Runtime-Integrationen

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

Model-Runtimes sind von semantischen Agent-/IDE-Adaptern und Inference-Gateways getrennt. Sie beschreiben, was ein lokaler oder selbst gehosteter Inferenzserver meldet; sie beweisen nicht, welcher Agent eine Anfrage initiiert hat.

Die aktuelle Basisimplementierung unterstützt **Ollama**, **llama.cpp**, **vLLM** und **LM Studio**.

## CLI

Finale Antwortmetadaten in Inferenzereignisse umwandeln:

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Runtime-Zustand oder Modellkataloge abfragen:

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

Standard-Endpunkte:

- Ollama: `http://localhost:11434`
- llama.cpp: `http://localhost:8080`
- vLLM: `http://localhost:8000`
- LM Studio: `http://localhost:1234`

## Gemeinsame OpenAI-kompatible Schicht

llama.cpp, vLLM und LM Studio verwenden gemeinsam einen OpenAI-kompatiblen Parser für Usage aus finalen Antworten und `/v1/models`-Katalogmetadaten. Die gemeinsame Schicht normalisiert Chat-Completions-artige `prompt_tokens` / `completion_tokens` und Responses-artige `input_tokens` / `output_tokens`, behält aber nur explizit erlaubte Token-Metadaten wie Cache- und Reasoning-Token-Anzahlen.

Runtime-spezifische Belege bleiben außerhalb des gemeinsamen Parsers. llama.cpp behält seine Timing-Felder und seinen Prometheus-Metrikadapter, anstatt diese Semantik vLLM oder LM Studio aufzuzwingen.

## Graphmodell

Die Runtime-Schicht kann erzeugen:

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --ADVERTISES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

Diese Relationen haben bewusst unterschiedliche Bedeutungen.

## Ollama

Finale Antwortmetadaten können Prompt-/Completion-Token-Anzahlen, Ladezeit, Prompt-Evaluationszeit, Generierungsdauer und Finish-Reason enthalten.

`/api/ps`-Snapshots können Metadaten zu geladenen Modellen wie VRAM-Größe, Kontextlänge, Format, Familie, Parametergröße und Quantisierung bereitstellen. Dies wird als `LOADED_MODEL` dargestellt, da der Endpunkt aktuell geladene Modelle meldet.

## llama.cpp

OpenAI-kompatible Antworten liefern normalisierte Usage sowie llama.cpp-spezifische Timing-/Durchsatzmetadaten. `/v1/models` wird als `SERVES_MODEL` dargestellt; optionales `/metrics` liefert aggregierte Runtime-Metriken.

Prometheus-Zeilen mit Labels werden übersprungen, da Labels sensible lokale Modellpfade oder andere Identifikatoren enthalten können.

llama.cpp-Modell-IDs, die wie lokale Pfade oder GGUF-Dateinamen aussehen, werden redigiert: Der vollständige native Identifikator wird für die Entitätsidentität gehasht, während nur der Basisname angezeigt wird.

## vLLM

vLLM verwendet die OpenAI-kompatible Antwort- und Modellkatalogschicht. `/v1/models` wird als `SERVES_MODEL` dargestellt, weil es die Modelle beschreibt, die dieser Serving-Endpunkt bereitstellt.

Prompt, Antwort, Reasoning-Text, Choices, Logprobs oder generierter Token-Text werden nicht in ExecWeave-Ereignisse kopiert.

## LM Studio

<!-- lmstudio-auto-live-v064 -->
Für die automatische Aufnahme in den Live Viewer starten Sie LM Studio unter ExecWeave mit einem expliziten lokalen Port, z. B. `execweave live --open -- lms server start --port 1234`. ExecWeave prüft vor dem Start, dass an diesem Endpoint noch keine kompatible API läuft, und probt `/v1/models` erst nach einem erfolgreichen Launcher-Exit. Die Relation bleibt `ADVERTISES_MODEL` und wird nicht zu `LOADED_MODEL` hochgestuft.

LM Studio verwendet denselben OpenAI-kompatiblen Antwortparser, aber sein `/v1/models`-Ergebnis wird als `ADVERTISES_MODEL` und nicht als `LOADED_MODEL` dargestellt.

Diese Unterscheidung ist bewusst: LM Studio kann heruntergeladene Modelle für den Server sichtbar machen, auch in Konfigurationen, in denen ein Modell erst bei Bedarf geladen wird. Ein Katalogeintrag beweist daher nicht, dass Modellgewichte zum Beobachtungszeitpunkt im Speicher resident waren.

## Datenschutzgrenze

ExecWeave schließt Prompt-Text, Antwortinhalt, Thinking-/Reasoning-Text, Choices, Logprobs und rohe generierte Tokens ausdrücklich aus dieser Schicht aus.

Erlaubte Metadaten können Modellidentität, Request-Identität, Prompt-/Input-Token-Anzahlen, Completion-/Output-Token-Anzahlen, Gesamt-Tokens, Cache-Token-Anzahlen, Reasoning-Token-Anzahlen und runtime-spezifische Timing-Metadaten enthalten. Absolute lokale Modellpfade werden für unterstützte OpenAI-kompatible lokale Runtimes redigiert; llama.cpp behält eine strengere GGUF-Pfadredaktion bei.

Aggregierte Runtime-Metriken werden nicht automatisch einem bestimmten Agent oder einer bestimmten Inferenzanfrage zugeordnet.

## Beleggrenze

Eine Runtime-API beweist nur, was dieser Inferenzserver gemeldet hat. Sie beweist nicht für sich, welcher Agent die Anfrage initiiert, welches Gateway sie geroutet oder welcher OS-Prozess sie verursacht hat.

Schichtübergreifende Identität erfordert explizite gemeinsame Identifikatoren oder einen separat definierten konservativen Korrelationsmechanismus. Abgeleitete Korrelation muss als Inferenz markiert bleiben und darf nicht als kausaler Beleg erscheinen.
