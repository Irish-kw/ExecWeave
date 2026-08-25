from __future__ import annotations

import argparse
from pathlib import Path

_PLUGIN = r'''const safeArgs = (tool, args) => {
  if (!args || typeof args !== "object") return {}
  const safe = {}
  if (tool === "bash" && typeof args.command === "string") {
    safe.command = args.command
  }
  for (const key of ["filePath", "file_path", "path", "cwd", "workdir"]) {
    if (typeof args[key] === "string") safe[key] = args[key]
  }
  return safe
}

export const ExecWeavePlugin = async ({ directory }) => {
  const emit = async (payload) => {
    try {
      const proc = Bun.spawn(["execweave-opencode-hook"], {
        stdin: "pipe",
        stdout: "ignore",
        stderr: "inherit",
        env: process.env,
      })
      proc.stdin.write(JSON.stringify({ ...payload, cwd: directory }))
      proc.stdin.end()
      await proc.exited
    } catch (error) {
      console.error("ExecWeave OpenCode plugin warning:", error)
    }
  }

  return {
    "chat.message": async (input) => {
      await emit({
        hook_event_name: "chat.message",
        sessionID: input.sessionID,
        agent: input.agent,
        model: input.model,
        messageID: input.messageID,
      })
    },
    "tool.execute.before": async (input, output) => {
      await emit({
        hook_event_name: "tool.execute.before",
        sessionID: input.sessionID,
        callID: input.callID,
        tool: input.tool,
        args: safeArgs(input.tool, output.args),
      })
    },
    "tool.execute.after": async (input) => {
      await emit({
        hook_event_name: "tool.execute.after",
        sessionID: input.sessionID,
        callID: input.callID,
        tool: input.tool,
        args: safeArgs(input.tool, input.args),
      })
    },
  }
}
'''


def plugin_text() -> str:
    return _PLUGIN


def install_plugin(root: str | Path, *, force: bool = False) -> Path:
    project = Path(root).expanduser().resolve()
    target = project / ".opencode" / "plugins" / "execweave.ts"
    if target.exists() and target.stat().st_size > 0 and not force:
        raise FileExistsError(f"OpenCode ExecWeave plugin already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(plugin_text(), encoding="utf-8", newline="\n")
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-opencode-plugin",
        description="Install or print the local ExecWeave OpenCode telemetry plugin.",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--install", action="store_true")
    action.add_argument("--print-plugin", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.print_plugin:
        print(plugin_text(), end="")
        return 0
    try:
        target = install_plugin(args.root, force=args.force)
    except (OSError, FileExistsError) as exc:
        parser.error(str(exc))
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
