from __future__ import annotations

from pathlib import Path
import tomllib

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "verification" / "docker-compose.yml"
PYPROJECT_PATH = REPO_ROOT / "llamaindex_runtime" / "pyproject.toml"
README_PATH = REPO_ROOT / "verification" / "README.md"


def test_verification_compose_exposes_all_backend_services() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = compose["services"]

    assert {"postgres", "qdrant", "milvus"}.issubset(services.keys())


def test_verification_compose_publishes_backend_ports() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = compose["services"]

    assert "5432:5432" in services["postgres"]["ports"]
    assert "6333:6333" in services["qdrant"]["ports"]
    assert "19530:19530" in services["milvus"]["ports"]


def test_verification_compose_uses_formal_runtime_migrations() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    postgres_volumes = compose["services"]["postgres"]["volumes"]

    assert any(
        "llamaindex_runtime/registry/migrations" in volume
        for volume in postgres_volumes
    )


def test_pyproject_declares_qdrant_and_milvus_optional_dependencies() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    optional = pyproject["project"]["optional-dependencies"]

    assert "qdrant" in optional
    assert "milvus" in optional


def test_verification_readme_documents_all_backend_env_vars() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "FORMAL_RUNTIME_DATABASE_URL" in readme
    assert "QDRANT_URL" in readme
    assert "MILVUS_URL" in readme
    assert "VECTOR_BACKEND" in readme


def test_verification_compose_requires_explicit_credentials() -> None:
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8")

    assert (
        "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
        in compose_text
    )
    assert (
        "MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY:?MINIO_ACCESS_KEY must be set}"
        in compose_text
    )
    assert (
        "MINIO_SECRET_KEY: ${MINIO_SECRET_KEY:?MINIO_SECRET_KEY must be set}"
        in compose_text
    )
