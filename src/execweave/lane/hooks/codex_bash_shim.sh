#!/run/ewreal/bash.real
# Shell shim for per-call lane binding of Codex shell commands (hooks of Codex 0.164 need an interactive trust step).
# Bind-mounted over /usr/bin/bash inside the experiment's private mount namespace only.  Acts only for `bash -c CMD` / `bash -lc CMD` invocations whose environment
# carries EW_CODEX_LANE (set for the Codex process by the runner) and not EW_IN_LANE (set inside a lane): the command is then run through the lane
# launcher as its own call lane, with the same output streams; everything else goes to the real bash unchanged.
if [ -n "${EW_CODEX_LANE:-}" ] && [ -z "${EW_IN_LANE:-}" ] && { [ "${1:-}" = "-lc" ] || [ "${1:-}" = "-c" ]; } && [ "$#" -eq 2 ]; then
  # the lane call id carries Codex's own per-call id (CODEX_TOOL_CALL_ID, set by the harness in the environment of the process it spawns, i.e. this
  # shim, before any command text runs) as a prefix, plus a unique suffix because one tool call may start more than one shell
  nid="${CODEX_TOOL_CALL_ID:-}"
  case "$nid" in *[!A-Za-z0-9_:-]*) nid="" ;; esac
  id="${nid:+$nid.}cx$(/usr/bin/date +%s%N)p$$"
  exec /usr/bin/python3 "$EW_LANE_EXEC" --sock "$EW_LANE_SOCK" --call-id "$id" -- /run/ewreal/bash.real "$1" "export EW_IN_LANE=1; $2"
fi
exec /run/ewreal/bash.real "$@"
