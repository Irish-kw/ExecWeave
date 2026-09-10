"""Exercise release job dependencies and both supported CI interpreter paths."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = {"ubuntu-latest", "windows-latest", "macos-latest"}


def _workflow(name: str) -> dict:
    value = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict) and isinstance(value.get("jobs"), dict)
    return value


def _needs(job: dict) -> set[str]:
    value = job.get("needs", [])
    return {value} if isinstance(value, str) else set(value)


def _assert_browser_job(document: dict, job: dict, install_name: str) -> None:
    env = {**document.get("env", {}), **job.get("env", {})}
    assert str(env.get("EXECWEAVE_E2E_REQUIRED")) == "1", "required browser mode missing"
    assert not job.get("continue-on-error"), "job can ignore failure"
    assert "if" not in job, "required job is conditional"
    steps = job["steps"]
    install = next(step for step in steps if step.get("name") == install_name)
    commands = install.get("run", "")
    extras = re.search(r'pip install -e [\'\"]\.\[([^]]+)\][\'\"]', commands)
    assert extras and {"dev", "e2e"} <= set(extras[1].split(",")), "browser dependencies missing"
    assert "python -m playwright install --with-deps chromium" in commands, "Chromium missing"
    tests = [step for step in steps if "-m pytest" in step.get("run", "")]
    assert tests, "pytest command missing"
    for step in (install, *tests):
        assert not step.get("continue-on-error"), "step can ignore failure"
        assert "if" not in step, "required step is conditional"
        effective_env = {**env, **step.get("env", {})}
        assert str(effective_env.get("EXECWEAVE_E2E_REQUIRED")) == "1", "browser mode disabled"
    assert any("xvfb-run -a" in step["run"] for step in tests), "Linux display not provisioned"


def _assert_publish_gate(document: dict) -> None:
    jobs = document["jobs"]
    minimum = jobs["minimum-python"]
    assert set(minimum["strategy"]["matrix"]["os"]) == SYSTEMS, "minimum OS coverage incomplete"
    assert minimum["strategy"]["fail-fast"] is False, "minimum matrix may cancel peers"
    setup = next(step for step in minimum["steps"] if step.get("uses", "").startswith("actions/setup-python@"))
    assert str(setup["with"]["python-version"]) == "3.10", "minimum interpreter missing"
    checkout = next(step for step in minimum["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ env.RELEASE_TAG }}", "minimum job tests wrong ref"
    _assert_browser_job(document, minimum, "Install minimum-version verification dependencies")
    assert _needs(jobs["compare-distributions"]) == {"verify", "minimum-python"}, "minimum gate disconnected"
    assert _needs(jobs["publish"]) == {"compare-distributions"}, "publish bypasses comparison"
    assert _needs(jobs["release-assets"]) == {"compare-distributions", "publish"}
    for name in ("compare-distributions", "publish", "release-assets"):
        assert "if" not in jobs[name], "publish dependency can bypass failure"
        assert not jobs[name].get("continue-on-error"), "publish dependency ignores failure"


@pytest.mark.parametrize(
    "event,ref,changed,full,expected_versions",
    [
        ("pull_request", "refs/pull/82/merge", "tests/test_gate.py", "", {"3.10", "3.12"}),
        ("pull_request", "refs/pull/82/merge", "pyproject.toml", "", {"3.10", "3.12"}),
        ("push", "refs/heads/main", "src/execweave/entry.py", "", {"3.10", "3.12"}),
        ("push", "refs/tags/v9.9.9", "README.md", "", {"3.10", "3.12"}),
        ("workflow_dispatch", "refs/heads/main", "README.md", "true", {"3.10", "3.12"}),
        ("pull_request", "refs/pull/82/merge", "README.md", "", {"3.12"}),
    ],
)
def test_cross_platform_ci_covers_minimum_supported_python_on_all_three_os(
    tmp_path: Path, event: str, ref: str, changed: str, full: str, expected_versions: set[str]
) -> None:
    # Execute the actual workflow planner. Only git's changed-file list is supplied
    # independently; expectations never come from the generated matrix.
    plan = _workflow("ci.yml")["jobs"]["plan"]
    script = next(step["run"] for step in plan["steps"] if step.get("id") == "matrix")
    code = script.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    output = tmp_path / "github-output"
    runner = (
        "from unittest.mock import patch\n"
        f"with patch('subprocess.check_output', return_value={changed + chr(10)!r}):\n"
        f"    exec({code!r})\n"
    )
    env = {**os.environ, "EVENT_NAME": event, "REF_NAME": ref, "FULL_MATRIX": full,
           "BASE_SHA": "base", "BEFORE_SHA": "base", "CURRENT_SHA": "head",
           "GITHUB_OUTPUT": str(output)}
    result = subprocess.run([sys.executable, "-c", runner], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    matrix = json.loads(values["matrix"])["include"]
    systems = SYSTEMS if len(expected_versions) == 2 else {"ubuntu-latest"}
    assert {(item["os"], item["python-version"]) for item in matrix} == {
        (system, version) for system in systems for version in expected_versions
    }
    assert len(matrix) == len(systems) * len(expected_versions)


def test_publish_blocks_distribution_comparison_on_three_os_python310_gate() -> None:
    _assert_publish_gate(_workflow("publish.yml"))


def test_ci_executes_required_browsers_before_merge_not_only_after_tag() -> None:
    document = _workflow("ci.yml")
    _assert_browser_job(document, document["jobs"]["test"], "Install")


def test_python310_tomllib_backport_is_declared_for_test_and_release_tooling() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for extra in ("dev", "release"):
        requirements = [Requirement(item) for item in project["project"]["optional-dependencies"][extra]]
        backport = next(item for item in requirements if item.name == "tomli")
        assert backport.marker is not None
        assert backport.marker.evaluate({"python_version": "3.10"})
        assert not backport.marker.evaluate({"python_version": "3.12"})


@pytest.mark.parametrize("mutation,reason", [
    ("dependency", "minimum gate disconnected"),
    ("extras", "browser dependencies missing"),
    ("chromium", "Chromium missing"),
    ("required", "required browser mode missing"),
    ("job_failure", "job can ignore failure"),
    ("publish_always", "bypass failure"),
    ("os", "minimum OS coverage incomplete"),
])
def test_publish_gate_mutations_are_rejected(mutation: str, reason: str) -> None:
    document = copy.deepcopy(_workflow("publish.yml"))
    jobs = document["jobs"]
    minimum = jobs["minimum-python"]
    install = next(step for step in minimum["steps"] if step.get("name") == "Install minimum-version verification dependencies")
    if mutation == "dependency":
        jobs["compare-distributions"]["needs"] = ["verify"]
    elif mutation == "extras":
        install["run"] = install["run"].replace("[dev,e2e,release]", "[dev]")
    elif mutation == "chromium":
        install["run"] = install["run"].replace("python -m playwright install --with-deps chromium", "")
    elif mutation == "required":
        minimum["env"] = {"EXECWEAVE_E2E_REQUIRED": "0"}
    elif mutation == "job_failure":
        minimum["continue-on-error"] = True
    elif mutation == "publish_always":
        jobs["compare-distributions"]["if"] = "always()"
    elif mutation == "os":
        minimum["strategy"]["matrix"]["os"] = ["ubuntu-latest"]
    with pytest.raises(AssertionError, match=reason):
        _assert_publish_gate(document)


@pytest.mark.parametrize("path", [
    "tests/test_release_publish_safety.py",
    "tests/test_codex_hook_global_fail_open.py",
    "scripts/check_wheel_install.py",
    "scripts/check_sdist_install.py",
    "scripts/check_distribution_contents.py",
])
def test_toml_imports_work_in_fresh_process_without_pytest_bootstrap(path: str) -> None:
    runner = (
        "import runpy, sys\n"
        f"module = runpy.run_path({str(ROOT / path)!r})\n"
        "assert module['tomllib'].loads('answer = 42')['answer'] == 42\n"
        "if sys.version_info < (3, 11):\n"
        "    assert 'tomllib' not in sys.modules, 'global TOML import was masked'\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run([sys.executable, "-c", runner], cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_stage_test_allowance_still_rejects_unrelated_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    path = ROOT / "scripts/_check_release_stage_integrity_impl.py"
    spec = importlib.util.spec_from_file_location("pr82_integrity_probe", path)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker, "_git", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 0, "M\ttests/test_graph.py\n", ""
    ))
    with pytest.raises(RuntimeError, match="tests/test_graph.py"):
        checker._assert_existing_tests_untouched("baseline", {
            "tests/test_release_publish_safety.py": "minimum-Python dependency assertion",
            "tests/test_codex_hook_global_fail_open.py": "local TOML backport import",
        })
