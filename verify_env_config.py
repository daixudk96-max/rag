#!/usr/bin/env python
"""Phase 1 validation input freeze verifier.

Checks .env configuration without printing secrets.
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from llamaindex_runtime.config import RuntimeSettings


def check_env_configuration() -> dict:
    """Verify .env configuration for real validation.

    Returns
    -------
    dict
        Configuration status report.
    """
    # Load LLM config from .env
    llm_config = RuntimeSettings.from_env_llm_only()

    # Check OPENAI_API_KEY (True/False only, never print value)
    api_key_present = bool(llm_config["openai_api_key"])

    # Check REAL_VALIDATION_DOCUMENT_PATH
    # Need to load from .env directly since RuntimeSettings doesn't include this field
    env_path = Path.cwd() / ".env"
    doc_path = ""
    query_text = ""

    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("REAL_VALIDATION_DOCUMENT_PATH="):
                    doc_path = line.split("=", 1)[1].strip()
                elif line.startswith("REAL_VALIDATION_QUERY="):
                    query_text = line.split("=", 1)[1].strip()

    doc_path_present = bool(doc_path) and doc_path != "__FILL_REAL_DOCUMENT_PATH__"
    query_text_present = bool(query_text) and query_text != "__FILL_REAL_QUERY__"

    return {
        "credential_status": "set" if api_key_present else "missing",
        "api_key_present": api_key_present,
        "document_path": doc_path if doc_path_present else "MISSING",
        "document_path_present": doc_path_present,
        "query_text": query_text if query_text_present else "MISSING",
        "query_text_present": query_text_present,
        "all_required_fields_present": api_key_present and doc_path_present and query_text_present,
    }


def main():
    """Main entry point."""
    result = check_env_configuration()

    print("=" * 60)
    print("Phase 1 - Validation Input Freeze Status")
    print("=" * 60)
    print()
    print(f"Credential Status: {result['credential_status']}")
    print(f"OPENAI_API_KEY Present: {result['api_key_present']}")
    print()
    print(f"REAL_VALIDATION_DOCUMENT_PATH Present: {result['document_path_present']}")
    if result['document_path_present']:
        print(f"Document Path: {result['document_path']}")
    print()
    print(f"REAL_VALIDATION_QUERY Present: {result['query_text_present']}")
    if result['query_text_present']:
        print(f"Query Text: {result['query_text']}")
    print()
    print("=" * 60)

    if result["all_required_fields_present"]:
        print("[PASS] ALL REQUIRED FIELDS PRESENT")
        print("Ready to proceed to Phase 2: Credentialed donor execution")
        return 0
    else:
        print("[BLOCKER] MISSING REQUIRED FIELDS")
        print()
        print("Missing fields:")
        if not result["api_key_present"]:
            print("  - OPENAI_API_KEY (must be set in .env)")
        if not result["document_path_present"]:
            print("  - REAL_VALIDATION_DOCUMENT_PATH (must be set in .env)")
        if not result["query_text_present"]:
            print("  - REAL_VALIDATION_QUERY (must be set in .env)")
        print()
        print("Please fill these fields in .env file before continuing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())