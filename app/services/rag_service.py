from __future__ import annotations

import csv
import itertools
import logging
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import chromadb
from chromadb import PersistentClient
from chromadb.utils import embedding_functions


LOGGER = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """Chunk text into overlapping segments suitable for embedding."""
    sanitized = " ".join(text.split())
    if not sanitized:
        return []
    if len(sanitized) <= chunk_size:
        return [sanitized]

    chunks: List[str] = []
    start = 0
    text_length = len(sanitized)
    while start < text_length:
        end = min(text_length, start + chunk_size)
        chunk = sanitized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_length:
            break
        start = max(0, end - overlap)
    return chunks


def read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_csv(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as csvfile:
        reader = csv.reader(csvfile)
        rows = list(reader)
    if not rows:
        return ""
    headers = rows[0]
    lines = []
    if headers:
        lines.append(" | ".join(headers))
    for row in rows[1:]:
        lines.append(" | ".join(row))
    return "\n".join(lines)


FILE_READERS = {
    ".md": read_markdown,
    ".markdown": read_markdown,
    ".txt": read_text,
    ".csv": read_csv,
}


class RAGService:
    """Handles document ingestion, vector indexing, and retrieval."""

    def __init__(
        self,
        data_root: Path,
        persist_directory: Path,
        collection_name: str = "rbac_documents",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        self.data_root = data_root
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.embedding_model
        )
        self.client: PersistentClient = chromadb.PersistentClient(path=str(self.persist_directory))
        # Always start with a clean collection to keep embeddings in sync with disk files
        self._recreate_collection()

    def _recreate_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except chromadb.errors.ChromaError:
            pass
        self.collection = self.client.create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    def build(self) -> None:
        """Load documents from disk and index them in the vector store."""
        documents: List[str] = []
        metadatas: List[Dict[str, str]] = []
        ids: List[str] = []

        if not self.data_root.exists():
            LOGGER.warning("Data root %s does not exist. Skipping ingestion.", self.data_root)
            return

        for department_dir in sorted(self.data_root.iterdir()):
            if not department_dir.is_dir():
                continue
            department = department_dir.name.lower()
            for file_path in sorted(department_dir.rglob("*")):
                if file_path.is_dir():
                    continue
                reader = FILE_READERS.get(file_path.suffix.lower())
                if not reader:
                    LOGGER.warning("Unsupported file type for %s. Skipping.", file_path)
                    continue
                try:
                    text = reader(file_path)
                except Exception as exc:  # pragma: no cover - defensive logging
                    LOGGER.exception("Failed to read %s: %s", file_path, exc)
                    continue
                chunks = chunk_text(text)
                relative_source = str(file_path.relative_to(self.data_root.parent))
                for chunk_index, chunk in enumerate(chunks):
                    documents.append(chunk)
                    metadatas.append(
                        {
                            "department": department,
                            "source": relative_source,
                            "chunk_index": str(chunk_index),
                        }
                    )
                    ids.append(f"{department}-{file_path.stem}-{uuid.uuid4()}")

        if documents:
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
            LOGGER.info("Loaded %d chunks into collection %s", len(documents), self.collection_name)
        else:
            LOGGER.warning("No documents were ingested from %s.", self.data_root)

    def query(
        self,
        question: str,
        departments: Iterable[str],
        top_k: int = 4,
    ) -> List[Dict[str, Optional[str]]]:
        """Retrieve the top_k documents matching the question within allowed departments."""
        normalized_departments = sorted({dept.strip().lower() for dept in departments if dept})
        if not normalized_departments:
            return []
        result = self.collection.query(
            query_texts=[question],
            where={"department": {"$in": normalized_departments}},
            n_results=top_k,
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        payload = []
        for doc, metadata, distance in itertools.zip_longest(documents, metadatas, distances):
            if not metadata:
                continue
            score = None
            if distance is not None:
                score = max(0.0, min(1.0, 1 - float(distance)))
            payload.append(
                {
                    "document": doc,
                    "department": metadata.get("department"),
                    "source": metadata.get("source"),
                    "chunk_index": metadata.get("chunk_index"),
                    "score": score,
                }
            )
        return payload
