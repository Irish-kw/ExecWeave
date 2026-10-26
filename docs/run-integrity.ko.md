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


## 로컬 무결성 검사의 한계

<!-- ew:trust:local-only -->

로컬 `seal` / `verify`는 우발적인 손상과 다시 seal하지 않은 변경을 감지합니다. **기록과 `integrity.json`에 쓸 수 있는 프로세스는 해시를 재계산하고 일관된 기록을 다시 seal할 수 있습니다.** `valid: true`는 로컬 일관성만 의미하며 변조 방지 감사를 의미하지 않습니다.

<!-- ew:trust:privileged -->

root, sudo 권한을 가진 Agent 또는 출력 디렉터리에 쓸 수 있는 모든 프로세스는 기록과 manifest를 함께 변경할 수 있습니다. 운영체제 권한과 프로세스 격리로 보호하세요. 쓰기 권한이 같다면 경로만 바꾸어도 격리가 되지 않습니다.

<!-- ew:compat:no-downgrade -->

**v0.8.35 이상에서 작성한 기록을 v0.8.34 reader로 여는 다운그레이드는 지원하지 않습니다.** 이전 reader는 `observation_assessment`를 경고 없이 버리고 관측 완전성을 잘못 표시할 수 있습니다. v0.8.35 이상 reader의 결론만 사용하세요. recorder를 롤백했다고 reader를 롤백해서는 안 됩니다.

완료된 run만 seal하고 보관된 자료를 사용하기 전에 verify하세요. 검증 실패는 로컬 불일치이지 악의적인 행동의 단독 증거가 아닙니다. 이 도구는 기록이나 다이제스트를 전송하지 않으며 별도의 권한 경계를 제공하지 않습니다.
