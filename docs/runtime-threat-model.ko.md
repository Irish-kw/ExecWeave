<!-- i18n-nav:start -->
<p align="center">
  <a href="runtime-threat-model.md">English</a> |
  <a href="runtime-threat-model.zh-TW.md">繁體中文</a> |
  <a href="runtime-threat-model.zh-CN.md">简体中文</a> |
  <a href="runtime-threat-model.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="runtime-threat-model.fr.md">Français</a> |
  <a href="runtime-threat-model.de.md">Deutsch</a> |
  <a href="runtime-threat-model.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Runtime 위협 모델과 알려진 회피 경계

이 문서는 ExecWeave v0.6.5가 테스트 가능한 계약의 일부로 취급하는 관측 한계를 정의합니다. 이는 **관측성 위협 모델**이며 sandbox 안전 보장이 아닙니다. 관측 대상 명령은 신뢰할 수 없고 활동을 관측하기 어렵게 만들 수 있지만, 운영체제 커널과 ExecWeave 설치 자체는 커널 수준으로 침해되지 않았다고 가정합니다.

## Portable backend

Portable backend는 process/network 활동에 psutil snapshot을, filesystem 변경에 watchdog를 사용합니다.

- **짧게 존재하는 process:** child가 두 process sample 사이에서 시작하고 종료되면 완전히 놓칠 수 있습니다. 설정된 poll interval은 blind window의 최대값을 보장하지 않으며 scheduler delay로 실제 간격이 더 길어질 수 있습니다.
- **짧게 존재하는 socket:** 연결이 두 socket observation 사이에서 생성되고 사라지면 놓칠 수 있습니다. 권한 또는 platform API 제한으로 socket state가 보이지 않을 수도 있습니다.
- **root command보다 오래 살아 있는 descendant:** root observation이 끝날 때 child가 살아 있으면 ExecWeave는 거짓 exit event를 만들지 않습니다. 그러나 portable run은 always-on monitor가 아니므로 이후 살아남거나 reparent된 descendant의 활동은 완료된 run의 관측 범위를 벗어납니다.
- **Filesystem attribution:** watchdog 변경은 session-correlated observation이며 의도적으로 `causal=false`입니다. 특정 PID가 write를 수행했다는 증거가 아닙니다.
- **Negative evidence:** portable backend에서 process/network/filesystem event가 없다는 사실은 해당 활동이 발생하지 않았다는 증거가 아닙니다.

## Linux strace backend

strace backend는 `strace -ff`로 시작된 command의 lineage와 선택된 syscall class를 추적합니다.

- traced lineage 내부에서는 clone/fork 증거로 portable polling이 놓칠 수 있는 짧은 descendant를 보존할 수 있습니다.
- 지원되는 syscall 증거가 있으면 filesystem/network event를 traced process에 attribution할 수 있습니다.
- 이는 **OS-wide visibility가 아닙니다**. traced lineage 외부 활동, 지원되지 않거나 파싱되지 않은 syscall pattern, permission/ptrace 제한, 선택된 evidence class 밖의 kernel behavior는 보장 범위 밖입니다.
- open의 read/write access mode는 byte-level data flow를 증명하지 않습니다. ExecWeave는 이후 실제로 읽거나 쓴 바이트 내용을 주장하지 않습니다.

## Specialized hooks 및 direct API integrations

Claude, Codex, Antigravity, Cursor, OpenCode, model-runtime, gateway, proxy, direct-API integration은 명시된 integration point에서 더 강한 semantic content evidence를 제공할 수 있지만 provider-hidden state를 공개하지 않습니다.

- response-only integration은 ExecWeave에 제공된 response fields만 증명합니다.
- caller-supplied request+response exchange는 제공된 exchange만 증명하며 transparent wire interception을 의미하지 않습니다.
- hook coverage는 upstream agent/IDE가 hook에 실제로 노출하는 정보에 제한됩니다.
- full-fidelity storage는 integration point에서 노출된 내용을 완전하게 저장한다는 뜻이며 model provider나 OS 전체를 완전하게 본다는 뜻이 아닙니다.

## Regression contract

`tests/test_threat_model.py`는 다음 경계를 deterministic executable tests로 고정합니다.

1. 두 process sample 사이에만 존재하는 portable child.
2. 두 socket sample 사이에만 존재하는 portable socket.
3. root-process observation 종료 시 살아 있는 child에 거짓 exit event를 만들지 않음.
4. portable filesystem change가 session-correlated, non-causal로 유지됨.
5. 대응하는 strace trace case가 짧은 child의 `SPAWNED` attribution을 보존함.

테스트는 “N ms sleep 후 CI가 우연히 놓치기를 기대”하는 timing race를 사용하지 않습니다. blind window를 observation 사이의 명시적 상태로 모델링해 Linux, macOS, Windows에서 재현 가능하게 합니다.

## Missing event의 의미

Missing event는 해당 run의 canonical evidence에 그 observation이 없다는 뜻뿐입니다. 향후 backend가 완전한 negative-evidence scope를 명시하고 입증하기 전에는 “발생하지 않았다”는 증거가 아닙니다. Finding severity와 evidence fidelity는 서로 독립적인 차원입니다.
