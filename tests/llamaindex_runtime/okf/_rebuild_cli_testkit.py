"""Shared builders and typed fakes for rebuild CLI behavioral tests."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
from psycopg import pq

from llamaindex_runtime.okf.parser import BundleResult, BundleStats, OKFDocument
from llamaindex_runtime.okf.serializer import serialize_document

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "rebuild_from_okf.py"
FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "okf_roundtrip"
_LIBPQ_ENVIRONMENT_KEYS = frozenset(
    default.envvar.decode("ascii")
    for default in pq.Conninfo.get_defaults()
    if default.envvar
)
_DATABASE_ENVIRONMENT_KEYS: frozenset[str] = _LIBPQ_ENVIRONMENT_KEYS | frozenset(
    {
        "PGREQUIRESSL",
        "PGSERVICEFILE",
        "PGSYSCONFDIR",
        "DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
        "OKF_FAILURE_AUDIT_ACCEPTANCE",
        "OKF_REBUILD_DOCKER_ACCEPTANCE",
    }
)


def _disposable_connection(
    database_url: str,
    *,
    autocommit: bool = False,
    connect_timeout: int = 5,
) -> psycopg.Connection[Any]:
    """Reuse production parsing and libpq controls for test-only direct access."""
    module = load_rebuild_module()
    target = module._parse_disposable_postgresql_target(str(database_url), "okf_task34")
    kwargs = module._runtime_connection_kwargs(
        target, autocommit=autocommit, connect_timeout=connect_timeout
    )
    return psycopg.connect(**kwargs)


def _sanitized_child_environment() -> dict[str, str]:
    """Build a child environment without inherited database routing."""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in _DATABASE_ENVIRONMENT_KEYS
    }


def load_rebuild_module() -> ModuleType:
    """Load the script as an isolated module for direct CLI contract tests."""
    spec = importlib.util.spec_from_file_location("rebuild_from_okf", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_bundle(tmp_path: Path, fixture: str) -> Path:
    """Serialize a frozen fixture into a temporary OKF bundle."""
    fixture_dir = FIXTURE_ROOT / fixture
    expected = json.loads(
        (fixture_dir / "expected_span_ids.json").read_text(encoding="utf-8")
    )
    nodes = json.loads(
        (fixture_dir / "docling_output.json").read_text(encoding="utf-8")
    )
    serialize_document(
        nodes,
        doc_id=expected["doc_id"],
        version_id=expected["version_id"],
        source_checksum="0" * 64,
        docling_version="2.109.0",
        bundle_root=tmp_path,
        name=fixture,
    )
    return tmp_path


def bundle_result(*documents: OKFDocument) -> BundleResult:
    """Create parser-shaped results without a filesystem roundtrip."""
    return BundleResult(
        list(documents), BundleStats(parsed=len(documents), skipped=0, malformed=0)
    )


def run_cli(
    *args: str,
    database_url: str | None = None,
    expected_database: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the CLI with every database-related environment variable removed."""
    env = _sanitized_child_environment()
    if database_url is not None:
        env["DATABASE_URL"] = database_url
        env["OKF_MIGRATION_TEST_DATABASE_DISPOSABLE"] = "1"
    if expected_database is not None:
        env["OKF_REBUILD_EXPECTED_DATABASE"] = expected_database
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


class Cursor:
    """Typed in-memory DB-API fake capturing queries and result sets."""

    def __init__(
        self, result_sets: list[list[tuple[object, ...]]] | None = None
    ) -> None:
        self._result_sets: Iterator[list[tuple[object, ...]]] = iter(result_sets or [])
        self._active_result_set: list[tuple[object, ...]] = []
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []

    def __enter__(self) -> Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, parameters: tuple[object, ...] | None = None) -> None:
        self.executed.append((query, parameters))
        if query.startswith("SELECT"):
            self._active_result_set = list(next(self._result_sets))

    def executemany(self, query: str, parameters: Iterable[tuple[object, ...]]) -> None:
        self.executed.append((query, tuple(parameters)))

    def fetchone(self) -> tuple[object, ...] | None:
        return self._active_result_set.pop(0) if self._active_result_set else None

    def fetchall(self) -> list[tuple[object, ...]]:
        result_set = self._active_result_set
        self._active_result_set = []
        return result_set


class Transaction:
    """Track whether the fake primary connection entered a transaction."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def __enter__(self) -> Transaction:
        self.connection.transactions += 1
        return self

    def __exit__(self, exc_type: object, *_: object) -> None:
        self.connection.rolled_back = exc_type is not None
        return None


class Connection:
    """Typed connection fake for rebuild transaction behavior."""

    def __init__(self, cursor: Cursor) -> None:
        self._cursor = cursor
        self.transactions = 0
        self.rolled_back = False
        self.committed = False

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> Cursor:
        return self._cursor

    def transaction(self) -> Transaction:
        return Transaction(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        return None
