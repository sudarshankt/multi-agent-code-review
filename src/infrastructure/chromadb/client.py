"""ChromaDB client: embedded (default) or HTTP (optional)."""

from __future__ import annotations

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_client = None
_collection = None


def _init_client():
    global _client, _collection
    if _client is not None:
        return

    settings = get_settings()
    chromadb_config = settings.chromadb
    mode = chromadb_config.mode.lower()

    try:
        if mode == "http":
            import chromadb

            _client = chromadb.HttpClient(
                host=chromadb_config.host,
                port=chromadb_config.port,
            )
        else:  # embedded (default)
            import chromadb

            _client = chromadb.PersistentClient(
                path=chromadb_config.persist_dir,
            )
        _collection = _client.get_or_create_collection(
            name=chromadb_config.collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("chromadb_initialized", mode=mode)
    except ImportError:
        logger.warning("chromadb_not_installed", hint="Install with: pip install -e '.[rag]'")
        _client = None
        _collection = None
    except Exception as exc:
        logger.error("chromadb_init_failed", error=str(exc), mode=mode)
        _client = None
        _collection = None


def get_collection():
    """Get the ChromaDB collection (lazy init)."""
    _init_client()
    return _collection


def query_knowledge(query: str, top_k: int = 5) -> list[str]:
    """Query the knowledge base for documents matching the query."""
    collection = get_collection()
    if collection is None:
        return []

    try:
        results = collection.query(query_texts=[query], n_results=top_k)
        docs = results.get("documents", [[]])[0]
        return docs
    except Exception:
        return []


def upsert_documents(documents: list[str], metadatas: list[dict] | None = None) -> None:
    """Upsert documents into the knowledge base."""
    collection = get_collection()
    if collection is None:
        return

    try:
        ids = [str(i) for i in range(len(documents))]
        collection.upsert(
            documents=documents,
            ids=ids,
            metadatas=metadatas or [{"source": "owasp"} for _ in documents],
        )
    except Exception as exc:
        logger.error("chromadb_upsert_failed", error=str(exc))
