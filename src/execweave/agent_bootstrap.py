from __future__ import annotations

import json
import os
import stat
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

_AUTO_FLAG = "--auto"
_CONFIG_RETRIES = 3
_SUPPORTED_AGENTS = {"claude", "codex", "gemini", "cursor", "opencode"}


@dataclass(frozen=True)
class AgentBootstrapResult:
    provider: str | None
    status: str
    path: str | None = None
    changed: bool = False
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _command_name(value: str) -> str:
    name = value.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def supported_agent(command: list[str]) -> str | None:
    if not command:
        return None
    name = _command_name(command[0])
    return name if name in _SUPPORTED_AGENTS else None


def _bounded_detail(value: object, limit: int = 240) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _load_json_object(raw: bytes, *, path: Path) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"configuration root must be an object: {path}")
    return payload


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _contains_execweave_command(value: object, marker: str) -> bool:
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str) and marker in command:
            return True
        return any(_contains_execweave_command(child, marker) for child in value.values())
    if isinstance(value, list):
        return any(_contains_execweave_command(child, marker) for child in value)
    return False


def _merge_hook_fragment(
    current: dict[str, Any],
    fragment: dict[str, Any],
    *,
    marker: str,
) -> tuple[dict[str, Any], bool]:
    merged = deepcopy(current)
    changed = False

    for key, value in fragment.items():
        if key == "hooks":
            continue
        if key not in merged:
            merged[key] = deepcopy(value)
            changed = True

    incoming_hooks = fragment.get("hooks")
    if not isinstance(incoming_hooks, dict):
        raise ValueError("ExecWeave hook fragment has no hooks object")

    existing_hooks = merged.get("hooks")
    if existing_hooks is None:
        existing_hooks = {}
        merged["hooks"] = existing_hooks
        changed = True
    if not isinstance(existing_hooks, dict):
        raise ValueError("existing hooks value is not an object")

    for event_name, incoming_groups in incoming_hooks.items():
        if not isinstance(incoming_groups, list):
            raise ValueError(f"ExecWeave hook event is not a list: {event_name}")
        existing_groups = existing_hooks.get(event_name)
        if existing_groups is None:
            existing_hooks[event_name] = deepcopy(incoming_groups)
            changed = True
            continue
        if not isinstance(existing_groups, list):
            raise ValueError(f"existing hook event is not a list: {event_name}")
        if _contains_execweave_command(existing_groups, marker):
            continue
        existing_groups.extend(deepcopy(incoming_groups))
        changed = True

    return merged, changed


def _write_bytes_optimistic(path: Path, original: bytes | None, payload: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = _read_bytes(path)
    if current != original:
        return False

    mode = None
    if path.exists():
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            mode = None

    temporary = path.with_name(f".{path.name}.execweave-{os.getpid()}.tmp")
    try:
        temporary.write_bytes(payload)
        if mode is not None:
            try:
                temporary.chmod(mode)
            except OSError:
                pass
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return True


def _merge_json_file(path: Path, fragment: dict[str, Any], *, marker: str) -> bool:
    for _ in range(_CONFIG_RETRIES):
        original = _read_bytes(path)
        current = _load_json_object(original or b"", path=path)
        merged, changed = _merge_hook_fragment(current, fragment, marker=marker)
        if not changed:
            return False
        encoded = (
            json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if _write_bytes_optimistic(path, original, encoded):
            return True
    raise RuntimeError(f"configuration changed concurrently while updating {path}")


def _write_plugin_file(path: Path, content: str, *, marker: str) -> bool:
    encoded = content.encode("utf-8")
    for _ in range(_CONFIG_RETRIES):
        original = _read_bytes(path)
        if original is not None:
            try:
                existing = original.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"existing OpenCode plugin is not UTF-8: {path}") from exc
            if existing == content or marker in existing:
                return False
            raise FileExistsError(f"refusing to replace existing OpenCode plugin: {path}")
        if _write_bytes_optimistic(path, original, encoded):
            return True
    raise RuntimeError(f"plugin path changed concurrently while updating {path}")


def _config_dir_from_env(environment: Mapping[str, str], key: str) -> Path | None:
    raw = environment.get(key, "").strip()
    return Path(raw).expanduser() if raw else None


def _provider_target(
    provider: str,
    *,
    home: Path,
    environment: Mapping[str, str],
) -> Path:
    if provider == "claude":
        root = _config_dir_from_env(environment, "CLAUDE_CONFIG_DIR") or home / ".claude"
        return root / "settings.json"
    if provider == "codex":
        root = _config_dir_from_env(environment, "CODEX_HOME") or home / ".codex"
        return root / "hooks.json"
    if provider == "gemini":
        return home / ".gemini" / "settings.json"
    if provider == "cursor":
        return home / ".cursor" / "hooks.json"
    if provider == "opencode":
        root = _config_dir_from_env(environment, "XDG_CONFIG_HOME") or home / ".config"
        return root / "opencode" / "plugins" / "execweave.ts"
    raise ValueError(f"unsupported provider: {provider}")


def _provider_fragment(provider: str) -> tuple[dict[str, Any], str]:
    if provider == "claude":
        from .claude_hook_cli import claude_hook_config

        return claude_hook_config(f"execweave-claude-hook {_AUTO_FLAG}"), "execweave-claude-hook"
    if provider == "codex":
        from .codex_hook_cli import codex_hook_config

        return codex_hook_config(f"execweave-codex-hook {_AUTO_FLAG}"), "execweave-codex-hook"
    if provider == "gemini":
        from .gemini_hook_cli import gemini_hook_config

        return gemini_hook_config(f"execweave-gemini-hook {_AUTO_FLAG}"), "execweave-gemini-hook"
    if provider == "cursor":
        from .cursor_hook_cli import cursor_hook_config

        return cursor_hook_config(f"execweave-cursor-hook {_AUTO_FLAG}"), "execweave-cursor-hook"
    raise ValueError(f"provider does not use JSON hooks: {provider}")


def bootstrap_supported_agent(
    command: list[str],
    *,
    home: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> AgentBootstrapResult:
    provider = supported_agent(command)
    if provider is None:
        command_name = _command_name(command[0]) if command else "unknown"
        return AgentBootstrapResult(
            provider=None,
            status="unavailable",
            detail=f"no specialized lifecycle integration for {command_name}",
        )

    env = os.environ if environment is None else environment
    home_path = Path.home() if home is None else Path(home).expanduser()
    target = _provider_target(provider, home=home_path, environment=env)

    try:
        if provider == "opencode":
            from .opencode_plugin_cli import plugin_text

            content = plugin_text(("execweave-opencode-hook", _AUTO_FLAG))
            changed = _write_plugin_file(target, content, marker="execweave-opencode-hook")
        else:
            fragment, marker = _provider_fragment(provider)
            changed = _merge_json_file(target, fragment, marker=marker)

        if provider == "claude":
            raw = _read_bytes(target)
            payload = _load_json_object(raw or b"", path=target)
            if payload.get("disableAllHooks") is True:
                return AgentBootstrapResult(
                    provider=provider,
                    status="unavailable",
                    path=str(target),
                    changed=changed,
                    detail="Claude hooks are disabled by disableAllHooks",
                )

        return AgentBootstrapResult(
            provider=provider,
            status="active",
            path=str(target),
            changed=changed,
            detail="specialized hook/plugin bootstrap is configured",
        )
    except (FileExistsError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return AgentBootstrapResult(
            provider=provider,
            status="bootstrap_failed",
            path=str(target),
            changed=False,
            detail=_bounded_detail(exc),
        )
