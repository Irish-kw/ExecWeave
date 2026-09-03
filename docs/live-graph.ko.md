<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave는 AI Agent 또는 임의의 command가 실행 중이어도 local execution graph를 계속 stream할 수 있습니다.

```bash
execweave live --open -- claude
```

## 현재 계약

Live runtime collector는 의도적으로 크로스플랫폼 `portable` backend를 사용합니다. v0.6.4부터 각 live run은 run-specific sidecar를 통해 두 번째 append-only specialized evidence stream도 수집할 수 있습니다.

ExecWeave는 실행된 command에 sidecar 경로를 다음 환경 변수로 전달합니다.

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Specialized evidence는 여러 attribution-safe 경로를 통해 자동으로 들어올 수 있습니다.

- 설정된 Claude Code, OpenAI Codex, Antigravity, Cursor hooks;
- 설치된 OpenCode plugin;
- ExecWeave가 지원되는 local Ollama, llama.cpp, vLLM server를 시작할 때의 loopback model-catalog probe;
- `lms server start --port <port>`에 대한 success-gated LM Studio post-launch probe. 단, launch 전에 동일한 compatible endpoint가 존재하지 않아야 함;
- ExecWeave custom callback을 한 번 설정했고 현재 `execweave live` 환경 안에서 시작된 LiteLLM Proxy.

이것은 `live`가 provider, gateway, runtime 설정을 몰래 수정한다는 뜻이 **아닙니다**. 필요한 hook/plugin/callback integration은 사전에 한 번 설정해야 합니다. 자동 model-runtime probe는 인식된 local launch command와 loopback endpoint에만 제한됩니다. OpenRouter routing metadata는 자동이 아닙니다. 원격 HTTPS/network observation만으로는 authoritative provider routing 정보를 알 수 없기 때문입니다.

Linux `strace` backend는 현재 command 종료 후 trace file을 parse합니다. 더 강한 syscall-backed attribution을 제공하지만 현재 구현에서는 live event source가 아닙니다. ExecWeave는 post-processed evidence를 live telemetry라고 표시하지 않습니다.

더 강한 Linux post-run attribution이 필요하면:

```bash
execweave record --backend strace --open -- claude
```

## v0.6.4 data flow

```text
specialized producers ─┐
  Agent hooks/plugin   │
  model-runtime probe  ├─→ semantic.jsonl ────────────────┐
  LiteLLM callback     │                                  │
                      ─┘                                  │
                                                         ↓
command ─→ portable ─→ events.jsonl ───────→ incremental live normalizer
                                                         ↓
                                                  GraphAccumulator
                                                         ↓
                                              localhost HTTP server
                                                         ↓
                                                 /live.json deltas
                                                         ↓
                                                   browser / Top
```

OS runtime evidence는 독립적인 ground-truth stream으로 유지됩니다. Specialized evidence는 provisional하게 live graph에 정규화되며 raw runtime stream을 다시 쓰거나 없는 evidence를 만들어낼 수 없습니다.

Browser와 detached `execweave top` dashboard는 sequence-numbered `/live.json` snapshots/deltas를 사용합니다. `/graph.json`은 현재 snapshot endpoint로 계속 제공됩니다. Incremental ingestion은 새로 append된 JSONL bytes만 tail하고, 마지막 줄이 incomplete이면 newline이 올 때까지 buffer합니다.

Command 종료 시 ExecWeave는:

1. completed runtime event stream을 validate하고;
2. launch 전에 준비된 attribution-safe post-command specialized observation을 완료하고;
3. specialized evidence가 있으면 canonical runtime + specialized merge를 수행해 `events.semantic.jsonl`을 만들고;
4. provisional live state를 신뢰하지 않고 해당 canonical stream에서 final graph를 다시 만들고;
5. `graph.json`과 standalone `viewer.html`을 쓰고;
6. live graph를 finished로 표시한 뒤 final viewer를 잠시 serve하고 local server를 종료합니다.

