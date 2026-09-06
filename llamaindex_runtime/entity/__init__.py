"""E2b raw-corpus entity-layer contracts (pure, dependency-free).

Phase 16-02 frozen contract layer. Importing this package imports only the
stdlib plus the existing OKF E2a contract helpers; it never imports
modelscope, torch, jieba, or any persistence/network/database code.
"""

from .contracts import (
    CONFIDENCE_KINDS,
    E2B_NAMESPACE,
    INPUT_KINDS,
    MENTION_SOURCES,
    ConfidenceKind,
    CorpusSpanInput,
    ExtractionInput,
    InputKind,
    MentionCandidate,
    MentionSource,
    QueryTextInput,
    canonical_json,
    canonical_json_sha256,
    deterministic_id,
)
from .merger import (
    CandidateOutcome,
    MergedMentions,
    OUTCOME_STATUSES,
    OutcomeStatus,
    merge_mentions,
)
from .dictionary_loader import (
    DictionarySourceError,
    load_dictionary_candidates,
)
from .frontmatter_supplement import (
    FrontmatterSourceError,
    frontmatter_declared_candidates,
)
from .failure_audit import (
    AuditWriteResult,
    E2bFailureAudit,
)
from .materialization_repository import (
    E2bDesiredLink,
    E2bDesiredMention,
    E2bDesiredState,
    E2bDmlRecorder,
    E2bDocumentScope,
    E2bMaterializationRepository,
    E2bReconciliationResult,
)
from .resolution import (
    PRIORITY_ORDER,
    ResolutionDecision,
    ResolutionInputError,
    ResolutionResult,
    resolve_candidates,
)
from .coref_rules import (
    CorefCluster,
    CorefClusterSet,
    build_coref_clusters,
)
from .segmenter import Segment, segment_text
from .extractor import (
    EntityExtractor,
    build_entity_extractor,
)

__all__ = [
    "CONFIDENCE_KINDS",
    "CorefCluster",
    "CorefClusterSet",
    "AuditWriteResult",
    "CandidateOutcome",
    "DictionarySourceError",
    "E2B_NAMESPACE",
    "E2bDesiredLink",
    "E2bDesiredMention",
    "E2bDesiredState",
    "E2bDmlRecorder",
    "E2bDocumentScope",
    "E2bFailureAudit",
    "E2bMaterializationRepository",
    "E2bReconciliationResult",
    "EntityExtractor",
    "FrontmatterSourceError",
    "INPUT_KINDS",
    "MENTION_SOURCES",
    "MergedMentions",
    "OUTCOME_STATUSES",
    "OutcomeStatus",
    "PRIORITY_ORDER",
    "ResolutionDecision",
    "ResolutionInputError",
    "ResolutionResult",
    "Segment",
    "ConfidenceKind",
    "CorpusSpanInput",
    "ExtractionInput",
    "InputKind",
    "MentionCandidate",
    "MentionSource",
    "QueryTextInput",
    "canonical_json",
    "canonical_json_sha256",
    "deterministic_id",
    "build_coref_clusters",
    "build_entity_extractor",
    "frontmatter_declared_candidates",
    "load_dictionary_candidates",
    "merge_mentions",
    "resolve_candidates",
    "segment_text",
]
