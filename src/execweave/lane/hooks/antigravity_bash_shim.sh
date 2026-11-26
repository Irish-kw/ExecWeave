#!/usr/bin/bash
# `bash` shim for the Antigravity CLI (agy).  agy starts every run_command as `bash -c '<CommandLine>'`, looking `bash` up through PATH (verified, see
# cli_facts/agy.md), and sets ANTIGRAVITY_SOURCE_METADATA={"tool":{"conversationId":..,"stepIndex":N,"toolCall":{"id":"call_N",..}}} for it.
# Install a copy of this file as <dir>/bash (mode 0755: the wheel ships it without the executable bit, so its bytes are
# the same on every OS) and put <dir> first in the PATH of the agy process.  Modes (EW_AGY_SHIM_MODE):
#   log   (default) append one JSON line (argv[1..2] shortened, call id and agy's own tool-call id parsed from the metadata) to $EW_AGY_SHIM_LOG and run the real bash unchanged
#   lane  run `bash -c CMD` of a tool call through the lane launcher as its own call lane (call id <conversationId>:<stepIndex>, the same id the hook uses);
#         invocations without tool metadata, nested ones (EW_IN_LANE) and commands that already start with lane_exec are passed through unchanged
REAL=/usr/bin/bash
mode="${EW_AGY_SHIM_MODE:-log}"
meta="${ANTIGRAVITY_SOURCE_METADATA:-}"
cid=""; native=""
if [ -n "$meta" ] && [ "${1:-}" = "-c" ]; then
  parsed="$(META="$meta" /usr/bin/python3 -c 'import json,os,re
try:
    t=json.loads(os.environ["META"])["tool"]
    s="%s:%s" % (t["conversationId"], t["stepIndex"])
    n=str((t.get("toolCall") or {}).get("id") or "")
    print((s if re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", s) else "") + " " + (n if re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", n) else "-"))
except Exception:
    print("- -")' 2>/dev/null)"
  cid="${parsed%% *}"; native="${parsed##* }"
  [ "$cid" = "-" ] && cid=""
  [ "$native" = "-" ] && native=""
fi
if [ "$mode" = "log" ] && [ -n "${EW_AGY_SHIM_LOG:-}" ]; then
  /usr/bin/python3 -c 'import json,sys,time
print(json.dumps({"t_ns": time.time_ns(), "pid": int(sys.argv[1]), "ppid": int(sys.argv[2]), "argc": int(sys.argv[3]), "argv1": sys.argv[4], "argv2": sys.argv[5][:200], "call_id": sys.argv[6], "native_call_id": sys.argv[7]}))' "$$" "$PPID" "$#" "${1:-}" "${2:-}" "$cid" "$native" >> "$EW_AGY_SHIM_LOG" 2>/dev/null
fi
if [ "$mode" = "lane" ] && [ -n "$cid" ] && [ -z "${EW_IN_LANE:-}" ] && [ "$#" -eq 2 ]; then
  case "$2" in *lane_exec.py*|*stub_lane_exec.py*) exec "$REAL" "$@" ;; esac
  exec /usr/bin/python3 "$EW_LANE_EXEC" --sock "$EW_LANE_SOCK" --call-id "$cid" --declared "agy-shim" -- "$REAL" -c "export EW_IN_LANE=1; export EW_TOOL_CALL_ID=$cid; $2"
fi
exec "$REAL" "$@"