Specialized event가 하나도 없으면 final materialization은 runtime-only로 유지됩니다.

## Live Viewer에 자동으로 들어오는 specialized integrations

| Integration | v0.6.4 Live Viewer 자동 전달 |
| --- | --- |
| Claude Code | **Yes**, ExecWeave hooks 설정 후 |
| OpenAI Codex | **Yes**, ExecWeave hooks 설정 후 |
| Antigravity | **Yes**, ExecWeave hooks 설정 후 |
| Cursor | **Yes**, ExecWeave hooks 설정 후 |
| OpenCode | **Yes**, ExecWeave plugin 설치 후 |
| Ollama | **Yes**, 인식된 local `ollama serve` launch인 경우 |
| llama.cpp | **Yes**, 인식된 local `llama-server` launch인 경우 |
| vLLM | **Yes**, 인식된 local vLLM server launch인 경우 |
| LM Studio | **Yes**, `lms server start --port <port>`가 성공하고 launch 전 endpoint가 없었던 경우 |
| LiteLLM Proxy | **Yes**, callback 설정 후 proxy가 live sidecar를 상속한 경우 |
| OpenRouter | **No** automatic routing metadata. local client의 OS/network activity는 관찰 가능 |

이 integration들은 동일한 per-run specialized sidecar contract를 공유하지만 evidence layer와 의미는 분리되어 유지됩니다. Model catalog는 Agent가 request를 일으켰다는 증거가 아니고, gateway response는 특정 OS process가 request를 일으켰다는 증거가 아닙니다. 누락된 identity는 추측하지 않습니다.

## Terminal Top

`top`은 Agent terminal 위에 렌더링되지 않습니다. 기존 terminal은 Agent가 계속 상호작용할 수 있고, dashboard는 같은 localhost live session에 별도 terminal window에서 attach합니다.

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open`은 browser Viewer도 추가합니다. Detached dashboard는 attach-only client이며 두 번째 Agent를 시작하지 않습니다. 내부 attach URL은 localhost HTTP로 제한됩니다.

## Network exposure

Live server는 다음 address에만 bind합니다.

```text
127.0.0.1
```

`0.0.0.0`으로 노출되지 않으며 LAN의 다른 host에서 접근하도록 설계되지 않았습니다.

Port를 명시하려면:

```bash
execweave live --port 8765 --open -- claude
```

기본 `--port 0`은 OS가 사용 가능한 local port를 고르게 합니다.

## Artifacts

기본 run directory:

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── semantic.jsonl
├── events.semantic.jsonl      # specialized evidence가 있을 때만 materialize
├── graph.json
└── viewer.html
```

`events.jsonl`은 항상 runtime-only입니다. `semantic.jsonl`은 raw specialized sidecar이며 Agent/IDE, model-runtime, inference-gateway evidence를 포함할 수 있습니다. Specialized evidence가 있으면 final `graph.json`은 `events.semantic.jsonl`에서 만들어지고, 없으면 `events.jsonl`에서 직접 만들어집니다.

다른 directory를 사용하려면:

```bash
execweave live --output-dir my-live-run --open -- claude
```

기존 non-empty artifact는 overwrite하지 않고 거부합니다.

## Provisional live normalization

Live run 중에는 session이 아직 끝나지 않았으므로 두 JSONL stream 모두 incomplete일 수 있습니다.

따라서 live normalizer는 incremental하고 conservative하게 동작합니다. 지금까지 관찰된 runtime process identity를 specialized process reference 해결에 사용할 수 있지만, 누락된 identity는 추측하지 않습니다. 아직 정규화할 수 없는 specialized event도 live에서 보였다는 이유만으로 더 강한 evidence가 되지 않습니다.

