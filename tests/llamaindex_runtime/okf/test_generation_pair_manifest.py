from __future__ import annotations

import json

import pytest

from llamaindex_runtime.okf.generation_manifest import GenerationManifest


def _manifest() -> GenerationManifest:
    return GenerationManifest.create(
        markdown_file="report.md",
        markdown_bytes="正文\n".encode(),
        sidecar_file="report.spans.json",
        sidecar_bytes=b'{"schema_version":1}',
        canonical_hash="a" * 64,
    )


def test_manifest_is_deterministic_utf8_and_fixed_field_order() -> None:
    raw = _manifest().to_bytes()
    assert raw == _manifest().to_bytes()
    assert raw.endswith(b"\n")
    assert raw.decode("utf-8") == (
        '{"canonical_hash":"'
        + "a" * 64
        + '","markdown_file":"report.md","markdown_sha256":"'
        + _manifest().markdown_sha256
        + '","schema_version":1,"sidecar_file":"report.spans.json",'
        + '"sidecar_sha256":"'
        + _manifest().sidecar_sha256
        + '"}\n'
    )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":1,"schema_version":1}',
        b'{"schema_version":1,"unknown":true}',
        b'{"schema_version":"1"}',
        b'{"schema_version":1,"markdown_file":"../x.md"}',
        b'{"schema_version":1,"markdown_file":"x.md","markdown_sha256":"A"}',
        b"\xff",
    ],
)
def test_manifest_rejects_malformed_duplicate_unknown_and_invalid_utf8(
    raw: bytes,
) -> None:
    with pytest.raises(ValueError, match="^pair_manifest_invalid$") as error:
        GenerationManifest.from_bytes(raw)
    assert error.value.__cause__ is None


def test_manifest_rejects_empty_shared_basename() -> None:
    raw = (
        _manifest()
        .to_bytes()
        .replace(b'"report.md"', b'".md"')
        .replace(b'"report.spans.json"', b'".spans.json"')
    )

    with pytest.raises(ValueError, match="^pair_manifest_invalid$"):
        GenerationManifest.from_bytes(raw)


def test_manifest_rejects_oversize_payload() -> None:
    with pytest.raises(ValueError, match="^pair_manifest_invalid$"):
        GenerationManifest.from_bytes(b" " * (16 * 1024 + 1))


@pytest.mark.parametrize(
    "raw",
    (
        lambda manifest: json.dumps(
            json.loads(manifest.to_bytes()), indent=2, sort_keys=True
        ).encode()
        + b"\n",
        lambda manifest: json.dumps(
            {
                field: getattr(manifest, field)
                for field in reversed(manifest.__dataclass_fields__)
            },
            separators=(",", ":"),
        ).encode()
        + b"\n",
        lambda manifest: manifest.to_bytes().replace(b":", b": ", 1),
        lambda manifest: manifest.to_bytes()[:-1],
        lambda manifest: manifest.to_bytes().replace(b"\n", b"\r\n"),
        lambda manifest: manifest.to_bytes() + b" ",
    ),
)
def test_manifest_rejects_noncanonical_json_bytes(raw) -> None:
    with pytest.raises(ValueError, match="^pair_manifest_invalid$") as error:
        GenerationManifest.from_bytes(raw(_manifest()))
    assert error.value.__cause__ is None


def test_manifest_requires_exact_schema_not_json_coercion() -> None:
    payload = json.loads(_manifest().to_bytes())
    payload["canonical_hash"] = "f" * 64
    noncanonical = json.dumps(payload).encode()

    with pytest.raises(ValueError, match="^pair_manifest_invalid$"):
        GenerationManifest.from_bytes(noncanonical)


@pytest.mark.parametrize(
    "member_name",
    ("Report", ".report", "report name", "report_1", "x" * 101),
)
def test_manifest_rejects_non_slug_member_basenames(member_name: str) -> None:
    payload = json.loads(_manifest().to_bytes())
    payload["markdown_file"] = f"{member_name}.md"
    payload["sidecar_file"] = f"{member_name}.spans.json"
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode() + b"\n"

    with pytest.raises(ValueError, match="^pair_manifest_invalid$"):
        GenerationManifest.from_bytes(raw)


def test_manifest_accepts_legal_kebab_case_member_basename() -> None:
    manifest = GenerationManifest.create(
        markdown_file="report-2026.md",
        markdown_bytes=b"markdown",
        sidecar_file="report-2026.spans.json",
        sidecar_bytes=b"sidecar",
        canonical_hash="a" * 64,
    )

    assert GenerationManifest.from_bytes(manifest.to_bytes()) == manifest


@pytest.mark.parametrize(
    "encoded_version",
    (b"1.0", b"true", b'"1"', b"2"),
)
def test_manifest_rejects_non_integer_or_wrong_schema_version(
    encoded_version: bytes,
) -> None:
    raw = (
        _manifest()
        .to_bytes()
        .replace(b'"schema_version":1', b'"schema_version":' + encoded_version)
    )

    with pytest.raises(ValueError, match="^pair_manifest_invalid$") as raised:
        GenerationManifest.from_bytes(raw)

    assert raised.value.__cause__ is None


def test_manifest_accepts_canonical_integer_schema_version_one_bytes() -> None:
    raw = _manifest().to_bytes()

    assert GenerationManifest.from_bytes(raw) == _manifest()
