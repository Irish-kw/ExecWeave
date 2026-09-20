"""Real worker sampling and lifecycle checks; not full product acceptance."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time

from test_pytest_diagnostic_runner import RUNNER, run


def load_runner():
    spec = importlib.util.spec_from_file_location("stack_sampling_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scheduled_sampling_covers_tests_without_serializing_locals(tmp_path):
    source = ("import time\n"
              "def test_sampled():\n"
              "    private_value = 'NEVER_SERIALIZE_THIS_LOCAL_7541'\n"
              "    time.sleep(.25)\n"
              "    assert private_value\n")
    result, out = run(tmp_path, source, interval=.02)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((out / 'stack-sampling.json').read_text())
    assert report['mode'] == 'cooperative_faulthandler'
    assert report['state'] == 'stopped' and report['error_type'] is None
    assert report['samples'] >= 2
    stacks = (out / 'stacks.txt').read_text()
    assert 'test_sampled' in stacks
    assert 'NEVER_SERIALIZE_THIS_LOCAL_7541' not in stacks
    invocation = json.loads((out / 'invocation.json').read_text())
    assert invocation['stack_sampling']['mode'] == report['mode']
    assert 'GIL-held native stall' in invocation['stack_sampling']['limitation']
    assert invocation['acceptance'] is False


def test_pytest_timer_cancellation_does_not_silence_sampling(tmp_path):
    source = ("import faulthandler, time\n"
              "def test_cancels_other_timer():\n"
              "    faulthandler.cancel_dump_traceback_later()\n"
              "    time.sleep(.25)\n")
    result, out = run(tmp_path, source, interval=.02)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'test_cancels_other_timer' in (out / 'stacks.txt').read_text()
    assert json.loads((out / 'stack-sampling.json').read_text())['state'] == 'stopped'


def test_sampler_does_not_replace_or_cancel_an_existing_native_timer(tmp_path):
    script = tmp_path / 'timer_owner.py'
    native = tmp_path / 'native.txt'
    sampled = tmp_path / 'sampled.txt'
    script.write_text(
        "import faulthandler, importlib.util, pathlib, time\n"
        f"spec = importlib.util.spec_from_file_location('runner', {str(RUNNER)!r})\n"
        "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
        f"with open({str(native)!r}, 'w') as original, open({str(sampled)!r}, 'w') as output:\n"
        "    faulthandler.dump_traceback_later(.5, file=original)\n"
        f"    sampler = module.StackSampler(pathlib.Path({str(tmp_path)!r}), output, .02)\n"
        "    sampler.start(); time.sleep(.1); sampler.close()\n"
        "    time.sleep(.65)\n"
        "    faulthandler.cancel_dump_traceback_later()\n",
        encoding='utf-8',
    )
    result = subprocess.run([sys.executable, str(script)], capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert 'Timeout' in native.read_text()
    assert 'timer_owner.py' in sampled.read_text()


def test_closed_output_is_reported_and_sampler_joins_before_return(tmp_path):
    module = load_runner()
    stream = (tmp_path / 'stacks.txt').open('w')
    stream.close()
    sampler = module.StackSampler(tmp_path, stream, .01)
    sampler.start()
    sampler.thread.join(timeout=2)
    assert not sampler.thread.is_alive()
    sampler.close()
    report = json.loads((tmp_path / 'stack-sampling.json').read_text())
    assert report['state'] == 'failed'
    assert report['error_type'] == 'ValueError' and report['samples'] == 0


def test_close_stops_writes_before_the_output_is_closed(tmp_path):
    module = load_runner()
    path = tmp_path / 'stacks.txt'
    with path.open('w') as stream:
        sampler = module.StackSampler(tmp_path, stream, .01)
        sampler.start()
        deadline = time.monotonic() + 2
        while not sampler.samples and time.monotonic() < deadline:
            time.sleep(.01)
        sampler.close()
        assert sampler.samples > 0 and not sampler.thread.is_alive()
    before = path.read_bytes()
    time.sleep(.05)
    assert path.read_bytes() == before


def test_sampling_failure_cannot_be_reported_as_a_successful_diagnostic(tmp_path):
    # Deliberately break the observer's real output stream, without replacing
    # faulthandler or pytest. The passing test and failed diagnostic are distinct.
    source = ("import threading, time\n"
              "def test_observer_failure():\n"
              "    found = False\n"
              "    for thread in threading.enumerate():\n"
              "        owner = getattr(getattr(thread, '_target', None), '__self__', None)\n"
              "        if type(owner).__name__ == 'StackSampler':\n"
              "            owner.stream.close()\n"
              "            found = True\n"
              "    assert found\n"
              "    time.sleep(.2)\n")
    result, out = run(tmp_path, source, interval=.02)
    assert result.returncode == 2
    summary = json.loads((out / 'summary.json').read_text())
    assert summary['state'] == 'failed' and summary['session_exit_code'] == 0
    assert summary['acceptance'] is False
    assert json.loads((out / 'stack-sampling.json').read_text())['state'] == 'failed'
    assert json.loads((out / 'worker-result.json').read_text()) == {
        'exit_code': 2, 'pytest_exit_code': 0,
    }
