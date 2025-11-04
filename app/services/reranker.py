from __future__ import annotations

import logging
from typing import Iterable, List, Sequence

try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None  # type: ignore

LOGGER = logging.getLogger(__name__)


class RerankerService:
    """Optional cross-encoder reranker for retrieved contexts."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        enabled: bool = False,
        top_k: int = 4,
    ) -> None:
        self.model_name = model_name
        self.enabled = enabled and CrossEncoder is not None
        self.top_k = top_k
        self._model = None

        if enabled and CrossEncoder is None:
            LOGGER.warning("Reranker requested but sentence-transformers CrossEncoder not available.")

    def _ensure_model(self) -> None:
        if not self.enabled:
            return
        if self._model is None:
            try:
                self._model = CrossEncoder(self.model_name)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.exception("Failed to load reranker model: %s", exc)
                self.enabled = False

    def reorder(self, question: str, contexts: Sequence[dict]) -> List[dict]:
        if not self.enabled or not contexts:
            return list(contexts)

        self._ensure_model()
        if not self.enabled or self._model is None:
            return list(contexts)

        pairs = [(question, ctx.get("document", "")) for ctx in contexts]
        scores = self._model.predict(pairs)
        scored_contexts = sorted(
            zip(scores, contexts),
            key=lambda item: item[0],
            reverse=True,
        )
        reranked = [ctx for _, ctx in scored_contexts[: self.top_k]]
        return reranked
