from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from llamaindex_runtime.config import RuntimeSettings


SUBPACKAGES = [
    "llamaindex_runtime.ingestion",
    "llamaindex_runtime.registry",
    "llamaindex_runtime.vector",
    "llamaindex_runtime.tree",
    "llamaindex_runtime.entrypoints",
    "llamaindex_runtime.graph",
    "llamaindex_runtime.interfaces",
    "llamaindex_runtime.embeddings",
]

EXPECTED_ROOT_EXPORTS = [
    "CanonicalSpan",
    "HybridRetrievalWorkflow",
    "JsonFormatter",
    "PostgresRegistryWriter",
    "QueryAgent",
    "QueryHit",
    "QueryResult",
    "RegistryWriter",
    "RetrievalTool",
    "RuntimeSettings",
    "SentenceTransformersEmbedding",
    "classify_query",
    "create_embed_model",
    "format_result_as_json",
    "get_request_logger",
    "main",
    "query",
    "setup_logging",
]
FORBIDDEN_EAGER_MODULES = (
    "sentence_transformers",
    "transformers",
    "torch",
    "litellm",
    "llamaindex_runtime.embeddings",
    "llamaindex_runtime.agent",
    "llamaindex_runtime.workflow",
    "llamaindex_runtime.cli",
    "llamaindex_runtime.entrypoints",
    "psycopg",
    "llamaindex_runtime.registry",
    "llama_index",
)

EXPECTED_GRAPH_EXPORTS: list[str] = []

EXPECTED_ENTRYPOINT_EXPORTS = ["QueryHit", "QueryResult", "classify_query", "query"]


def _matches_forbidden_prefix(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_EAGER_MODULES
    )


def _run_clean_python(source: str) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "DATABASE_URL",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
            "OKF_REBUILD_EXPECTED_DATABASE",
        }
    }
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        check=False,
        text=True,
        env=env,
    )


def test_runtime_package_is_importable() -> None:
    module = importlib.import_module("llamaindex_runtime")
    assert module.__name__ == "llamaindex_runtime"


def test_root_facade_handles_unknown_attributes_in_process() -> None:
    module = importlib.import_module("llamaindex_runtime")

    assert set(module.__all__) <= set(dir(module))
    with pytest.raises(AttributeError, match="unknown_runtime_export"):
        module.unknown_runtime_export


def test_runtime_version_is_semver() -> None:
    module = importlib.import_module("llamaindex_runtime")
    assert re.fullmatch(r"\d+\.\d+\.\d+", module.__version__)


