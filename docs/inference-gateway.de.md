# Inference-Gateway-Integrationen

<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a> |
  <a href="inference-gateway.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="inference-gateway.ru.md">Русский</a>
</p>

Inference-Gateways bilden eine separate Schicht zwischen Agent/Client und Modell-Provider/-Runtime. Die aktuelle Basisimplementierung unterstützt **OpenRouter** und **LiteLLM Proxy**.

ExecWeave bewahrt angefordertes Modell, aufgelöstes Modell, gerouteten Provider und Deployment-Identität als getrennte Belege, statt sie in einem einzigen Modellfeld zusammenzufassen.

## CLI

Eine finale OpenRouter-Antwort konvertieren:

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

Eine finale LiteLLM-Proxy-Antwort konvertieren:

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

OpenRouter-Generierungsmetadaten konvertieren:

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

Wenn ein Aufrufer über eine explizite gemeinsame Request-Identität zwischen einer Gateway-Beobachtung und einer Model-Runtime-Beobachtung verfügt, können die beiden bestehenden Request-Knoten verbunden werden:

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

Gateway-Antwort-JSON wird von stdin gelesen. Standard-Endpunktidentitäten sind:

- OpenRouter: `https://openrouter.ai/api/v1`
- LiteLLM Proxy: `http://localhost:4000`

## Graphmodell

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_request --ROUTED_TO_DEPLOYMENT--> inference_deployment
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
inference_request --SAME_INFERENCE_REQUEST--> inference_request
```

Eine LiteLLM-Anfrage kann beispielsweise bewahren:

```text
requested_model = assistant
resolved_model  = azure/gpt-5
provider        = Azure
deployment      = deployment-west
```

Diese Fakten sind nicht austauschbar.

## OpenRouter

OpenRouter-Antwortmetadaten halten das angeforderte Modell getrennt vom Antwortmodell und einem explizit beobachteten gerouteten Provider. OpenRouter-spezifische Generierungsmetadaten können zusätzlich Latenz, Generierungszeit, Kosten, native Token-Anzahlen, Streaming-Status und Abbruchstatus melden.

## LiteLLM Proxy

LiteLLM wird als `inference_gateway` modelliert, nicht als `model_runtime`. Seine OpenAI-kompatible Antwort liefert Request-/Modell-/Usage-Metadaten über dieselbe Gateway-Belegschicht.

`--provider-name` und `--deployment-id` werden nur ausgegeben, wenn autoritative Routing-Metadaten dem Aufrufer oder Adapter vorliegen. ExecWeave **leitet keinen** Provider oder kein Deployment aus einer Modellzeichenfolge wie `azure/...` ab. Wenn diese Routing-Fakten nicht verfügbar sind, werden die entsprechenden Kanten ausgelassen.

## Exakte Gateway ↔ Model Runtime-Identität

`execweave-inference-link` ist absichtlich strenger als zeitliche Korrelation. Es erzeugt `SAME_INFERENCE_REQUEST` nur, wenn der Aufrufer bereits einen expliziten Identifikator besitzt, der zwischen Gateway- und Runtime-Beobachtung geteilt wird. Identität wird niemals aus Zeitstempeln, Modellnamen, Token-Anzahlen, Latenz oder anderen Ähnlichkeitssignalen geraten.

Gateway- und Runtime-Requests bleiben getrennte Knoten und behalten ihre schichtspezifischen Metadaten. Die Identitätskante ist markiert als:

```text
identity_exact: true
inferred: false
causal: false
```

Das bedeutet, dass beide Beobachtungen laut der bereitgestellten gemeinsamen Identität dieselbe logische Inferenzanfrage betreffen. Es beweist **nicht**, dass ein bestimmter Agent oder OS-Prozess die Anfrage verursacht hat. Ohne explizite gemeinsame Identität erzeugt ExecWeave diese Kante nicht.

## Usage-Metadaten

Der Antwortparser erlaubt gezielt Metadaten wie Prompt-/Input-Tokens, Completion-/Output-Tokens, Gesamt-Tokens, gecachte Prompt-Tokens, Cache-Write-Tokens, Reasoning-Token-Anzahlen und gemeldete Kosten.

## Datenschutzgrenze

ExecWeave speichert weder Prompt-Text noch Antwort-/Completion-Inhalte, Reasoning-Text, Choices oder beliebige Provider-Payload-Felder. Zugangsdaten, Query-Parameter und Fragmente von Gateway-Endpunkten werden aus der gespeicherten Endpunktidentität entfernt.

Das ursprünglich angeforderte Modell wird niemals aus der Antwort geraten; es muss vom Aufrufer explizit bereitgestellt werden, sofern dieser Beleg verfügbar ist. Die rohe `--shared-request-id`, die für exakte schichtübergreifende Identität verwendet wird, wird nicht gespeichert; ExecWeave legt nur einen SHA-256-abgeleiteten Identitätshash am Link-Ereignis ab.

## Beleggrenze

Gateway-Antwortmetadaten beweisen nur, was das Gateway gemeldet hat oder welche autoritativen Routing-Metadaten zusammen mit der Antwort bereitgestellt wurden. Sie beweisen nicht, welcher lokale Agent die Anfrage initiiert, welcher Model-Runtime-Prozess sie bedient oder welcher OS-Prozess sie verursacht hat.

Gateway-Ereignisse bleiben deshalb nicht kausal (`causal: false`) und getrennt von semantischen Agent-/IDE-Belegen, Model-Runtime-Belegen und OS-Runtime-Belegen. Eine exakte gemeinsame Request-Identität kann Gateway- und Model-Runtime-Beobachtungen verbinden, ohne ihre Schichten zusammenzuführen. Separat inferierte Korrelation muss ausdrücklich als Inferenz markiert bleiben und darf niemals als kausaler Beleg dargestellt werden.
