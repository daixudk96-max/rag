from __future__ import annotations

import os
from pathlib import Path

import psycopg

from llamaindex_runtime.registry.migration_catalog import (
    FULL_MIGRATION_CATALOG,
    PAGEINDEX_MIGRATIONS,
)

# Compatibility export: the root runner has one authoritative catalog.
KEY_MIGRATIONS = FULL_MIGRATION_CATALOG
__all__ = ["KEY_MIGRATIONS", "PAGEINDEX_MIGRATIONS", "main"]


def main() -> None:
    migrations_dir = (
        Path(__file__).resolve().parent
        / "llamaindex_runtime"
        / "registry"
        / "migrations"
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for migration_file in KEY_MIGRATIONS:
                migration_path = migrations_dir / migration_file
                migration_sql = migration_path.read_text(encoding="utf-8")
                cursor.execute(migration_sql)
                connection.commit()
                print(f"Applied migration: {migration_file}")

            cursor.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
            tables = tuple(row[0] for row in cursor.fetchall())

    print(f"Tables after migrations: {len(tables)}")
    for table in tables:
        print(f"  - {table}")


if __name__ == "__main__":
    main()
