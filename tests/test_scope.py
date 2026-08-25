from pathlib import Path

from execweave.scope import protect_filesystem_scope


def test_broad_home_scope_disables_filesystem_collection() -> None:
    decision = protect_filesystem_scope(
        Path.home(),
        collect_filesystem=True,
        warn=False,
    )

    assert decision.broad_scope is True
    assert decision.collect_filesystem is False
    assert decision.reason is not None
    assert "disabled recursive filesystem observation" in decision.reason


def test_broad_scope_can_be_explicitly_allowed() -> None:
    decision = protect_filesystem_scope(
        Path.home(),
        collect_filesystem=True,
        allow_broad_scope=True,
        warn=False,
    )

    assert decision.broad_scope is True
    assert decision.collect_filesystem is True
    assert decision.reason is None


def test_project_scope_preserves_filesystem_collection(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    decision = protect_filesystem_scope(
        project,
        collect_filesystem=True,
        warn=False,
    )

    assert decision.broad_scope is False
    assert decision.collect_filesystem is True
    assert decision.watch_root == project.resolve()


def test_disabled_filesystem_collection_stays_disabled(tmp_path: Path) -> None:
    decision = protect_filesystem_scope(
        tmp_path,
        collect_filesystem=False,
        warn=False,
    )

    assert decision.collect_filesystem is False
