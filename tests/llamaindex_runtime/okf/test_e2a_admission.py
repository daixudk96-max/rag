from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from llamaindex_runtime.okf import e2a_admission
from llamaindex_runtime.okf.raw_pair import RawPairSnapshot
from llamaindex_runtime.okf.rooted_open import BundleAuthority
from llamaindex_runtime.okf.sidecar import SpanRecord, SpanSidecar


def _snapshot(doc_id: str, version_id: str, span_id: str) -> RawPairSnapshot:
    return RawPairSnapshot(
        markdown_bytes=b"---\ntype: raw\n---\nbody\n",
        sidecar_bytes=b"{}",
        manifest=None,  # type: ignore[arg-type]
        frontmatter={},
        body="body",
        sidecar=SpanSidecar(
            schema_version=1,
            doc_id=doc_id,
            version_id=version_id,
            spans=(SpanRecord(span_id, None, (), 0, "body"),),
        ),
    )


def _authority(tmp_path: Path) -> BundleAuthority:
    return BundleAuthority(tmp_path)


def _write_raw_triplet(pair: Path) -> None:
    pair.write_text("{}", encoding="utf-8")
    slug = pair.name.removesuffix(".pair.json")
    (pair.parent / f"{slug}.md").write_text(
        "---\ntype: raw\n---\nbody\n", encoding="utf-8"
    )
    (pair.parent / f"{slug}.spans.json").write_text("{}", encoding="utf-8")


def test_admission_uses_strict_reader_for_nested_manifest_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc_id, version_id, span_id = (str(uuid4()), str(uuid4()), str(uuid4()))
    pair = tmp_path / "raw" / "reports" / "2026" / "cat.pair.json"
    pair.parent.mkdir(parents=True)
    _write_raw_triplet(pair)
    calls: list[tuple[object, tuple[str, ...]]] = []

    def fake_read(authority: object, parts: tuple[str, ...]) -> RawPairSnapshot:
        calls.append((authority, parts))
        return _snapshot(doc_id, version_id, span_id)

    monkeypatch.setattr(e2a_admission, "read_raw_pair", fake_read)
    with _authority(tmp_path) as authority:
        state = e2a_admission.admit_e2a_corpus(authority)

    assert calls == [(calls[0][0], ("raw", "reports", "2026", "cat.md"))]
    assert state.canonical_spans[0].span_id == span_id
    assert (
        state.corpus_manifest["artifacts"][0]["path"]
        == "raw/reports/2026/cat.pair.json"
    )


def test_admission_manifest_is_reorder_invariant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = (str(uuid4()), str(uuid4()), str(uuid4()))
    second = (str(uuid4()), str(uuid4()), str(uuid4()))
    for name in ("zebra", "ant"):
        path = tmp_path / "raw" / f"{name}.pair.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_raw_triplet(path)

    def fake_read(_: object, parts: tuple[str, ...]) -> RawPairSnapshot:
        values = first if parts[-1] == "ant.md" else second
        return _snapshot(*values)

    monkeypatch.setattr(e2a_admission, "read_raw_pair", fake_read)
    with _authority(tmp_path) as authority:
        state = e2a_admission.admit_e2a_corpus(authority)

    assert [parent.relative_path for parent in state.parents] == [
        "raw/ant.pair.json",
        "raw/zebra.pair.json",
    ]
    assert state.corpus_manifest_sha256 == e2a_admission.admit_e2a_corpus_hash(state)


@pytest.mark.parametrize(
    "relative_path",
    ("templates/entity.md", "synthesis/result.md", "AGENTS.md", ".hidden/fact.md"),
)
def test_admission_excludes_reserved_and_support_paths(
    tmp_path: Path, relative_path: str
) -> None:
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# not a fact", encoding="utf-8")

    with _authority(tmp_path) as authority:
        with pytest.raises(ValueError, match="empty"):
            e2a_admission.admit_e2a_corpus(authority)


def test_admission_fails_closed_before_return_for_duplicate_document_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = (str(uuid4()), str(uuid4()), str(uuid4()))
    for name in ("one", "two"):
        path = tmp_path / "raw" / f"{name}.pair.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_raw_triplet(path)
    monkeypatch.setattr(e2a_admission, "read_raw_pair", lambda *_: _snapshot(*values))

    with _authority(tmp_path) as authority:
        with pytest.raises(ValueError, match="duplicate"):
            e2a_admission.admit_e2a_corpus(authority)


