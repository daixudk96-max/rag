"""Static capability contract for the E2A trusted disposable image (Task #87).

Two independent sources drive this contract:

1. Requirements: the exact SQL filenames in FULL_MIGRATION_CATALOG, scanned
   for `CREATE EXTENSION [IF NOT EXISTS] <name>` with a fixed regex (no SQL
   execution, no arbitrary filesystem reads, no image pulls).
2. Declared capabilities: the immutable trusted-image capability registry
   exported by the Phase 15 E2A harness types module.

The contract guarantees the active trusted image is DECLARED to supply every
extension the root migration catalog actually requires. Capabilities are never
inferred from the image name and no image internals are inspected at runtime.

TDD Phase: RED - these tests fail against the old stock postgres:15 harness.
"""

from __future__ import annotations

import importlib.resources
import re
from typing import Any, cast

import pytest

from llamaindex_runtime.registry.migration_catalog import FULL_MIGRATION_CATALOG

from . import _phase15_e2a_harness_types as _types
from ._phase15_e2a_harness_lifecycle import DisposableE2aSession

# Fixed regex: CREATE EXTENSION [IF NOT EXISTS] <identifier>
# Anchored identifiers only - no path separators, no arbitrary traversal.
_CREATE_EXTENSION_RE = re.compile(
    r"CREATE\s+EXTENSION\s+(?:IF\s+NOT\s+EXISTS\s+)?" r"([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

# Rejected images that must fail closed under the exact allowlist.
_LEGACY_STOCK_IMAGE = "postgres:15"
_ARBITRARY_IMAGE = "evil-registry.example/repo:latest"


def _required_extensions_from_catalog() -> frozenset[str]:
    """Scan exactly the SQL filenames in FULL_MIGRATION_CATALOG.

    Uses the same importlib.resources read path as the harness
    `_apply_migrations` (no arbitrary filesystem paths), mirrors the harness
    filename guard (no separators / traversal), and never executes SQL.
    """
    migrations = importlib.resources.files("llamaindex_runtime.registry.migrations")
    required: set[str] = set()
    for filename in FULL_MIGRATION_CATALOG:
        assert "/" not in filename and "\\" not in filename and ".." not in filename
        sql_text = (migrations / filename).read_text(encoding="utf-8")
        for match in _CREATE_EXTENSION_RE.finditer(sql_text):
            required.add(match.group(1).lower())
    return frozenset(required)


class TestTrustedImageCapabilityContract:
    """Two-source contract between migration catalog and declared capabilities."""

    def test_active_image_has_declared_capability_registry_entry(self) -> None:
        """Every active trusted image must have a declared capability entry."""
        assert _types.TRUSTED_DISPOSABLE_IMAGE in _types.TRUSTED_IMAGE_CAPABILITIES

    def test_registry_contains_only_the_active_trusted_image(self) -> None:
        """Registry must be single-entry: exactly the active trusted image."""
        assert list(_types.TRUSTED_IMAGE_CAPABILITIES) == [
            _types.TRUSTED_DISPOSABLE_IMAGE
        ]

    def test_capability_registry_is_immutable(self) -> None:
        """Registry must be an immutable mapping (MappingProxyType-equivalent)."""
        from types import MappingProxyType

        assert isinstance(_types.TRUSTED_IMAGE_CAPABILITIES, MappingProxyType)
        mutable_view = cast(
            dict[str, frozenset[str]], _types.TRUSTED_IMAGE_CAPABILITIES
        )
        with pytest.raises(TypeError):
            mutable_view[_ARBITRARY_IMAGE] = frozenset({"x"})

    def test_declared_capabilities_are_immutable_frozensets(self) -> None:
        """Every declared capability set must be a frozenset."""
        for capabilities in _types.TRUSTED_IMAGE_CAPABILITIES.values():
            assert type(capabilities) is frozenset

    def test_required_extensions_and_active_capabilities_are_nonempty(self) -> None:
        """Both contract sources must be non-empty (no vacuous truth)."""
        required = _required_extensions_from_catalog()
        declared = _types.TRUSTED_IMAGE_CAPABILITIES[_types.TRUSTED_DISPOSABLE_IMAGE]
        assert required, "catalog must require at least one extension"
        assert declared, "trusted image must declare at least one capability"

    def test_catalog_requirements_are_subset_of_declared_capabilities(self) -> None:
        """Every catalog-required extension must be a declared capability."""
        required = _required_extensions_from_catalog()
        declared = _types.TRUSTED_IMAGE_CAPABILITIES[_types.TRUSTED_DISPOSABLE_IMAGE]
        missing = sorted(required - declared)
        assert not missing, (
            "catalog requires extensions missing from the trusted image's "
            f"declared capabilities: {missing}"
        )

    def test_active_image_is_exact_upstream_pgvector_tag(self) -> None:
        """Active image must be the exact upstream pgvector tag (mutable tag)."""
        assert _types.TRUSTED_DISPOSABLE_IMAGE == "pgvector/pgvector:pg15"

    def test_active_image_remains_postgres_15_major(self) -> None:
        """Active image tag must remain PostgreSQL 15 major (pg15)."""
        tag = _types.TRUSTED_DISPOSABLE_IMAGE.rsplit(":", 1)[-1]
        assert tag == "pg15", f"trusted image tag must be pg15, got {tag!r}"

    def test_constructor_accepts_active_constant_without_starting_docker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Constructor accepts the active constant and never starts Docker."""
        monkeypatch.setenv(_types.AUTHORIZATION_FLAG, "separately-authorized")
        runner_called = False

        def runner(*args: Any, **kwargs: Any) -> Any:
            nonlocal runner_called
            runner_called = True
            raise AssertionError("Docker must not be started by construction")

        session = DisposableE2aSession(
            container_name="contract-test-container",
            password="test-password",
            image=_types.TRUSTED_DISPOSABLE_IMAGE,
            runner=runner,
        )
        assert session._image == _types.TRUSTED_DISPOSABLE_IMAGE
        assert runner_called is False

    def test_constructor_rejects_legacy_stock_postgres15_fail_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Old stock postgres:15 must fail closed at construction."""
        monkeypatch.setenv(_types.AUTHORIZATION_FLAG, "separately-authorized")
        with pytest.raises(ValueError):
            DisposableE2aSession(
                container_name="contract-test-container",
                password="test-password",
                image=_LEGACY_STOCK_IMAGE,
            )

    def test_validation_rejects_arbitrary_image_strings(self) -> None:
        """Exact allowlisting: arbitrary strings must all fail closed."""
        for image in (
            _ARBITRARY_IMAGE,
            "ubuntu:24.04",
            "postgres:16",
            "postgres:latest",
            "",
            "pgvector/pgvector:pg15@sha256:0000000000000000000000000000000000000000000000000000000000000000",
        ):
            with pytest.raises(ValueError):
                _types._validate_disposable_image(image)

    def test_rejection_error_is_fixed_and_never_echoes_attempted_image(
        self,
    ) -> None:
        """Error text must be fixed/generic and never echo the attempted image."""
        with pytest.raises(ValueError) as excinfo:
            _types._validate_disposable_image(_ARBITRARY_IMAGE)
        message = str(excinfo.value)
        assert message == "Untrusted image - only pgvector/pgvector:pg15 allowed"
        assert _ARBITRARY_IMAGE not in message

        with pytest.raises(ValueError) as excinfo_legacy:
            _types._validate_disposable_image(_LEGACY_STOCK_IMAGE)
        legacy_message = str(excinfo_legacy.value)
        assert _LEGACY_STOCK_IMAGE not in legacy_message