Sidecar truncation이 발생하면 provisional materialization을 reset하고 현재 file에서 replay합니다. Incomplete trailing JSONL record는 complete event로 처리하지 않고 buffer합니다. Final graph는 runtime validation 성공 후 canonical merge에서 다시 만들어집니다.

## Automatic model-runtime probe boundary

Automatic model-runtime observation 범위는 의도적으로 좁습니다. ExecWeave는 인식된 local server launch command와 local/loopback endpoint만 probe합니다. Probe failure는 fail-open이며 실행한 command의 결과를 바꾸지 않습니다.

Ollama, llama.cpp, vLLM은 server 실행 중 local model state/catalog를 sample할 수 있습니다. LM Studio는 다릅니다. `lms server start`는 persistent server를 시작하는 short-lived launcher이므로 ExecWeave는 launch 전에 observation을 준비하고, compatible endpoint가 이미 존재하면 이번 session에 귀속시키지 않습니다. Launcher가 성공적으로 종료된 경우에만 post-launch catalog를 materialize합니다.

Catalog relation은 runtime-specific semantics를 유지합니다. 예를 들어 LM Studio catalog visibility는 `ADVERTISES_MODEL`이며 model weights가 그 시점에 memory resident였다는 증거가 아닙니다.

## LiteLLM callback boundary

LiteLLM Proxy는 custom-callback configuration에서 `execweave.litellm_callback.execweave_litellm_callback`을 한 번 로드할 수 있습니다. Proxy가 `execweave live` 안에서 실행되면 `EXECWEAVE_SEMANTIC_SIDECAR`를 상속하고 whitelist된 routing/usage metadata만 해당 run에 씁니다.

Callback은 messages, response content, model parameters, arbitrary metadata, API-key metadata, provider `api_base`를 저장하지 않습니다. Provider identity를 model string이나 URL에서 추측하지 않습니다. Run-specific sidecar 환경 변수가 없으면 callback은 no-op입니다.

LiteLLM config fragment 출력:

```bash
execweave-litellm-callback --print-config
```

## Portable-backend limitations

현재 live runtime layer는 portable collector의 제한을 그대로 가집니다.

- process discovery는 polling-based;
- 매우 짧게 실행되는 process는 놓칠 수 있음;
- filesystem change는 process-attributed가 아니라 session-correlated;
- per-process network inspection은 OS visibility와 permissions에 의존.

이 제한은 event attribution metadata에 계속 표시됩니다. Live Viewer는 non-causal observation을 causal edge로 upgrade하지 않습니다.

## Large-session safety

Live update는 bounded delta history를 사용하며 매 poll마다 전체 event stream을 replay하지 않습니다. Graph가 Viewer safety budget을 넘으면 live endpoint는 compact counts-only payload로 전환되어 browser가 unsafe한 대형 SVG graph를 materialize하지 않아도 collection과 final canonical artifact generation을 계속할 수 있습니다.

## Future native live backends

예정된 collector:

- Linux eBPF;
- Windows ETW;
- macOS Endpoint Security.

동일한 ExecWeave event semantics를 유지하면서 completeness, process attribution, runtime overhead를 개선하는 것이 목표입니다.

## CI coverage

Repository CI는 다음을 포함합니다.

- localhost live-session startup 및 final artifact generation;
- sequence-numbered snapshot/delta와 resynchronization;
- incomplete trailing JSONL record;
- runtime identity가 ready되기 전 semantic sidecar arrival;
- semantic sidecar truncation 및 replay;
- canonical final runtime + specialized rebuild;
- Claude, Codex, Antigravity, Cursor, OpenCode의 automatic shared-sidecar delivery;
- Ollama, llama.cpp, vLLM automatic local model-runtime probe와 attribution-safe LM Studio launch handling;
- LiteLLM callback privacy, fail-open behavior, final live-graph materialization;
- 두 번째 Agent를 시작하지 않는 detached Top behavior;
- localhost-only Top attach URL;
- clean-wheel 설치 후 LiteLLM callback setup command.