def test_admission_rejects_partial_invalid_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("valid", "invalid"):
        path = tmp_path / "raw" / f"{name}.pair.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_raw_triplet(path)
    valid = (str(uuid4()), str(uuid4()), str(uuid4()))

    def fake_read(_: object, parts: tuple[str, ...]) -> RawPairSnapshot:
        if parts[-1] == "invalid.md":
            raise ValueError("pair_manifest_invalid")
        return _snapshot(*valid)

    monkeypatch.setattr(e2a_admission, "read_raw_pair", fake_read)
    with _authority(tmp_path) as authority:
        with pytest.raises(ValueError, match="pair_manifest_invalid"):
            e2a_admission.admit_e2a_corpus(authority)


class _RetryBudgetAuthority:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def read_manifest(self, _: tuple[str, ...]) -> bytes:
        self.calls.append("manifest")
        return b"m"

    def read_document(self, _: tuple[str, ...], maximum: int | None = None) -> bytes:
        self.calls.append(f"document:{maximum}")
        return b"d"

    def read_sidecar(self, _: tuple[str, ...]) -> bytes:
        self.calls.append("sidecar")
        return b"s"


def test_mdsm_retry_budget_reserves_each_attempt_and_refunds_successful_bytes() -> None:
    source = _RetryBudgetAuthority()
    authority = e2a_admission._BudgetedAuthority(source)
    authority._ledger = e2a_admission._ReadLedger(  # noqa: SLF001
        {
            "manifest": 2 * 16 * 1024,
            "markdown": 64 * 1024 * 1024,
            "sidecar": 64 * 1024 * 1024,
            "manual": 64 * 1024 * 1024,
        },
        {"manifest": 0, "markdown": 0, "sidecar": 0, "manual": 0},
    )
    parts = ("raw", "source.md")

    authority.read_manifest(parts)
    authority.read_document(parts)
    authority.read_sidecar(("raw", "source.spans.json"))
    authority.read_manifest(parts)

    assert authority._ledger.used == {  # noqa: SLF001
        "manifest": 2,
        "markdown": 1,
        "sidecar": 1,
        "manual": 0,
    }
    assert source.calls == [
        "manifest",
        f"document:{16 * 1024 * 1024}",
        "sidecar",
        "manifest",
    ]


class _OversizedRawSourceAuthority:
    def __init__(self) -> None:
        self.maximums: list[int | None] = []

    def read_document(self, _: tuple[str, ...], maximum: int | None = None) -> bytes:
        self.maximums.append(maximum)
        raise ValueError("document exceeds maximum size")


def test_raw_markdown_read_uses_16_mib_per_file_cap_and_fails_closed() -> None:
    source = _OversizedRawSourceAuthority()
    authority = e2a_admission._BudgetedAuthority(source)  # noqa: SLF001

    with pytest.raises(ValueError, match="^document exceeds maximum size$"):
        authority.read_document(("raw", "oversized.md"))

    assert source.maximums == [16 * 1024 * 1024]


def test_evidence_references_reject_malformed_and_duplicate_values_before_lookup() -> (
    None
):
    document_id, version_id, span_id = str(uuid4()), str(uuid4()), str(uuid4())
    parent = e2a_admission.E2aParent(
        document_id, version_id, "raw/source.pair.json", "a" * 64
    )
    span = e2a_admission.E2aSpan(document_id, version_id, span_id, 0, "body")
    natural_key = e2a_admission.canonical_json(
        {"entity_type": "animal", "title": "cat"}
    )
    fact = e2a_admission.E2aManualFact(
        e2a_admission.deterministic_id("entity", natural_key),
        "entity",
        "entities/cat.md",
        "b" * 64,
        natural_key=natural_key,
    )
    ownership = e2a_admission.E2aOwnershipFact.create(
        relative_path=fact.relative_path,
        fact_kind="entity",
        fact_id=fact.fact_id,
        source_digest=fact.source_digest,
    )
    pairs = ((parent, (span,), {}),)
    malformed = {
        "document_id": [],
        "version_id": version_id,
        "span_id": span_id,
    }

    with pytest.raises(ValueError, match="^e2a_admission_evidence_invalid$"):
        e2a_admission._evidence_links({"evidence": [malformed]}, fact, ownership, pairs)
    with pytest.raises(ValueError, match="^e2a_admission_evidence_invalid$"):
        e2a_admission._evidence_links(
            {
                "evidence": [
                    {
                        "document_id": document_id,
                        "version_id": version_id,
                        "span_id": span_id,
                    },
                    {
                        "document_id": document_id,
                        "version_id": version_id,
                        "span_id": span_id,
                    },
                ]
            },
            fact,
            ownership,
            pairs,
        )


