"""Remediation script to complete ingestion for Phase 7 active version.

The active version a376679b-3a95-4724-a31f-ece0c9fa35b8 was registered
but never parsed (processing_status='registered', parsed_at=None),
resulting in zero canonical_spans which blocks Phase 7 DB_EVIDENCE_READY.

This script uses the known document path directly and completes the ingestion.
"""

# ruff: noqa: E402

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load .env before database access
env_path = REPO_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)

import psycopg  # noqa: E402

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter

ACTIVE_VERSION_ID = uuid.UUID("a376679b-3a95-4724-a31f-ece0c9fa35b8")
KNOWN_DOCUMENT_PATH = REPO_ROOT / "PageIndex完整功能分析与集成方案.md"


def main() -> int:
    """Complete ingestion for the active version and verify Phase 7 readiness."""
    import os

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not configured", file=sys.stderr)
        return 2

    if not KNOWN_DOCUMENT_PATH.exists():
        print(
            f"ERROR: Known document path not found: {KNOWN_DOCUMENT_PATH}",
            file=sys.stderr,
        )
        return 2

    print(f"Using known document path: {KNOWN_DOCUMENT_PATH.name}")

    try:
        with psycopg.connect(db_url) as conn:
            # Step 1: Parse document using DoclingIngestor
            print("\n[Step 1] Parsing document...")
            ingestor = DoclingIngestor()
            registry_writer = PostgresRegistryWriter(conn)

            # Get doc_id from version
            cur = conn.cursor()
            cur.execute(
                "SELECT doc_id FROM document_versions WHERE version_id = %s",
                (str(ACTIVE_VERSION_ID),),
            )
            doc_id = uuid.UUID(str(cur.fetchone()[0]))

            result = ingestor.ingest(
                KNOWN_DOCUMENT_PATH, doc_id=doc_id, version_id=ACTIVE_VERSION_ID
            )

            print(f"Parsed {len(result.spans)} spans")

            # Step 2: Write canonical_spans to database
            print("\n[Step 2] Writing canonical_spans...")
            registry_writer.write_spans(
                version_id=ACTIVE_VERSION_ID, spans=result.spans
            )

            # Step 3: Update processing_status
            print("\n[Step 3] Updating processing_status...")
            cur.execute(
                """UPDATE document_versions
                   SET processing_status = 'parsed',
                       parsed_at = NOW(),
                       processing_status_updated_at = NOW()
                   WHERE version_id = %s""",
                (str(ACTIVE_VERSION_ID),),
            )
            conn.commit()

            # Step 4: Verify canonical_spans count
            print("\n[Step 4] Verifying canonical_spans...")
            cur.execute(
                "SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
                (str(ACTIVE_VERSION_ID),),
            )
            count = cur.fetchone()[0]
            print(f"canonical_spans count after remediation: {count}")

            if count == 0:
                print(
                    "ERROR: canonical_spans still zero after remediation",
                    file=sys.stderr,
                )
                return 2

            print(f"\n✓ Remediation complete: {count} canonical_spans written")
            print("✓ processing_status updated to 'parsed'")
            print("\nRerun Phase 7 evidence-chain verification next")

            return 0

    except psycopg.OperationalError as exc:
        print(
            f"ERROR: Database connection failed: {type(exc).__name__}", file=sys.stderr
        )
        return 2
    except Exception as exc:
        print(f"ERROR: Remediation failed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
