"""Wave-1 tenth-remediation contract extraction regressions."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import MappingProxyType

import pytest

from llamaindex_runtime.okf import e2a_contracts as contracts

_EXPECTED_ALL = [
    "DmlRecorder",
    "E2A_GLOBAL_SCOPE_VERSION_ID",
    "E2aDesiredState",
    "E2aEvidenceObject",
    "E2aEvidenceReference",
    "E2aManualFact",
    "E2aOwnershipFact",
    "E2aParent",
    "E2aReconciliationResult",
    "E2aSpan",
    "canonical_json",
    "canonical_json_sha256",
    "deterministic_id",
]
_PRIVATE_HELPERS = (
    "_canonical_value",
    "_frozen_mapping",
    "_string_key",
    "_unicode_scalar",
    "_freeze_json",
    "_tuple",
    "_frozen_json_tuple",
    "_typed",
    "_counts",
    "_uuid",
    "_digest",
    "_path",
    "_unique",
)
_PUBLIC_CLASSES = (
    "DmlRecorder",
    "E2aDesiredState",
    "E2aEvidenceObject",
    "E2aEvidenceReference",
    "E2aManualFact",
    "E2aOwnershipFact",
    "E2aParent",
    "E2aReconciliationResult",
    "E2aSpan",
)


def _primitives() -> object:
    return import_module("llamaindex_runtime.okf.e2a_contract_primitives")


def _line_count(module: object) -> int:
    return len(Path(module.__file__).read_text(encoding="utf-8").splitlines())  # type: ignore[attr-defined]


def test_contract_modules_stay_under_the_physical_line_cap() -> None:
    assert _line_count(contracts) < 800

    primitives = _primitives()
    assert _line_count(primitives) < 800


def test_current_public_exports_and_legacy_private_helpers_remain_accessible() -> None:
    primitives = _primitives()

    assert contracts.__all__ == _EXPECTED_ALL
    for name in (
        "E2A_NAMESPACE",
        "E2A_GLOBAL_SCOPE_VERSION_ID",
        "Outcome",
        *_EXPECTED_ALL,
    ):
        assert hasattr(contracts, name)
    for name in _PRIVATE_HELPERS:
        assert getattr(contracts, name) is getattr(primitives, name)


def test_public_class_module_identities_remain_in_the_legacy_module() -> None:
    for name in _PUBLIC_CLASSES:
        assert getattr(contracts, name).__module__ == contracts.__name__


def test_canonical_behavior_and_freezing_are_preserved_through_reexports() -> None:
    primitives = _primitives()
    value = {"z": ["猫", {"ready": True}], "a": 2}

    assert contracts.canonical_json(value) == '{"a":2,"z":["猫",{"ready":true}]}'
    assert primitives._canonical_value(value) == value  # noqa: SLF001
    frozen = contracts._frozen_mapping(value, "metadata")  # noqa: SLF001
    assert isinstance(frozen, MappingProxyType)
    assert frozen["z"] == ("猫", MappingProxyType({"ready": True}))
    with pytest.raises(TypeError):
        frozen["a"] = 3  # type: ignore[index]


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    (
        ("_canonical_value", (object(),), "JSON value is not canonical"),
        ("_frozen_mapping", ([], "metadata"), "metadata must be a mapping"),
        (
            "_unicode_scalar",
            ("\ud800", "label"),
            "label must be a Unicode scalar string",
        ),
        ("_freeze_json", (float("inf"),), "JSON values must be finite"),
        ("_tuple", ({"unexpected"}, "records"), "records must be a tuple"),
        (
            "_frozen_json_tuple",
            ({"unexpected"}, "records"),
            "records must be a tuple",
        ),
        ("_typed", (("wrong",), int, "records"), "records has invalid values"),
        (
            "_counts",
            ({"writes": -1},),
            "DML counts must be non-negative integer mappings",
        ),
        ("_uuid", ("not-a-uuid", "record_id"), "record_id must be a UUID"),
        (
            "_digest",
            ("A" * 64, "source_digest"),
            "source_digest must be a lowercase SHA-256 digest",
        ),
        ("_path", ("../escape.md",), "safe relative path is required"),
        (
            "_unique",
            (("same", "same"), lambda item: item, "record"),
            "duplicate record identity",
        ),
    ),
)
def test_reexported_private_helper_errors_remain_exact(
    name: str, arguments: tuple[object, ...], message: str
) -> None:
    primitives = _primitives()

    for module in (contracts, primitives):
        with pytest.raises(ValueError, match=f"^{message}$"):
            getattr(module, name)(*arguments)
