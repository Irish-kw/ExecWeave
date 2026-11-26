"""Per-call execution lanes (Linux, root).

A root launcher starts every routed shell call in its own cgroup v2 lane and records the
binding of call id to lane in a hash-chained, Ed25519-signed ledger.  A root eBPF sensor
(bpftrace) stamps each recorded event with the cgroup id of the acting task, and the
auditor attributes events to calls by cgroup-id equality with the ledger.

Modules:
  service        the launcher (Unix-socket protocol, ledger, delegation grants, call isolation)
  exec_client    the launch client that a harness hook or shell shim runs for each call
  backend        the auditor: sensor log + ledger -> ExecWeave event stream and lane attribution
  sensor_nonce   per-run record nonce for the sensor log
  sensor_guard   start/end canary that checks that the sensor observes every CPU
  runner         one recorded session: cgroup mount, sensor, launcher, command, audit
  hooks          harness integrations (Claude Code, Cursor, Antigravity, Codex shell shim)
"""
