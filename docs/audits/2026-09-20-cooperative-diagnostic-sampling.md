# Diagnostic stack sampling without the global native timer

Baseline: `54e13653d4b2d7ec2c0ff276f8bb971e94e24c09`.
Scope: one diagnostic script, six new tests, and this record. Product source,
existing tests, workflow definitions, dependencies and version are unchanged.

## Observed failure and isolated comparison

I reproduced the previously reported worker exit -11 with the unchanged runner:
11 of its 12 tests passed; the descendant-deadline test failed because its worker
exited -11 before collection. Its progress log was empty and the native timer's
stack output stopped halfway through a pathlib frame. This is a local
Linux/Python 3.13.5 observation, not a reproduction of Windows cancellation.

A separate subprocess probe imported and enumerated `importlib.metadata`, with
no ExecWeave import or pytest session. With a 10 ms repeated native
`dump_traceback_later` timer, two of five processes exited -11. With a scheduled
Python thread calling `dump_traceback` synchronously at the same interval, all
five exited zero and produced stack output. This isolates a diagnostic path in
this runtime; it does not identify an upstream defect, establish a universal
crash rate, or explain every earlier failed job. The probe and original logs
are retained in the validation bundle, not installed as product code.

## Change and limitations

The runner now invokes native `faulthandler.dump_traceback(all_threads=True)`
from a cooperative Python thread. It no longer arms or cancels the process-wide
`dump_traceback_later` timer, leaving that timer available to pytest or tests.
On normal completion it signals and joins the sampler before closing its file.
Output errors are recorded by exception type without locals or exception text.
A passing pytest session with a failed sampler returns diagnostic exit 2 rather
than being reported as a successful diagnostic; pytest's own result is retained.

`invocation.json` declares the sampling mode and limitation. The separate
`stack-sampling.json` is a startup/stopped/failed status record: counts in its
initial `running` record are not a final sample count after forced termination.
The flushed `stacks.txt` remains the actual partial evidence at a deadline.

**This sampler requires Python thread scheduling.** A native extension holding
the GIL can prevent samples. A missing sample is not evidence of no deadlock.
The separate supervisor still enforces its unchanged deadline, preserves the
progress journal, inventories only its worker/descendants, and returns 124 on
expiry. It does not require the worker's sampler thread to remain responsive.
The observer does not replace pytest's fatal-signal handling, alter selection or
ordering, retry a crashed worker, or convert missing evidence into acceptance.

API background: Python's documentation distinguishes the watchdog-thread
`dump_traceback_later` API from direct `dump_traceback` calls:
https://docs.python.org/3.13/library/faulthandler.html
The thread-scheduling limitation is consistent with Python's GIL description:
https://docs.python.org/3.13/library/threading.html
These documents establish API semantics, not the cause of the observed -11.

## Executed checks

- Unchanged baseline runner module: **11 passed, 1 failed** (worker -11).
- Initial repaired runner module: **12 passed**.
- Initial five new sampling checks: **5 passed**.
- Final source, original deadline cases: **2 passed, 10 deselected**.
- Final source, other original cases and all six new checks: **16 passed,
  2 deselected**.
- The final two groups cover **18 distinct checks**, with no case omitted across
  the groups. Earlier executions and standalone probe trials are not added to
  this total. Existing test source and time limits were not changed.
- Ruff, Python compilation, diff whitespace and exact source-tree comparison
  are checked before upload.

One combined attempt hit the command execution deadline before a completed
JUnit result. It also recorded a deadline case that stopped during plugin
imports before any test started. That incomplete attempt is retained and is
**not** a passing combined suite. Splitting the two later invocations is explicit;
these results do not prove order-independent timing or native Windows behavior.
I did not disable plugin autoload or increase the original three-second fixture
budget to hide this timing limitation.

The six new checks cover real stack output with no local-variable values,
sampling after another timer is cancelled, preserving another native timer,
closed-output errors, sampler shutdown before file close, and a passing test
with an explicitly failed observer. The fault-injection case closes the actual
sampler output; it does not replace pytest, faulthandler or process APIs.

Local runtime: Linux, Python 3.13.5, pytest 9.0.2, psutil 7.2.2. Ruff was installed
from an existing mounted wheel; no repository dependency changed. The exact
baseline was rebuilt from the fc3184e Actions bundle plus validated 02f3bd3 and
54e1365 file snapshots; its tree matched
`45c3fcff6860d3ef97ae3d7bfe88676eb16fd3c2` before editing.

## Acceptance and rollback

Native current-head CI must independently validate this tooling. The unfinished
54e1365 Windows matrix and the earlier cancellations are not relabeled as passed.
The product's R2/R3 replay and three-OS browser evidence retain their original
fixed-candidate scope. No fresh provider or full product test was run here.

Revert this commit to restore the former diagnostic timer; captured product
evidence needs no migration. The historical diagnostic workflow remains manual
and pinned to its original product candidate. No main update, merge, tag or
publication is part of this change. The PR remains draft.
