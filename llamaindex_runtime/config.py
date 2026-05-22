from __future__ import annotations

import os
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv, dotenv_values


@dataclass(frozen=True)
class RuntimeSettings:
    VALID_VECTOR_BACKENDS: ClassVar[frozenset[str]] = frozenset({"pgvector", "qdrant", "milvus"})
    VALID_TREE_STRATEGIES: ClassVar[frozenset[str]] = frozenset({"auto_merging"})
    VALID_EMBEDDING_PROVIDERS: ClassVar[frozenset[str]] = frozenset({"mock", "sentence_transformers"})
    VALID_EMBEDDING_MODEL_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"all-MiniLM-L6-v2", "paraphrase-MiniLM-L3-v2", "all-MiniLM-L12-v2", "all-mpnet-base-v2"}
    )

    database_url: str
    vector_backend: str = "pgvector"
    tree_strategy: str = "auto_merging"
    embedding_provider: str = "mock"
    embedding_model_name: str = "all-MiniLM-L6-v2"
    qdrant_url: str = "http://localhost:6333"
    milvus_url: str = "http://localhost:19530"
    # Phase 2: LLM configuration fields for local .env support
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    openai_base_url: str = ""

    def __post_init__(self) -> None:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for the formal runtime")
        if self.vector_backend not in self.VALID_VECTOR_BACKENDS:
            raise ValueError(f"Unsupported vector backend: {self.vector_backend}")
        if self.tree_strategy not in self.VALID_TREE_STRATEGIES:
            raise ValueError(f"Unsupported tree strategy: {self.tree_strategy}")
        if self.embedding_provider not in self.VALID_EMBEDDING_PROVIDERS:
            raise ValueError(f"Unsupported embedding_provider: {self.embedding_provider}")
        if (
            self.embedding_provider == "sentence_transformers"
            and self.embedding_model_name not in self.VALID_EMBEDDING_MODEL_NAMES
        ):
            raise ValueError(f"Unsupported embedding_model_name: {self.embedding_model_name}")
        if self.vector_backend == "qdrant":
            if not self.qdrant_url or not self.qdrant_url.strip():
                raise ValueError("qdrant_url must be a non-empty URL when vector_backend is 'qdrant'")
            parsed = urlparse(self.qdrant_url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("qdrant_url must use http:// or https:// scheme")
            if not parsed.netloc or not parsed.netloc.strip():
                raise ValueError("qdrant_url must include a valid hostname")
        if self.vector_backend == "milvus":
            if not self.milvus_url or not self.milvus_url.strip():
                raise ValueError("milvus_url must be a non-empty URL when vector_backend is 'milvus'")
            parsed = urlparse(self.milvus_url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("milvus_url must use http:// or https:// scheme")
            if not parsed.netloc or not parsed.netloc.strip():
                raise ValueError("milvus_url must include a valid hostname")

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        # Phase 3 fix: Load .env file before reading environment
        # This enables local file-based config without session mutation
        #
        # Strategy: Find .env in cwd, load values into os.environ
        # This works even when os.environ was cleared (pure file-based loading)
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            # Load .env file values into os.environ
            # dotenv_values returns dict, we merge into os.environ
            env_values = dotenv_values(env_path)
            os.environ.update(env_values)

        return cls(
            database_url=os.getenv("DATABASE_URL", ""),
            vector_backend=os.getenv("VECTOR_BACKEND", "pgvector"),
            tree_strategy=os.getenv("TREE_STRATEGY", "auto_merging"),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "mock"),
            embedding_model_name=os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            milvus_url=os.getenv("MILVUS_URL", "http://localhost:19530"),
            # Phase 2: Read LLM config from local .env
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
            openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
        )

    @classmethod
    def from_env_llm_only(cls) -> dict[str, str | float]:
        """Load only LLM configuration from environment without DATABASE_URL requirement.

        Phase 3: Used by unified LLM seam to load local .env LLM values
        without requiring database configuration.

        Phase 3 Fix: Added explicit .env file loading to enable true file-based config
        (not just process environment). Works even when os.environ is cleared.

        Returns
        -------
        dict[str, str | float]
            LLM config dict: openai_api_key, llm_model, llm_temperature, openai_base_url
        """
        # Phase 3 fix: Load .env file before reading environment
        # This enables local file-based LLM config without session mutation
        #
        # Strategy: Find .env in cwd, load values into os.environ
        # This works even when os.environ was cleared (pure file-based loading)
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            # Load .env file values into os.environ
            # dotenv_values returns dict, we merge into os.environ
            env_values = dotenv_values(env_path)
            os.environ.update(env_values)

        return {
            "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
            "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
            "llm_temperature": float(os.getenv("LLM_TEMPERATURE", "0.0")),
            "openai_base_url": os.getenv("OPENAI_BASE_URL", ""),
        }
