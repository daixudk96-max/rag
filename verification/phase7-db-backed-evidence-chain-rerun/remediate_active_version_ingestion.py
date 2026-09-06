"""Remediation script to complete ingestion for Phase 7 active version.

The active version a376679b-3a95-4724-a31f-ece0c9fa35b8 was registered
but never parsed (processing_status='registered', parsed_at=None),
resulting in zero canonical_spans which blocks Phase 7 DB_EVIDENCE_READY.

This script:
1. Reads the source document from the registered documents table
2. Parses it using DoclingIngestor
3. Writes canonical_spans to the database
4. Updates processing_status to 'parsed'
5. Verifies Phase 7 readiness after remediation
"""
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

from llamaindex_runtime.ingestion.docling_ingestor import DoclingIngestor  # noqa: E402
from llamaindex_runtime.registry.postgres_adapter import PostgresRegistryWriter  # noqa: E402

ACTIVE_VERSION_ID = uuid.UUID("a376679b-3a95-4724-a31f-ece0c9fa35b8")


def main() -> int:
    """Complete ingestion for the active version and verify Phase 7 readiness."""
    import os

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not configured", file=sys.stderr)
        return 2

    try:
        with psycopg.connect(db_url) as conn:
            # Step 1: Get source document path
            cur = conn.cursor()
            cur.execute(
                """SELECT d.source_uri, d.title
                   FROM documents d
                   JOIN document_versions dv ON d.doc_id = dv.doc_id
                   WHERE dv.version_id = %s""",
                (str(ACTIVE_VERSION_ID),),
            )
            row = cur.fetchone()
            if not row:
                print(
                    f"ERROR: Version {ACTIVE_VERSION_ID} not found in database",
                    file=sys.stderr,
                )
                return 2

            source_uri = row[0]
            title = row[1]
            print(f"Source URI: {source_uri}")
            print(f"Title: {title}")

            # Convert file:// URI to Path
            from urllib.parse import urlparse, unquote

            parsed_uri = urlparse(source_uri)
            if parsed_uri.scheme != "file":
                print(
                    f"ERROR: Unsupported source URI scheme: {parsed_uri.scheme}",
                    file=sys.stderr,
                )
                return 2

            source_path = Path(unquote(parsed_uri.path))
            if not source_path.exists():
                print(
                    f"ERROR: Source file not found: {source_path}",
                    file=sys.stderr,
                )
                return 2

            print(f"Source path resolved: {source_path}")

            # Step 2: Parse document using DoclingIngestor
            print("\n[Step 1] Parsing document...")
            ingestor = DoclingIngestor()
            registry_writer = PostgresRegistryWriter(conn)

            # Get doc_id from version
            cur.execute(
                "SELECT doc_id FROM document_versions WHERE version_id = %s",
                (str(ACTIVE_VERSION_ID),),
            )
            doc_id = uuid.UUID(str(cur.fetchone()[0]))

            result = ingestor.ingest(
                source_path, doc_id=doc_id, version_id=ACTIVE_VERSION_ID
            )

            print(f"Parsed {len(result.spans)} spans")

            # Step 3: Write canonical_spans to database
            print("\n[Step 2] Writing canonical_spans...")
            registry_writer.write_spans(version_id=ACTIVE_VERSION_ID, spans=result.spans)

            # Step 4: Update processing_status
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

            # Step 5: Verify canonical_spans count
            print("\n[Step 4] Verifying canonical_spans...")
            cur.execute(
                "SELECT COUNT(*) FROM canonical_spans WHERE version_id = %s",
                (str(ACTIVE_VERSION_ID),),
            )
            count = cur.fetchone()[0]
            print(f"canonical_spans count after remediation: {count}")

            if count == 0:
                print("ERROR: canonical_spans still zero after remediation", file=sys.stderr)
                return 2

            print(f"\n✓ Remediation complete: {count} canonical_spans written")
            print(f"✓ processing_status updated to 'parsed'")
            print(f"\nPhase 7 should now be DB_EVIDENCE_READY")

            return 0

    except psycopg.OperationalError as exc:
        print(f"ERROR: Database connection failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: Remediation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())