from pathlib import Path

path = Path("src/execweave/auto_specialized.py")
text = path.read_text(encoding="utf-8")
old = '''    listen_host, listen_port = listen_address
    internal_port = _allocate_loopback_port()
    upstream = f"http://127.0.0.1:{internal_port}"
'''
new = '''    listen_host, listen_port = listen_address
    public_endpoint = f"http://{listen_host}:{listen_port}"
    try:
        existing = _get_json(
            f"{public_endpoint}/api/ps",
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except _PROBE_ERRORS:
        existing = None
    if isinstance(existing, dict) and isinstance(existing.get("models"), list):
        print(
            "ExecWeave Ollama relay: existing Ollama server detected at "
            f"{public_endpoint}; leaving that server unclaimed.",
            file=sys.stderr,
        )
        yield environment
        return

    internal_port = _allocate_loopback_port()
    upstream = f"http://127.0.0.1:{internal_port}"
'''
if text.count(old) != 1:
    raise SystemExit(f"guarded replacement count: {text.count(old)}")
text = text.replace(old, new, 1)
text = text.replace(
    '''    if server is None:
        public_endpoint = f"http://{listen_host}:{listen_port}"
        raise RuntimeError(''',
    '''    if server is None:
        raise RuntimeError(''',
    1,
)
path.write_text(text, encoding="utf-8")
