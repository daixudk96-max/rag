"""TDD tests for Phase 16-01: the RAG_ENTITY_EXTRACTOR control-plane switch.

Frozen contract (16-BOUNDARY D8 / R-OKF-04):
- ``VALID_ENTITY_EXTRACTORS`` is exactly ``{"off"}``.
- The switch defaults to ``"off"`` so the enabled baseline consumes zero
  generative-LLM/model resources until explicitly enabled.
- Invalid values fail fast at construction time, before any entity code or
  model package could be imported.
- ``from_env()`` reads ``RAG_ENTITY_EXTRACTOR`` with the existing
  process-env-over-.env-file precedence (no new semantics for other keys).
- Constructing ``RuntimeSettings`` never imports ``modelscope`` / ``torch`` /
  ``sentencepiece``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from llamaindex_runtime.config import RuntimeSettings

REPO_ROOT = Path(__file__).resolve().parents[2]

# Live/authorization variables that must never be present during non-live
# selectors (mirrors the plan's `env -u` list).
_LIVE_DB_VARS = (
    "DATABASE_URL",
    "FORMAL_RUNTIME_DATABASE_URL",
    "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
    "OKF_REBUILD_EXPECTED_DATABASE",
    "OKF_FAILURE_AUDIT_ACCEPTANCE",
    "OKF_REBUILD_DOCKER_ACCEPTANCE",
    "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
    "OKF_E2B_DISPOSABLE_TEST_AUTHORIZED",
    "OKF_E2B_MIGRATION_TEST_AUTHORIZED",
    "OKF_E2B_MODELSCOPE_MIRROR_AUTHORIZED",
    "OKF_E2B_RANER_SMOKE_AUTHORIZED",
    "OKF_E2B_C2_ENTRY_AUTHORIZED",
)

_HEAVY_MODULE_PREFIXES = ("modelscope", "torch", "sentencepiece")


def _db_url() -> str:
    return "postgresql://postgres:postgres@localhost:5432/rag_registry"


class TestRagEntityExtractorSwitch:
    """RuntimeSettings accepts only off and defaults to off."""

    def test_valid_entity_extractors_is_frozen_set(self) -> None:
        assert RuntimeSettings.VALID_ENTITY_EXTRACTORS == frozenset({"off"})

    def test_default_is_off(self) -> None:
        settings = RuntimeSettings(database_url=_db_url())
        assert settings.rag_entity_extractor == "off"

    def test_explicit_off_is_accepted(self) -> None:
        settings = RuntimeSettings(database_url=_db_url(), rag_entity_extractor="off")
        assert settings.rag_entity_extractor == "off"

    def test_retired_raner_value_is_rejected(self) -> None:
        # RaNER was retired in Phase 19; the value must fail closed.
        with pytest.raises(ValueError, match="entity extractor"):
            RuntimeSettings(database_url=_db_url(), rag_entity_extractor="raner")

    @pytest.mark.parametrize("invalid", ["uie", "hanlp", "deepke", ""])
    def test_invalid_values_raise_value_error(self, invalid: str) -> None:
        with pytest.raises(ValueError, match="entity extractor"):
            RuntimeSettings(database_url=_db_url(), rag_entity_extractor=invalid)

    def test_not_yet_frozen_degradation_candidate_is_rejected(self) -> None:
        # base-news is only a future resource-limited degradation candidate and
        # must NOT be silently accepted as an enabled switch value.
        with pytest.raises(ValueError, match="entity extractor"):
            RuntimeSettings(database_url=_db_url(), rag_entity_extractor="base-news")


class TestRagEntityExtractorEnv:
    """from_env reads RAG_ENTITY_EXTRACTOR with process-env-over-.env precedence."""

    def test_from_env_rejects_retired_raner_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", _db_url())
        monkeypatch.setenv("RAG_ENTITY_EXTRACTOR", "raner")
        with pytest.raises(ValueError, match="entity extractor"):
            RuntimeSettings.from_env()

    def test_from_env_defaults_to_off_when_unset(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Isolate cwd so the repo .env fallback cannot refill the key.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE_URL", _db_url())
        monkeypatch.delenv("RAG_ENTITY_EXTRACTOR", raising=False)
        settings = RuntimeSettings.from_env()
        assert settings.rag_entity_extractor == "off"

    def test_from_env_rejects_invalid_env_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", _db_url())
        monkeypatch.setenv("RAG_ENTITY_EXTRACTOR", "uie")
        with pytest.raises(ValueError, match="entity extractor"):
            RuntimeSettings.from_env()

    def test_process_env_wins_over_env_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql://file@localhost/db\n" "RAG_ENTITY_EXTRACTOR=uie\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE_URL", _db_url())
        monkeypatch.setenv("RAG_ENTITY_EXTRACTOR", "off")
        settings = RuntimeSettings.from_env()
        assert settings.rag_entity_extractor == "off"

    def test_env_file_loaded_when_process_env_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql://file@localhost/db\n" "RAG_ENTITY_EXTRACTOR=off\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("RAG_ENTITY_EXTRACTOR", raising=False)
        settings = RuntimeSettings.from_env()
        assert settings.database_url == "postgresql://file@localhost/db"
        assert settings.rag_entity_extractor == "off"


class TestNoHeavyImportAtConfigConstruction:
    """Constructing RuntimeSettings must not import modelscope/torch/sentencepiece."""

    def _run_clean_python(self, source: str) -> subprocess.CompletedProcess[str]:
        env = {
            key: value for key, value in os.environ.items() if key not in _LIVE_DB_VARS
        }
        return subprocess.run(
            [sys.executable, "-c", source],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            text=True,
            env=env,
        )

    def test_config_construction_imports_no_heavy_modules(self) -> None:
        source = (
            "import json, sys\n"
            "from llamaindex_runtime.config import RuntimeSettings\n"
            "settings = RuntimeSettings(database_url='postgresql://x@localhost/x')\n"
            "assert settings.rag_entity_extractor == 'off'\n"
            "loaded = sorted(sys.modules)\n"
            "heavy = [n for n in loaded if any(\n"
            "    n == prefix or n.startswith(prefix + '.')\n"
            "    for prefix in ('modelscope', 'torch', 'sentencepiece')\n"
            ")]\n"
            "print(json.dumps(heavy))\n"
        )
        result = self._run_clean_python(source)
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert json.loads(result.stdout) == []


class TestRagCorefResolverSwitch:
    """RuntimeSettings accepts exactly off|rules and defaults to off (16-C2).

    Frozen contract (supplement handoff §4.4 / R-OKF-09):
    - ``VALID_COREF_RESOLVERS`` is exactly ``{"off", "rules"}``.
    - The switch defaults to ``"off"`` so C2 behavior is byte-identical to
      C1-only and the rules engine produces nothing.
    - Invalid values (including any model value) fail fast at construction
      time, before any coref code could run.
    """

    def test_valid_coref_resolvers_is_frozen_set(self) -> None:
        assert RuntimeSettings.VALID_COREF_RESOLVERS == frozenset({"off", "rules"})

    def test_default_is_off(self) -> None:
        settings = RuntimeSettings(database_url=_db_url())
        assert settings.rag_coref_resolver == "off"

    def test_explicit_off_is_accepted(self) -> None:
        settings = RuntimeSettings(database_url=_db_url(), rag_coref_resolver="off")
        assert settings.rag_coref_resolver == "off"

    def test_explicit_rules_is_accepted(self) -> None:
        settings = RuntimeSettings(database_url=_db_url(), rag_coref_resolver="rules")
        assert settings.rag_coref_resolver == "rules"

    @pytest.mark.parametrize("invalid", ["model", "hanlp", "llm", ""])
    def test_invalid_values_raise_value_error(self, invalid: str) -> None:
        with pytest.raises(ValueError, match="coref resolver"):
            RuntimeSettings(database_url=_db_url(), rag_coref_resolver=invalid)

    def test_not_yet_frozen_model_value_is_rejected(self) -> None:
        # Any model value must first complete checkpoint/license/output-
        # contract/fixture review (supplement handoff §4.4); it must NOT be
        # accepted through the config surface as a supported capability.
        with pytest.raises(ValueError, match="coref resolver"):
            RuntimeSettings(database_url=_db_url(), rag_coref_resolver="model")


class TestRagCorefResolverEnv:
    """from_env reads RAG_COREF_RESOLVER with process-env-over-.env precedence."""

    def test_from_env_reads_rules(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", _db_url())
        monkeypatch.setenv("RAG_COREF_RESOLVER", "rules")
        settings = RuntimeSettings.from_env()
        assert settings.rag_coref_resolver == "rules"

    def test_from_env_defaults_to_off_when_unset(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Isolate cwd so the repo .env fallback cannot refill the key.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE_URL", _db_url())
        monkeypatch.delenv("RAG_COREF_RESOLVER", raising=False)
        settings = RuntimeSettings.from_env()
        assert settings.rag_coref_resolver == "off"

    def test_from_env_rejects_invalid_env_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", _db_url())
        monkeypatch.setenv("RAG_COREF_RESOLVER", "model")
        with pytest.raises(ValueError, match="coref resolver"):
            RuntimeSettings.from_env()

    def test_process_env_wins_over_env_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql://file@localhost/db\n" "RAG_COREF_RESOLVER=rules\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE_URL", _db_url())
        monkeypatch.setenv("RAG_COREF_RESOLVER", "off")
        settings = RuntimeSettings.from_env()
        assert settings.rag_coref_resolver == "off"

    def test_env_file_loaded_when_process_env_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql://file@localhost/db\n" "RAG_COREF_RESOLVER=rules\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("RAG_COREF_RESOLVER", raising=False)
        settings = RuntimeSettings.from_env()
        assert settings.database_url == "postgresql://file@localhost/db"
        assert settings.rag_coref_resolver == "rules"


_MIGRATIONS_DIR = REPO_ROOT / "llamaindex_runtime" / "registry" / "migrations"
_MIGRATION_021 = "021_ner_coref_clusters.sql"


class TestMigration021StaticSpec:
    """Non-DB static validation of the provisional 021 C2 schema migration.

    Static inspection only: the file must exist in the catalog, define
    ``coref_clusters`` + ``coref_cluster_mentions`` with normalized membership
    columns, carry the per-cluster tombstone column, and create no
    ``entity_merge_log`` / canonical-merge table (D7).
    """

    def test_catalog_has_021_exactly_once_after_020(self) -> None:
        from llamaindex_runtime.registry.migration_catalog import (
            FULL_MIGRATION_CATALOG,
        )

        assert FULL_MIGRATION_CATALOG.count(_MIGRATION_021) == 1
        assert FULL_MIGRATION_CATALOG.index("020_ner_entity_mentions.sql") + 1 == (
            FULL_MIGRATION_CATALOG.index(_MIGRATION_021)
        )

    def test_021_file_exists_in_migrations_dir(self) -> None:
        assert (_MIGRATIONS_DIR / _MIGRATION_021).is_file()

    def test_021_defines_coref_clusters_and_membership_tables(self) -> None:
        sql = (_MIGRATIONS_DIR / _MIGRATION_021).read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS coref_clusters" in sql
        assert "CREATE TABLE IF NOT EXISTS coref_cluster_mentions" in sql

    def test_021_cluster_table_columns(self) -> None:
        sql = (_MIGRATIONS_DIR / _MIGRATION_021).read_text(encoding="utf-8")
        assert "cluster_id UUID NOT NULL" in sql
        assert "version_id UUID NOT NULL" in sql
        assert "REFERENCES document_versions" in sql
        assert "coref_rules_version TEXT NOT NULL" in sql
        assert "tombstoned BOOLEAN NOT NULL DEFAULT false" in sql
        assert "created_at TIMESTAMPTZ" in sql

    def test_021_normalized_membership_columns(self) -> None:
        sql = (_MIGRATIONS_DIR / _MIGRATION_021).read_text(encoding="utf-8")
        assert "cluster_id UUID NOT NULL" in sql
        assert "mention_id UUID NOT NULL" in sql
        assert "REFERENCES coref_clusters" in sql
        assert "REFERENCES entity_mentions" in sql
        assert "ordinal_no INTEGER NOT NULL DEFAULT 0" in sql
        assert "PRIMARY KEY (cluster_id, mention_id)" in sql

    def test_021_has_no_merge_table(self) -> None:
        sql = (_MIGRATIONS_DIR / _MIGRATION_021).read_text(encoding="utf-8")
        lowered = sql.lower()
        assert "entity_merge_log" not in lowered
        assert "merge_log" not in lowered
        assert "canonical_merge" not in lowered
