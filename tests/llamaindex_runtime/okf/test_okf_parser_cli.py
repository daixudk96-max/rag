from __future__ import annotations

import importlib
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest


EXPECTED_OKF_EXPORTS = [
    "OKFParser",
    "OKFDocument",
    "OKFFrontmatter",
    "OKFParagraph",
]
FORBIDDEN_IMPORT_PREFIXES = (
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


def _clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "DATABASE_URL",
            "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
            "OKF_REBUILD_EXPECTED_DATABASE",
        }
    }


def _run_clean_python(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        check=False,
        text=True,
        env=_clean_environment(),
    )


def test_okf_facade_is_lazy_and_preserves_canonical_parser_exports() -> None:
    result = _run_clean_python(
        "import inspect, json, pickle, socket, sys\n"
        "def blocked(*args, **kwargs):\n"
        "    raise AssertionError('network access during OKF facade import')\n"
        "socket.create_connection = blocked\n"
        "socket.socket.connect = blocked\n"
        "socket.socket.connect_ex = blocked\n"
        "import llamaindex_runtime.okf as okf\n"
        "assert okf.__all__ == " + repr(EXPECTED_OKF_EXPORTS) + "\n"
        "assert set(okf.__all__) <= set(dir(okf))\n"
        "assert 'llamaindex_runtime.okf.parser' not in sys.modules\n"
        "try:\n"
        "    okf.unknown_okf_export\n"
        "except AttributeError as error:\n"
        "    assert str(error) == 'unknown_okf_export'\n"
        "    assert error.__cause__ is None\n"
        "else:\n"
        "    raise AssertionError('unknown name must raise AttributeError')\n"
        "from llamaindex_runtime.okf import parser\n"
        "for name in okf.__all__:\n"
        "    direct = getattr(parser, name)\n"
        "    value = getattr(okf, name)\n"
        "    assert value is direct\n"
        "    assert value.__module__ == 'llamaindex_runtime.okf.parser'\n"
        "    assert inspect.signature(value) == inspect.signature(direct)\n"
        "    assert pickle.loads(pickle.dumps(value)) is direct\n"
        "assert okf.__dict__['OKFParser'] is parser.OKFParser\n"
        "namespace = {}\n"
        "exec('from llamaindex_runtime.okf import *', namespace)\n"
        "assert all(namespace[name] is getattr(okf, name) for name in okf.__all__)\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_okf_facade_direct_parser_first_and_concurrent_access_are_canonical() -> None:
    result = _run_clean_python(
        "from concurrent.futures import ThreadPoolExecutor\n"
        "from llamaindex_runtime.okf.parser import OKFDocument, OKFFrontmatter, OKFParagraph, OKFParser\n"
        "import llamaindex_runtime.okf as okf\n"
        "expected = (OKFParser, OKFDocument, OKFFrontmatter, OKFParagraph)\n"
        "with ThreadPoolExecutor(max_workers=8) as executor:\n"
        "    values = list(executor.map(lambda _: tuple(getattr(okf, name) for name in okf.__all__), range(32)))\n"
        "assert all(value == expected for value in values)\n"
        "assert all(left is right for left, right in zip(values[0], expected))\n"
    )

    assert result.returncode == 0, result.stderr


def test_okf_facade_import_does_not_load_forbidden_modules() -> None:
    result = _run_clean_python(
        "import json, socket, sys\n"
        "def blocked(*args, **kwargs):\n"
        "    raise AssertionError('network access during OKF facade import')\n"
        "socket.create_connection = blocked\n"
        "socket.socket.connect = blocked\n"
        "socket.socket.connect_ex = blocked\n"
        "import llamaindex_runtime.okf\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    loaded_modules = set(__import__("json").loads(result.stdout))
    assert not [
        name
        for name in loaded_modules
        if any(
            name == prefix or name.startswith(f"{prefix}.")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    ]


def test_okf_facade_resolves_and_caches_all_public_exports_in_process() -> None:
    okf = __import__("llamaindex_runtime.okf", fromlist=["*"])
    parser = importlib.import_module("llamaindex_runtime.okf.parser")

    assert tuple(getattr(okf, name) for name in okf.__all__) == tuple(
        getattr(parser, name) for name in okf.__all__
    )
    assert all(name in okf.__dict__ for name in okf.__all__)
    assert set(okf.__all__) <= set(dir(okf))
    with pytest.raises(AttributeError, match="unknown_okf_export"):
        okf.unknown_okf_export


def test_parser_module_cli_accepts_a_valid_known_type_bundle(tmp_path: Path) -> None:
    document = tmp_path / "entity.md"
    document.write_text(
        "---\n"
        "type: entity\n"
        "title: Alice\n"
        "timestamp: '2026-07-15T09:30:00Z'\n"
        "canonical_entity_id: b2191a11-cd8b-4c6e-b34a-7b5552e3c03c\n"
        "entity_type: person\n"
        "---\n"
        "Alice is an engineer.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "llamaindex_runtime.okf.parser", str(tmp_path)],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        check=False,
        text=True,
        env=_clean_environment(),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "Parsed 1 documents:" in result.stdout
    assert "Type: document" in result.stdout
    assert "Title:" not in result.stdout
    assert "Aliases:" not in result.stdout
    assert "entity.md" not in result.stdout
    assert "\x1b" not in result.stdout
    assert not [
        character
        for character in result.stdout
        if character not in "\n\r\t" and unicodedata.category(character).startswith("C")
    ]
