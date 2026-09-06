"""TrialEngine adapter for the D2 v2 quantitative coverage gate.

Fails closed: transport or parsing failures raise, no TrialReport is
produced, and the caller must not extract the batch.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from llamaindex_runtime.entity.identity import CANONICAL_TYPES
from llamaindex_runtime.extraction.trial import (
    COVERAGE_THRESHOLD,
    MIN_TRIAL_SAMPLES,
    BatchHomogeneity,
    TrialReport,
)
from llamaindex_runtime.llm_openai._validation import (
    _require_nonempty_str,
    _require_unit_interval,
)
from llamaindex_runtime.llm_openai.client import (
    OpenAICompatClient,
    _parse_json_payload,
)

__all__ = ["LlmTrialEngine"]

_TRIAL_ENGINE_ID = "llm-trial-v1"
_TRIAL_PROMPT_TEMPLATE = (
    "You are an information extraction engine. Extract entities and relations"
    " from the text below. Respond with ONLY a JSON object of the shape"
    ' {{"entities": [{{"name": "...", "type": "..."}}], "relations":'
    ' [{{"subject": "...", "predicate": "...", "object": "..."}}]}} with no'
    " markdown fences and no commentary. Allowed entity types: {types}."
    " Allowed relation predicates: {predicates}. Text: {text}"
)


@dataclass(frozen=True)
class LlmTrialEngine:
    """TrialEngine adapter: one LLM extraction call per sample text.

    Fails closed: any transport, parsing, or item-shape failure raises so no
    TrialReport exists and the caller must not extract the batch (the D2 v2
    gate treats a missing report as do-not-extract).
    """

    client: OpenAICompatClient
    relation_types: frozenset[str] = field(kw_only=True)
    engine_id: str = field(kw_only=True, default=_TRIAL_ENGINE_ID)
    coverage_threshold: float = field(kw_only=True, default=COVERAGE_THRESHOLD)

    def __post_init__(self) -> None:
        if not isinstance(self.client, OpenAICompatClient):
            raise ValueError("client must be an OpenAICompatClient")
        if not isinstance(self.relation_types, frozenset):
            raise ValueError("relation_types must be a frozenset of strings")
        if not self.relation_types:
            raise ValueError("relation_types must not be empty")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.relation_types
        ):
            raise ValueError("relation_types must contain non-blank strings")
        _require_nonempty_str(self.engine_id, "engine_id")
        _require_unit_interval(self.coverage_threshold, "coverage_threshold")

    def _sample_prompt(self, text: str) -> str:
        return _TRIAL_PROMPT_TEMPLATE.format(
            types=", ".join(sorted(CANONICAL_TYPES)),
            predicates=", ".join(sorted(self.relation_types)),
            text=text,
        )

    def run_trial(self, batch_id: str, sample_texts: Sequence[str]) -> TrialReport:
        if type(batch_id) is not str or not batch_id:
            raise ValueError("batch_id must be a non-empty string")
        if isinstance(sample_texts, (str, bytes)):
            raise ValueError(
                "sample_texts must be a sequence of strings, not a bare string"
            )
        texts = list(sample_texts)
        if not texts or any(type(item) is not str or not item for item in texts):
            raise ValueError(
                "sample_texts must be a non-empty sequence of non-empty strings"
            )
        if len(texts) < MIN_TRIAL_SAMPLES:
            raise ValueError(
                "sample_texts must have at least "
                f"MIN_TRIAL_SAMPLES={MIN_TRIAL_SAMPLES} samples "
                f"(got {len(texts)})"
            )
        covered = 0
        total = 0
        uncovered: list[str] = []
        proposals: set[str] = set()
        for text in texts:
            content = self.client.complete(self._sample_prompt(text)).content
            payload = _parse_json_payload(content)
            entities = payload.get("entities")
            if not isinstance(entities, list):
                raise ValueError("llm trial output entities must be a list")
            for entry in entities:
                if not isinstance(entry, Mapping):
                    raise ValueError("llm trial entity entries must be mappings")
                name = entry.get("name")
                entity_type = entry.get("type")
                if not isinstance(name, str) or not name:
                    raise ValueError("llm trial entity name must be a string")
                if not isinstance(entity_type, str) or not entity_type:
                    raise ValueError("llm trial entity type must be a string")
                total += 1
                if entity_type in CANONICAL_TYPES:
                    covered += 1
                else:
                    uncovered.append(f"entity:{entity_type}:{name}")
                    proposals.add(entity_type)
            relations = payload.get("relations")
            if not isinstance(relations, list):
                raise ValueError("llm trial output relations must be a list")
            for entry in relations:
                if not isinstance(entry, Mapping):
                    raise ValueError("llm trial relation entries must be mappings")
                predicate = entry.get("predicate")
                if not isinstance(predicate, str) or not predicate:
                    raise ValueError("llm trial relation predicate must be a string")
                total += 1
                if predicate in self.relation_types:
                    covered += 1
                else:
                    # Unknown predicates are recorded as uncovered only;
                    # new_type_proposals is reserved for unknown ENTITY types (the entity
                    # vocabulary is closed by CANONICAL_TYPES; the relation vocabulary is
                    # caller-supplied and deliberately not extended here).
                    uncovered.append(f"relation:{predicate}")
        # Zero extractable items is NOT full coverage: without positive
        # evidence the D2 v2 gate must not unlock the PURE_UIE reward route
        # (falls back to HETEROGENEOUS / LLM-primary).
        coverage = float(covered) / float(total) if total else 0.0
        homogeneity = (
            BatchHomogeneity.SIMILAR
            if coverage >= self.coverage_threshold
            else BatchHomogeneity.HETEROGENEOUS
        )
        notes = (
            f"llm trial: {covered}/{total} in-vocabulary items"
            f" across {len(texts)} sample(s)"
        )
        return TrialReport(
            batch_id=batch_id,
            sample_texts=tuple(texts),
            coverage_ratio=coverage,
            uncovered_items=tuple(uncovered),
            new_type_proposals=tuple(sorted(proposals)),
            homogeneity=homogeneity,
            engine_id=self.engine_id,
            notes=notes,
        )
