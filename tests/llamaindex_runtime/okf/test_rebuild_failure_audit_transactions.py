"""No-database regression coverage for rebuild primary-connection cleanup."""

from __future__ import annotations

import pytest

from ._rebuild_failure_audit_testkit import (
    _admitted,
    _assert_primary_seams_unused,
    _AuditConnection,
    _Cursor,
    _document,
    _load_module,
    _primary_factory,
    _StateConnection,
)


@pytest.mark.parametrize(
    ("rollback_error", "audited"),
    [(False, True), (True, False)],
    ids=("body-rollback-success", "body-rollback-failure"),
)
def test_body_failure_requires_one_direct_rollback_close_then_optional_audit(
    monkeypatch: pytest.MonkeyPatch, rollback_error: bool, audited: bool
) -> None:
    module = _load_module()
    events: list[str] = []
    primary = _StateConnection(
        _Cursor([("expected",)]), events, rollback_error=rollback_error
    )
    audit = _AuditConnection(_Cursor([("expected",)]), events)
    body_failure = ValueError("body failure")
    monkeypatch.setattr(
        module,
        "_rebuild_admitted_document",
        lambda *_: (_ for _ in ()).throw(body_failure),
    )

    with pytest.raises(ValueError) as captured:
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=_primary_factory(primary, audit),
        )

    assert captured.value is body_failure
    assert primary.connect_count == primary.rollback_count == primary.close_count == 1
    assert primary.commit_count == 0
    assert primary.audit_count == int(audited)
    assert events == ["connect", "rollback", "close"]
    assert (audit.cursor_value.executed != []) is audited
    _assert_primary_seams_unused(primary)


def test_commit_failure_rolls_back_closes_and_audits_only_after_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    events: list[str] = []
    primary = _StateConnection(
        _Cursor([("expected",)]), events, commit_error=RuntimeError("commit failure")
    )
    audit = _AuditConnection(_Cursor([("expected",)]), events)
    monkeypatch.setattr(module, "_rebuild_admitted_document", lambda *_: 1)

    with pytest.raises(RuntimeError, match="commit failure"):
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=_primary_factory(primary, audit),
        )

    assert primary.connect_count == primary.commit_count == primary.rollback_count == 1
    assert primary.close_count == primary.audit_count == 1
    assert events == ["connect", "commit", "rollback", "close"]
    _assert_primary_seams_unused(primary)


def test_success_commits_then_closes_once_without_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    events: list[str] = []
    primary = _StateConnection(_Cursor([("expected",)]), events)
    monkeypatch.setattr(module, "_rebuild_admitted_document", lambda *_: 1)

    assert (
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=_primary_factory(primary, None),
        )
        == 1
    )
    assert primary.connect_count == primary.commit_count == primary.close_count == 1
    assert primary.rollback_count == primary.audit_count == 0
    assert events == ["connect", "commit", "close"]
    _assert_primary_seams_unused(primary)


def test_close_failure_after_rollback_preserves_primary_identity_without_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    events: list[str] = []
    body_failure = ValueError("body failure must survive close")
    primary = _StateConnection(
        _Cursor([("expected",)]), events, close_error=RuntimeError("close failure")
    )
    audit = _AuditConnection(_Cursor([("expected",)]), events)
    monkeypatch.setattr(
        module,
        "_rebuild_admitted_document",
        lambda *_: (_ for _ in ()).throw(body_failure),
    )

    with pytest.raises(ValueError) as captured:
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=_primary_factory(primary, audit),
        )

    assert captured.value is body_failure
    assert primary.rollback_count == primary.close_count == 1
    assert primary.audit_count == primary.commit_count == 0
    assert events == ["connect", "rollback", "close"]
    _assert_primary_seams_unused(primary)


def test_close_failure_after_commit_has_safe_outward_failure_no_rollback_or_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    events: list[str] = []
    primary = _StateConnection(
        _Cursor([("expected",)]), events, close_error=RuntimeError("close failure")
    )
    audit = _AuditConnection(_Cursor([("expected",)]), events)
    monkeypatch.setattr(module, "_rebuild_admitted_document", lambda *_: 1)

    with pytest.raises(module._PrimaryExitFailure) as captured:
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=_primary_factory(primary, audit),
        )

    assert (
        str(captured.value) == "Primary connection close failed after committed rebuild"
    )
    assert primary.connect_count == primary.commit_count == primary.close_count == 1
    assert primary.rollback_count == primary.audit_count == 0
    assert events == ["connect", "commit", "close"]
    _assert_primary_seams_unused(primary)


def test_close_failure_after_commit_preserves_commit_failure_without_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    events: list[str] = []
    commit_failure = RuntimeError("commit failure must survive close")
    primary = _StateConnection(
        _Cursor([("expected",)]),
        events,
        commit_error=commit_failure,
        close_error=RuntimeError("close failure"),
    )
    audit = _AuditConnection(_Cursor([("expected",)]), events)
    monkeypatch.setattr(module, "_rebuild_admitted_document", lambda *_: 1)

    with pytest.raises(RuntimeError) as captured:
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=_primary_factory(primary, audit),
        )

    assert captured.value is commit_failure
    assert primary.commit_count == primary.rollback_count == primary.close_count == 1
    assert primary.audit_count == 0
    assert events == ["connect", "commit", "rollback", "close"]
    _assert_primary_seams_unused(primary)


def test_factory_failure_never_closes_or_audits() -> None:
    module = _load_module()
    calls: list[str] = []

    def factory(_: str) -> object:
        calls.append("connect")
        raise RuntimeError("factory failure")

    with pytest.raises(RuntimeError, match="factory failure"):
        module._rebuild_admitted_bundle(
            _admitted(module, _document()),
            "ignored",
            "expected",
            connection_factory=factory,
        )

    assert calls == ["connect"]
