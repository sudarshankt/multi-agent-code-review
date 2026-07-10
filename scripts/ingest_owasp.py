#!/usr/bin/env python3
"""Ingest OWASP knowledge base into ChromaDB.

Gracefully skips if sentence-transformers or chromadb are unavailable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("ERROR: sentence-transformers not installed. Run: pip install -e '.[rag]'")
    sys.exit(1)

from src.core.logging import configure_logging, get_logger
from src.infrastructure.chromadb.client import upsert_documents

logger = get_logger(__name__)


def main():
    configure_logging()
    base_dir = Path(__file__).parent.parent / "knowledge_base" / "owasp"

    # Load OWASP top 10.
    top10_file = base_dir / "top10_2021.json"
    cwe_file = base_dir / "cwe_mappings.json"

    documents: list[str] = []
    if top10_file.exists():
        with open(top10_file) as f:
            top10 = json.load(f)
        for item in top10:
            doc = (
                f"{item['id']} {item['name']}: {item['description']} "
                f"Prevention: {'; '.join(item.get('prevention', []))}"
            )
            documents.append(doc)
    else:
        print(f"Warning: {top10_file} not found")

    if cwe_file.exists():
        with open(cwe_file) as f:
            cwes = json.load(f)
        for item in cwes:
            doc = (
                f"{item['id']} {item['name']}: {item['description']} "
                f"Patterns: {'; '.join(item.get('detection_patterns', []))}"
            )
            documents.append(doc)
    else:
        print(f"Warning: {cwe_file} not found")

    if not documents:
        print("No documents to ingest.")
        return

    # Upsert to ChromaDB.
    try:
        upsert_documents(documents)
        logger.info("ingest_complete", count=len(documents))
        print(f"✓ Ingested {len(documents)} documents into ChromaDB")
    except Exception as exc:
        logger.error("ingest_failed", error=str(exc))
        print(f"✗ Failed to ingest: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
