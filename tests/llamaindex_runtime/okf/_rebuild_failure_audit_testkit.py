"""Private fakes and builders for rebuild failure-audit tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Callable

from llamaindex_runtime.okf.parser import OKFDocument, OKFFrontmatter
from llamaindex_runtime.okf.sidecar import SpanRecord

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "rebuild_from_okf.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rebuild_failure_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _document(
    doc_id: str = "00000000-0000-0000-0000-000000000002",
    version_id: str = "00000000-0000-0000-0000-000000000001",
) -> OKFDocument:
    return OKFDocument(
        file_path=Path("raw/never-in-a-manifest.md"),
        frontmatter=OKFFrontmatter(type="raw", doc_id=doc_id, version_id=version_id),
        body="must never persist",
        spans=(
            SpanRecord("00000000-0000-0000-0000-000000000003", None, (), 0, "text"),
        ),
        canonical_hash="a" * 64,
    )


def _admitted(module: ModuleType, *documents: OKFDocument) -> object:
    return module._AdmittedBundle(
        tuple(module._freeze_raw_document(document) for document in documents)
    )


class _Cursor:
    def __init__(
        self, results: list[tuple[object, ...]] | None = None, fail: bool = False
    ) -> None:
        self.results = list(results or [])
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []
        self.fail = fail

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, parameters: tuple[object, ...] | None = None) -> None:
        self.executed.append((query, parameters))
        if self.fail:
            raise RuntimeError("audit write must not replace primary failure")

    def fetchone(self) -> tuple[object, ...] | None:
        return self.results.pop(0) if self.results else None


class _Transaction:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def __enter__(self) -> _Transaction:
        self.connection.transaction_count += 1
        return self

    def __exit__(self, exc_type: object, *_: object) -> None:
        self.connection.rolled_back = exc_type is not None
        return None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_value = cursor
        self.transaction_count = 0
        self.rolled_back = False
        self.committed = False
        self.closed = False

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self.cursor_value

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class _StateConnection:
    """Psycopg-faithful primary fake: context exit would be a second terminal call."""

    def __init__(
        self,
        cursor: _Cursor,
        events: list[str],
        *,
        commit_error: Exception | None = None,
        rollback_error: bool = False,
        close_error: Exception | None = None,
    ) -> None:
        self.cursor_value = cursor
        self.events = events
        self.commit_error = commit_error
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.connect_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0
        self.audit_count = 0
        self.enter_count = 0
        self.exit_count = 0
        self.transaction_count = 0

    def __enter__(self) -> _StateConnection:
        self.enter_count += 1
        raise AssertionError("primary rebuild must not enter a connection context")

    def __exit__(self, *_: object) -> None:
        self.exit_count += 1
        raise AssertionError("primary rebuild must not exit a connection context")

    def cursor(self) -> _Cursor:
        return self.cursor_value

    def transaction(self) -> object:
        self.transaction_count += 1
        raise AssertionError("primary rebuild must not use connection.transaction()")

    def commit(self) -> None:
        self.events.append("commit")
        self.commit_count += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.events.append("rollback")
        self.rollback_count += 1
        if self.rollback_error:
            raise RuntimeError("rollback failure")

    def close(self) -> None:
        self.events.append("close")
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


class _AuditConnection(_Connection):
    def __init__(self, cursor: _Cursor, events: list[str]) -> None:
        super().__init__(cursor)
        self.events = events

    def __enter__(self) -> _AuditConnection:
        self.events.append("audit.enter")
        return self


def _primary_factory(
    primary: _StateConnection, audit: _AuditConnection | None
) -> Callable[[str], object]:
    connections: list[object] = [primary, *([] if audit is None else [audit])]

    def factory(_: str) -> object:
        connection = connections.pop(0)
        if connection is primary:
            primary.connect_count += 1
            primary.events.append("connect")
        else:
            primary.audit_count += 1
        return connection

    return factory


def _assert_primary_seams_unused(primary: _StateConnection) -> None:
    assert primary.enter_count == primary.exit_count == primary.transaction_count == 0
