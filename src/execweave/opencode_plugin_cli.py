from __future__ import annotations

import argparse
import json
from pathlib import Path

_PLUGIN = r'''const sessionIDFrom = (value, depth = 0) => {
  if (!value || typeof value !== "object" || depth > 5) return undefined
  for (const key of ["sessionID", "sessionId", "session_id"]) {
    if (typeof value[key] === "string" && value[key]) return value[key]
  }
  const children = Array.isArray(value) ? value : Object.values(value)
  for (const child of children) {
    const found = sessionIDFrom(child, depth + 1)
    if (found) return found
  }
  return undefined
}

const withoutTransportCredentials = (value) => {
  if (!value || typeof value !== "object") return value
  const banned = new Set(["authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key", "api-key", "api_key", "apikey", "access_token", "refresh_token", "client_secret", "password"])
  if (Array.isArray(value)) return value.map(withoutTransportCredentials)
  const clean = {}
  for (const [key, child] of Object.entries(value)) {
    if (!banned.has(key.toLowerCase())) clean[key] = withoutTransportCredentials(child)
  }
  return clean
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
      let timer
      const timeout = new Promise((resolve) => {
        timer = setTimeout(() => {
          try { proc.kill() } catch {}
          resolve(undefined)
        }, 5000)
      })
      await Promise.race([proc.exited, timeout])
      clearTimeout(timer)
    } catch (error) {
      console.error("ExecWeave OpenCode plugin warning:", error)
    }
  }

  return {
    event: async ({ event }) => {
      await emit({
        hook_event_name: "event",
        event_type: event?.type,
        sessionID: sessionIDFrom(event),
        event,
      })
    },
    "chat.message": async (input, output) => {
      await emit({ hook_event_name: "chat.message", ...input, message: output.message, parts: output.parts })
    },
    "chat.params": async (input, output) => {
      await emit({ hook_event_name: "chat.params", ...input, params: output })
    },
    "chat.headers": async (input, output) => {
      await emit({ hook_event_name: "chat.headers", ...input, headers: withoutTransportCredentials(output.headers) })
    },
    "tool.execute.before": async (input, output) => {
      await emit({ hook_event_name: "tool.execute.before", ...input, args: output.args })
    },
    "tool.execute.after": async (input, output) => {
      await emit({ hook_event_name: "tool.execute.after", ...input, args: input.args, result: output })
    },
    "command.execute.before": async (input, output) => {
      await emit({ hook_event_name: "command.execute.before", ...input, command_parts: output.parts })
    },
    "permission.ask": async (input, output) => {
      await emit({ hook_event_name: "permission.ask", sessionID: sessionIDFrom(input), permission: input, decision: output.status })
    },
    "tool.definition": async (input, output) => {
      await emit({ hook_event_name: "tool.definition", ...input, description: output.description, parameters: output.parameters })
    },
    "experimental.chat.messages.transform": async (_input, output) => {
      await emit({ hook_event_name: "experimental.chat.messages.transform", sessionID: sessionIDFrom(output.messages), messages: output.messages })
    },
    "experimental.chat.system.transform": async (input, output) => {
      await emit({ hook_event_name: "experimental.chat.system.transform", ...input, system: output.system })
    },
    "experimental.session.compacting": async (input, output) => {
      await emit({ hook_event_name: "experimental.session.compacting", ...input, context: output.context, prompt: output.prompt })
    },
    "experimental.text.complete": async (input, output) => {
      await emit({ hook_event_name: "experimental.text.complete", ...input, text: output.text })
    },
  }
}
'''


def plugin_text(command: tuple[str, ...] = ("execweave-opencode-hook",)) -> str:
    rendered_command = json.dumps(list(command))
    marker = 'Bun.spawn(["execweave-opencode-hook"], {'
    return _PLUGIN.replace(marker, f"Bun.spawn({rendered_command}, {{", 1)


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