def test_root_import_is_lazy_network_free_and_stderr_clean() -> None:
    result = _run_clean_python(
        "import json, socket, sys\n"
        "def blocked(*args, **kwargs):\n"
        "    raise AssertionError('network access during package import')\n"
        "socket.create_connection = blocked\n"
        "socket.socket.connect = blocked\n"
        "socket.socket.connect_ex = blocked\n"
        "import llamaindex_runtime\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    loaded_modules = json.loads(result.stdout)
    assert not [name for name in loaded_modules if _matches_forbidden_prefix(name)]


def test_okf_parser_import_is_lazy_network_free_and_stderr_clean() -> None:
    result = _run_clean_python(
        "import json, socket, sys\n"
        "def blocked(*args, **kwargs):\n"
        "    raise AssertionError('network access during parser import')\n"
        "socket.create_connection = blocked\n"
        "socket.socket.connect = blocked\n"
        "socket.socket.connect_ex = blocked\n"
        "import llamaindex_runtime.okf.parser\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    loaded_modules = json.loads(result.stdout)
    assert not [name for name in loaded_modules if _matches_forbidden_prefix(name)]


def test_root_facade_preserves_public_surface_and_lazy_cache() -> None:
    result = _run_clean_python(
        "import json, llamaindex_runtime as runtime, sys\n"
        "before = set(sys.modules)\n"
        "assert runtime.__all__ == " + repr(EXPECTED_ROOT_EXPORTS) + "\n"
        "assert runtime.__version__ == '0.1.0'\n"
        "assert '__version__' not in runtime.__all__\n"
        "assert set(runtime.__all__) <= set(dir(runtime))\n"
        "try:\n"
        "    runtime.unknown_runtime_export\n"
        "except AttributeError as error:\n"
        "    assert error.__cause__ is None\n"
        "else:\n"
        "    raise AssertionError('unknown name must raise AttributeError')\n"
        "value = runtime.JsonFormatter\n"
        "from llamaindex_runtime.logging import JsonFormatter\n"
        "assert value is JsonFormatter\n"
        "assert runtime.__dict__['JsonFormatter'] is value\n"
        "after_lightweight = set(sys.modules)\n"
        "assert 'llamaindex_runtime.embeddings' not in after_lightweight\n"
        "assert 'llamaindex_runtime.agent' not in after_lightweight\n"
        "assert 'llamaindex_runtime.workflow' not in after_lightweight\n"
        "assert 'llamaindex_runtime.registry.postgres_adapter' not in after_lightweight\n"
        "embedding = runtime.SentenceTransformersEmbedding\n"
        "from llamaindex_runtime.embeddings import SentenceTransformersEmbedding\n"
        "assert embedding is SentenceTransformersEmbedding\n"
        "assert 'llamaindex_runtime.embeddings' in sys.modules\n"
        "print(json.dumps(sorted(set(sys.modules) - before)))\n"
    )

    assert result.returncode == 0, result.stderr


def test_root_star_import_resolves_the_legacy_all_surface() -> None:
    result = _run_clean_python(
        "namespace = {}\n"
        "exec('from llamaindex_runtime import *', namespace)\n"
        "expected = " + repr(EXPECTED_ROOT_EXPORTS) + "\n"
        "assert all(name in namespace for name in expected)\n"
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module_name", SUBPACKAGES)
def test_runtime_subpackages_are_importable(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.__name__ == module_name


@pytest.mark.parametrize(
    "import_sequence",
    [
        "implementation = importlib.import_module('llamaindex_runtime.entrypoints._query')\n"
        "facade_query = entrypoints.query\n"
        "assert facade_query is implementation.query\n"
        "assert callable(facade_query)\n",
        "facade_query = entrypoints.query\n"
        "implementation = importlib.import_module('llamaindex_runtime.entrypoints._query')\n"
        "assert entrypoints.query is facade_query\n"
        "assert facade_query is implementation.query\n"
        "assert callable(entrypoints.query)\n",
        "namespace = {}\n"
        "exec('from llamaindex_runtime.entrypoints import *', namespace)\n"
        "facade_query = namespace['query']\n"
        "implementation = importlib.import_module('llamaindex_runtime.entrypoints._query')\n"
        "assert entrypoints.query is facade_query\n"
        "assert facade_query is implementation.query\n"
        "assert callable(namespace['query'])\n",
    ],
    ids=["implementation-submodule-first", "facade-first", "star-import"],
)
def test_entrypoints_query_facade_is_stable_across_import_orders(
    import_sequence: str,
) -> None:
    result = _run_clean_python(
        "import importlib\n"
        "entrypoints = importlib.import_module('llamaindex_runtime.entrypoints')\n"
        + import_sequence
    )

    assert result.returncode == 0, result.stderr


def test_entrypoints_facade_resolves_exports_and_unknown_attributes() -> None:
    entrypoints = importlib.import_module("llamaindex_runtime.entrypoints")
    modules = {
        "QueryHit": importlib.import_module("llamaindex_runtime.entrypoints.types"),
        "QueryResult": importlib.import_module("llamaindex_runtime.entrypoints.types"),
        "classify_query": importlib.import_module(
            "llamaindex_runtime.entrypoints.classifier"
        ),
        "query": importlib.import_module("llamaindex_runtime.entrypoints._query"),
    }

    for name in EXPECTED_ENTRYPOINT_EXPORTS:
        entrypoints.__dict__.pop(name, None)

    assert set(entrypoints.__all__) <= set(dir(entrypoints))
    with pytest.raises(AttributeError, match="unknown_entrypoint_export"):
        entrypoints.unknown_entrypoint_export
    assert all(
        getattr(entrypoints, name) is getattr(modules[name], name) for name in modules
    )


@pytest.mark.parametrize(
    "import_order",
    [
        ("llamaindex_runtime.graph", "llamaindex_runtime.entrypoints"),
        ("llamaindex_runtime.entrypoints", "llamaindex_runtime.graph"),
    ],
)
def test_graph_and_entrypoint_facades_are_import_order_independent(
    import_order: tuple[str, str, str],
) -> None:
    result = _run_clean_python(
        "import importlib, sys\n"
        f"order = {import_order!r}\n"
        "for name in order:\n"
        "    importlib.import_module(name)\n"
        "graph = importlib.import_module('llamaindex_runtime.graph')\n"
        "entrypoints = importlib.import_module('llamaindex_runtime.entrypoints')\n"
        "entrypoint_types = importlib.import_module('llamaindex_runtime.entrypoints.types')\n"
        "entrypoint_classifier = importlib.import_module('llamaindex_runtime.entrypoints.classifier')\n"
        "assert not any(name == 'torch' or name.startswith('torch.') for name in sys.modules)\n"
        "assert not any(name == 'llamaindex_runtime.agent' or name.startswith('llamaindex_runtime.agent.') for name in sys.modules)\n"
        f"assert graph.__all__ == {EXPECTED_GRAPH_EXPORTS!r}\n"
        f"assert entrypoints.__all__ == {EXPECTED_ENTRYPOINT_EXPORTS!r}\n"
        "assert set(entrypoints.__all__) <= set(dir(entrypoints))\n"
        "try:\n"
        "    entrypoints.unknown_entrypoint_export\n"
        "except AttributeError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('unknown name must raise AttributeError')\n"
        "assert entrypoints.QueryHit is entrypoint_types.QueryHit\n"
        "assert entrypoints.QueryResult is entrypoint_types.QueryResult\n"
        "assert entrypoints.classify_query is entrypoint_classifier.classify_query\n"
        "facade_query = entrypoints.query\n"
        "entrypoint_query = importlib.import_module('llamaindex_runtime.entrypoints._query')\n"
        "assert facade_query is entrypoint_query.query\n"
        "assert entrypoints.query is facade_query\n"
    )

    assert result.returncode == 0, result.stderr


def test_runtime_settings_require_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Isolate cwd to a dir with no .env so from_env's .env-fallback does not
    # refill DATABASE_URL after delenv (env-first/.env-fallback precedence).
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        RuntimeSettings.from_env()


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [("vector_backend", "unknown"), ("tree_strategy", "custom")],
)
def test_runtime_settings_validate_supported_strategies(
    field_name: str, field_value: str
) -> None:
    kwargs = {
        "database_url": "postgresql://postgres:postgres@localhost:5432/rag_registry",
        "vector_backend": "pgvector",
        "tree_strategy": "auto_merging",
    }
    kwargs[field_name] = field_value

    with pytest.raises(ValueError):
        RuntimeSettings(**kwargs)


def test_postgres_registry_writer_is_exposed_from_top_level() -> None:
    """PostgresRegistryWriter should be importable from llamaindex_runtime."""
    from llamaindex_runtime import PostgresRegistryWriter
    from llamaindex_runtime.registry.postgres_adapter import (
        PostgresRegistryWriter as DirectPostgresRegistryWriter,
    )

    assert PostgresRegistryWriter is DirectPostgresRegistryWriter


def test_registry_writer_healthcheck_returns_true_on_success() -> None:
    """PostgresRegistryWriter.healthcheck() should return True when SELECT 1 succeeds."""
    from unittest.mock import MagicMock, patch
    from llamaindex_runtime import PostgresRegistryWriter

    # Patch register_vector to bypass psycopg type checking
    with patch("llamaindex_runtime.registry.postgres_adapter.register_vector"):
        # Create a mock connection and cursor
        mock_connection = MagicMock()
        mock_connection.autocommit = (
            False  # Required by PostgresRegistryWriter.__init__
        )
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)

        # Create writer with mock connection
        writer = PostgresRegistryWriter(mock_connection)

        # Test healthcheck returns True
        assert writer.healthcheck() is True

        # Verify the correct query was executed
        mock_cursor.execute.assert_called_once_with("SELECT 1")


def test_registry_writer_healthcheck_returns_false_on_failure() -> None:
    """PostgresRegistryWriter.healthcheck() should return False when query fails."""
    from unittest.mock import MagicMock, patch
    from llamaindex_runtime import PostgresRegistryWriter

    # Patch register_vector to bypass psycopg type checking
    with patch("llamaindex_runtime.registry.postgres_adapter.register_vector"):
        # Create a mock connection and cursor that returns wrong result
        mock_connection = MagicMock()
        mock_connection.autocommit = (
            False  # Required by PostgresRegistryWriter.__init__
        )
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (0,)

        # Create writer with mock connection
        writer = PostgresRegistryWriter(mock_connection)

        # Test healthcheck returns False
        assert writer.healthcheck() is False


def test_json_formatter_is_exposed_from_top_level() -> None:
    """JsonFormatter should be importable from llamaindex_runtime."""
    from llamaindex_runtime import JsonFormatter
    from llamaindex_runtime.logging import JsonFormatter as DirectJsonFormatter

    assert JsonFormatter is DirectJsonFormatter


def test_setup_logging_is_exposed_from_top_level() -> None:
    """setup_logging should be importable from llamaindex_runtime."""
    from llamaindex_runtime import setup_logging
    from llamaindex_runtime.logging import setup_logging as DirectSetupLogging

    assert setup_logging is DirectSetupLogging


def test_get_request_logger_is_exposed_from_top_level() -> None:
    """get_request_logger should be importable from llamaindex_runtime."""
    from llamaindex_runtime import get_request_logger
    from llamaindex_runtime.logging import get_request_logger as DirectGetRequestLogger

    assert get_request_logger is DirectGetRequestLogger


def test_registry_writer_protocol_is_exposed_from_top_level() -> None:
    """RegistryWriter protocol should be importable from llamaindex_runtime."""
    from llamaindex_runtime import RegistryWriter
    from llamaindex_runtime.registry.contracts import (
        RegistryWriter as DirectRegistryWriter,
    )

    assert RegistryWriter is DirectRegistryWriter


def test_registry_writer_is_protocol() -> None:
    """RegistryWriter should be a Protocol for type checking."""
    from typing import Protocol

    from llamaindex_runtime import RegistryWriter

    assert issubclass(RegistryWriter, Protocol)


def test_root_facade_handles_direct_submodule_first_and_concurrent_access() -> None:
    result = _run_clean_python(
        "from concurrent.futures import ThreadPoolExecutor\n"
        "from llamaindex_runtime.logging import JsonFormatter\n"
        "import llamaindex_runtime as runtime\n"
        "with ThreadPoolExecutor(max_workers=8) as executor:\n"
        "    values = list(executor.map(lambda _: runtime.JsonFormatter, range(32)))\n"
        "assert all(value is JsonFormatter for value in values)\n"
        "assert runtime.__dict__['JsonFormatter'] is JsonFormatter\n"
    )

    assert result.returncode == 0, result.stderr
