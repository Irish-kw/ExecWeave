# Run Integrity(실행 무결성)

<!-- i18n-nav:start -->
<p align="center">
  <a href="run-integrity.md">English</a> |
  <a href="run-integrity.zh-TW.md">繁體中文</a> |
  <a href="run-integrity.zh-CN.md">简体中文</a> |
  <a href="run-integrity.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="run-integrity.fr.md">Français</a> |
  <a href="run-integrity.de.md">Deutsch</a> |
  <a href="run-integrity.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave v0.6.5는 완료된 run을 deterministic SHA-256 inventory로 seal하고 나중에 동일한 inventory를 verify할 수 있습니다. 이 기능은 로컬에서 seal 이후 발생한 손상이나 변경을 탐지하기 위한 것입니다. manifest와 evidence가 동일한 쓰기 가능한 trust boundary 안에 남아 있는 경우 공격자에 저항하는 tamper evidence라고 표현하지 않습니다.

## 범위

`execweave-integrity seal`은 선택한 run directory 아래의 모든 regular file을 재귀적으로 조사하되 `integrity.json` 자체는 제외합니다. entry는 relative POSIX path 기준으로 결정적으로 정렬되며 path, byte size, SHA-256 digest를 기록합니다. Symbolic link는 따라가거나 조용히 정규화하지 않고 거부합니다.

seal은 capture와 필요한 derived artifacts가 모두 끝난 뒤에만 실행하는 것을 전제로 합니다. seal 이후 생성된 file은 unsealed로 보고되며 sealed file이 수정, 교체 또는 삭제되면 verification이 실패합니다.

## Seal 및 verify

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

`seal`은 기존 integrity contract를 덮어쓰지 않습니다. `verify`는 manifest schema가 유효하고 manifest body digest가 일치하며 모든 sealed file의 size와 SHA-256이 맞고 seal 이후 추가 regular file이 존재하지 않을 때만 성공합니다.

## Manifest contract

| 필드 | 의미 |
| --- | --- |
| `schema_version` | Integrity schema 버전이며 v0.6.5는 `0.1`부터 시작합니다. |
| `files` | 결정적 순서의 sealed file inventory입니다. |
| `manifest_body_sha256` | 이 digest field를 제외한 canonical manifest content의 SHA-256입니다. |
| `trust_model` | local seal이 증명하는 범위와 증명하지 않는 범위를 명시합니다. |

manifest에는 `malicious_writer_resistance: false`와 `external_trust_anchor: false`가 반드시 기록됩니다. 이는 선택적인 문서 표현이 아니라 schema contract의 일부입니다.

## Trust boundary

local digest는 accidental corruption, 불완전한 copy, seal 시점 이후의 post-seal change를 찾는 데 유용합니다. 그러나 run evidence와 `integrity.json`을 모두 다시 쓸 수 있는 process를 막지는 못합니다. 그런 process는 hash를 다시 계산하여 내부적으로 일관된 새 manifest를 만들 수 있습니다.

더 강한 보장이 필요하면 `manifest_body_sha256` 또는 전체 manifest를 observed process가 쓸 수 없는 위치로 복사하거나 해당 process가 접근할 수 없는 key로 보호 또는 서명해야 합니다. 실제 trust anchor는 그 외부 작업에서 만들어집니다. ExecWeave는 같은 directory의 manifest 자체가 trust anchor라고 주장하지 않습니다.

## 운영 규칙

완료된 run만 seal하십시오. archived 또는 transferred evidence에 의존하기 전에 verify하십시오. verification error는 directory가 sealed inventory와 더 이상 정확히 일치하지 않는다는 신호이지 악의적 행위를 입증하는 것은 아닙니다. seal 이후 새 artifact가 필요하다면 먼저 생성한 뒤 새로운 finalized copy를 seal하고 기존 manifest를 조용히 다시 쓰지 마십시오.
