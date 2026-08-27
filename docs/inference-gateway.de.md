# Inference Gateway Integrations

<!-- i18n-nav:start -->
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
<!-- i18n-nav:end -->

Inference Gateways bilden eine eigene Evidenzebene zwischen Agent/Client und Model-Provider/-Runtime. ExecWeave modelliert derzeit **OpenRouter** und **LiteLLM Proxy** und hält Requested Model, Resolved Model, Routed Provider und Deployment Identity getrennt.

## CLI

Eine finale Gateway-Antwort von stdin erfassen:

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
```

Nur für OpenRouter kann ein vom Aufrufer geliefertes Request+Response-Objekt erfasst werden:

```bash
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

`exchange` erwartet JSON-Objekte `request` und `response` auf stdin. Dies ist ausdrücklich caller-supplied evidence und **keine** transparente Wire-Interzeption.

OpenRouter-Generation-Metadaten bleiben über `generation` verfügbar.

## OpenRouter-Full-Fidelity-Grenze

Bei `event --gateway openrouter` speichert v0.6.5 die vollständige gelieferte finale Antwort im lokalen content-addressed Store und emittiert zusätzlich die kompakte Routing-/Usage-Zusammenfassung. Bei `exchange --gateway openrouter` können der vollständige vom Aufrufer gelieferte Request und die Response gespeichert werden.

`content_complete_from_source: true` bedeutet, dass der vollständige an diesen Integrationspunkt gelieferte Wert gespeichert wurde. Es behauptet keine Sicht auf Requests vor Provider-seitiger Umschreibung, verborgene Routing-Stufen, Modellinternas oder Netzwerkbytes, die ExecWeave nicht beobachtet hat.

Sensible anwendungsbezogene Werte im gelieferten Request/Response-Content bleiben erhalten. Endpoint-Identität wird separat bereinigt; Query-Parameter/Fragmente und das Filtern erkannter Transport-Credentials ersetzen keine Content-Redaction.

## LiteLLM-Grenze

LiteLLM bleibt im aktuellen v0.6.5-Baseline eine metadatenorientierte Integration. Response-Parser und optionaler Custom Callback erhalten Routing-/Usage-Felder über einen strikten Vertrag; OpenRouter-Full-Fidelity macht den LiteLLM-Callback nicht automatisch zu einer vollständigen Inhaltsaufzeichnung.

Callback-Konfiguration ausgeben und den konfigurierten Proxy im aktuellen ExecWeave-Run starten:

```bash
execweave-litellm-callback --print-config
execweave live --open -- litellm --config config.yaml
```

Ohne `EXECWEAVE_SEMANTIC_SIDECAR` ist der Callback ein No-op. Provider-/Deployment-Identität wird nur bei autoritativer Evidenz ausgegeben; ExecWeave leitet sie nicht aus Modellnamen-Präfixen oder Provider-URLs ab.

## Exakte Gateway ↔ Model-Runtime-Identität

Wenn der Aufrufer bereits einen ausdrücklich geteilten Request-Identifier hat, kann `execweave-inference-link` Gateway- und Runtime-Request-Nodes verbinden, ohne die Ebenen zusammenzuführen. Der rohe Identifier wird nicht persistiert; der Link verwendet einen SHA-256-abgeleiteten Identity-Hash.

```text
identity_exact: true
inferred: false
causal: false
```

Dies ist exakte logische Request-Identität, kein Beweis dafür, dass ein bestimmter Agent oder OS-Prozess die Inferenz verursacht hat.

## Datenschutz und Evidenzgrenze

OpenRouter-Full-Fidelity-Artefakte können vollständigen Request/Response-Content und sensible anwendungsbezogene Werte enthalten. LiteLLM-Artefakte folgen ihrem engeren Metadata-/Callback-Vertrag. Behandeln Sie Gateway-Evidenz als sensibel und prüfen Sie sie vor dem Teilen.

Gateway-Beobachtungen beweisen nur, was der Integrationspunkt gemeldet hat oder welche autoritativen Routing-Daten zusammen mit ihm geliefert wurden. Sie beweisen nicht für sich allein, welcher lokale Agent einen Request gestartet, welcher Runtime-Prozess ihn bedient oder welcher OS-Prozess ihn verursacht hat. Fehlende Shared Identity darf nicht durch Timestamp-/Modellnamen-Raten ersetzt werden.
