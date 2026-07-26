"""ChromaDB client: embedded (default) or HTTP (optional)."""

from __future__ import annotations

from pathlib import Path

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_client = None
_collection = None


def _resolve_embedding_model(model_name: str) -> str:
    """Resolve local model paths and sanitize model ids for SentenceTransformers."""
    raw = (model_name or "").strip()
    if not raw:
        return "sentence-transformers/all-MiniLM-L6-v2"

    path_candidate = Path(raw)
    if path_candidate.exists():
        return str(path_candidate.resolve())

    # `./foo` is rejected by HF repo-id validation when no local directory exists.
    if raw.startswith("./"):
        normalized = raw[2:]
        logger.warning("chromadb_embedding_model_normalized", original=raw, normalized=normalized)
        return normalized

    return raw


def _init_client():
    global _client, _collection
    if _client is not None:
        return

    settings = get_settings()
    chromadb_config = settings.chromadb
    mode = chromadb_config.mode.lower()
    repo_root = Path(__file__).resolve().parents[3]

    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        if mode == "http":
            _client = chromadb.HttpClient(
                host=chromadb_config.host,
                port=chromadb_config.port,
            )
        else:  # embedded (default)
            persist_dir = Path(chromadb_config.persist_dir)
            if not persist_dir.is_absolute():
                persist_dir = repo_root / persist_dir
            _client = chromadb.PersistentClient(
                path=str(persist_dir),
            )

        # Loads from a local model directory (no network call) so embedding
        # works on networks that block huggingface.co / S3 model downloads.
        embedding_function = SentenceTransformerEmbeddingFunction(
            model_name=_resolve_embedding_model(chromadb_config.embedding_model_path),
        )
        _collection = _client.get_or_create_collection(
            name=chromadb_config.collection,
            metadata={"hnsw:space": "cosine"},
            embedding_function=embedding_function,
        )
        logger.info("chromadb_initialized", mode=mode)
    except ImportError:
        logger.warning("chromadb_not_installed", hint="Install with: pip install chromadb sentence-transformers")
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
