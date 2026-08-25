# OpenCode Plugin

<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

ExecWeave는 project-local plugin을 통해 OpenCode와 통합합니다. OpenCode는 `tool.execute.before`와 `tool.execute.after` 모두에서 정확한 `sessionID + callID`를 제공하므로 동일한 logical tool call을 heuristic으로 짝지을 필요가 없습니다.

## 설치

현재 프로젝트에 생성된 plugin을 설치합니다.

```bash
execweave-opencode-plugin --install
```

다음 파일이 생성됩니다.

```text
.opencode/plugins/execweave.ts
```

OpenCode는 이 디렉터리의 project plugin을 자동 로드합니다. 기존 파일이 있으면 ExecWeave는 `--force`가 명시되지 않는 한 덮어쓰지 않습니다.

그다음 실행을 기록합니다.

```bash
execweave-opencode-record --open -- opencode
```

## 수집하는 semantic evidence

현재 baseline plugin은 최소 metadata만 전달합니다.

- `chat.message`
- `tool.execute.before`
- `tool.execute.after`

대표적인 Graph 관계:

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

OpenCode의 `callID`를 `tool_call` identity에 직접 사용합니다.

## 프라이버시 경계

OpenCode after-hook은 tool output을 볼 수 있지만 ExecWeave가 생성하는 plugin은 `output.output`이나 `output.metadata`를 전달하지 않습니다.

Plugin은 arguments를 전달하기 전에 축소합니다.

- `bash`: declared `command`만
- file-oriented tools: `filePath`, `file_path`, `path` 같은 path field만
- 필요한 경우 working-directory metadata

Raw write content, chat message parts, tool output은 ExecWeave hook으로 전송되지 않습니다.

## Tool → Process correlation

`callID`는 OpenCode 내부의 logical call identity를 증명하지만 OS PID는 아닙니다. Tool → Process는 여전히 보수적인 derived bridge이며 runtime evidence가 유일하게 지지하는 process를 보여줄 때만 생성됩니다.

Derived bridge는 항상 `inferred: true`, `causal: false`입니다.

## Evidence boundary

Plugin이 보고하는 것은 OpenCode semantic intent입니다. Process/file/network runtime observation은 OS collector가 독립적으로 확립합니다. Provider plugin을 declared command나 file action이 실제로 발생했다는 증거로 취급하지 않습니다.