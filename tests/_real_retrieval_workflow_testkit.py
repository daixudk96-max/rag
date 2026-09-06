from __future__ import annotations

import psycopg

import scripts.run_pageindex_real_retrieval_workflow as workflow


class _FakeCursor:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.executed_sql: list[str] = []
        self._fail_on_call = fail_on_call

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)
        if (
            self._fail_on_call is not None
            and len(self.executed_sql) == self._fail_on_call
        ):
            raise RuntimeError("boom")


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _HostileError(Exception):
    def __str__(self) -> str:
        raise AssertionError("exception __str__ must not be called")

    def __repr__(self) -> str:
        raise AssertionError("exception __repr__ must not be called")


class _HostileCursor(_FakeCursor):
    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)
        if sql == "SELECT 1":
            raise _HostileError()


def _installed_libpq_envvars() -> set[str]:
    envvars: set[str] = set()
    for option in psycopg.pq.Conninfo.get_defaults():
        metadata_value: object = option.envvar
        envvar = workflow._normalize_libpq_metadata_value(metadata_value)
        if envvar is not None:
            envvars.add(envvar)
    return envvars