class _ManualFactAuthority:
    def read_document(self, _: tuple[str, ...], __: int) -> bytes:
        return b"---\ntype: entity\n---\nbody"


def test_manual_admission_materializes_one_evidence_object_per_target_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = str(uuid4())
    first_version, second_version = str(uuid4()), str(uuid4())
    first_span, second_span, third_span = str(uuid4()), str(uuid4()), str(uuid4())
    natural_key = e2a_admission.canonical_json(
        {"title": "cat", "entity_type": "animal"}
    )
    fact_id = e2a_admission.deterministic_id("entity", natural_key)
    frontmatter = {
        "type": "entity",
        "title": "cat",
        "entity_type": "animal",
        "evidence": [
            {
                "document_id": document_id,
                "version_id": first_version,
                "span_id": first_span,
            },
            {
                "document_id": document_id,
                "version_id": first_version,
                "span_id": second_span,
            },
            {
                "document_id": document_id,
                "version_id": second_version,
                "span_id": third_span,
            },
        ],
    }
    contract = e2a_admission.EntityFrontmatterContract(
        "entity", "cat", "2026-01-01T00:00:00Z", fact_id, "animal"
    )
    parents = (
        e2a_admission.E2aParent(
            document_id, first_version, "raw/first.pair.json", "a" * 64
        ),
        e2a_admission.E2aParent(
            document_id, second_version, "raw/second.pair.json", "b" * 64
        ),
    )
    pairs = (
        (
            parents[0],
            (
                e2a_admission.E2aSpan(
                    document_id, first_version, first_span, 0, "first"
                ),
                e2a_admission.E2aSpan(
                    document_id, first_version, second_span, 6, "second"
                ),
            ),
            {
                "kind": "raw_pair",
                "path": "raw/first.pair.json",
                "identity": f"{document_id}:{first_version}",
                "canonical_hash": "a" * 64,
            },
        ),
        (
            parents[1],
            (
                e2a_admission.E2aSpan(
                    document_id, second_version, third_span, 0, "third"
                ),
            ),
            {
                "kind": "raw_pair",
                "path": "raw/second.pair.json",
                "identity": f"{document_id}:{second_version}",
                "canonical_hash": "b" * 64,
            },
        ),
    )
    monkeypatch.setattr(
        e2a_admission, "load_strict_e2a_frontmatter", lambda _: (frontmatter, "")
    )
    monkeypatch.setattr(e2a_admission, "validate_known_frontmatter", lambda _: contract)

    admitted = e2a_admission._admit_fact(
        _ManualFactAuthority(), ("entity", ("entities", "cat.md")), pairs
    )
    state = e2a_admission._desired_state(pairs, (admitted,))

    assert admitted[1] is not None
    assert len(state.evidence_objects) == 2
    link_ids = [link.evidence_id for link in state.evidence_links]
    assert len(set(link_ids)) == 2
    assert sorted(link_ids.count(value) for value in set(link_ids)) == [1, 2]


def test_admission_path_filters_and_ledger_argument_validation_fail_closed() -> None:
    with pytest.raises(ValueError, match="unsupported_raw"):
        e2a_admission._raw_pair_paths((("raw", "unexpected.txt"),))
    with pytest.raises(ValueError, match="raw_set_invalid"):
        e2a_admission._raw_pair_paths((("raw", "orphan.md"),))
    with pytest.raises(ValueError, match="unsupported_manual"):
        e2a_admission._manual_fact_paths((("entities", "unexpected.txt"),))
    ledger = e2a_admission._ReadLedger({"manual": 1}, {"manual": 0})

    with pytest.raises(ValueError, match="^e2a_admission_resource_limit$"):
        ledger.read("manual", lambda _parts, _maximum: b"", ("entities", "x.md"), 0)
