from __future__ import annotations

import os
import textwrap
from typing import List, Sequence

try:
    from groq import Groq
except ImportError:  # pragma: no cover - Groq optional during local dev without install
    Groq = None  # type: ignore


DEFAULT_SYSTEM_PROMPT = """You are an internal assistant for FinSolve Technologies.
You must always respect the provided context and cite the specific document names used.
If the answer is unavailable, state that you cannot find the information in the accessible documents."""


class LLMService:
    """Wrapper around the Groq LLM API with a graceful local fallback."""

    def __init__(
        self,
        model_name: str = "llama-3.1-8b-instant",
        temperature: float = 0.1,
    ) -> None:
        self.model_name = model_name
        self.temperature = temperature
        self.api_key = os.getenv("GROQ_API_KEY")
        self._client = None
        if self.api_key and Groq:
            self._client = Groq(api_key=self.api_key)

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def generate(
        self,
        question: str,
        role: str,
        contexts: Sequence[dict],
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> str:
        formatted_context = self._format_context(contexts)
        if not formatted_context:
            return "I could not find relevant information in the accessible documents."

        if not self.is_configured:
            # Deterministic fallback summarization
            summary_lines = [
                "Key points from the knowledge base:",
            ]
            for context in contexts:
                snippet = textwrap.shorten(context.get("document", ""), width=180, placeholder="...")
                source = context.get("source", "unknown source")
                summary_lines.append(f"- {snippet} (source: {source})")
            summary_lines.append("LLM generation is unavailable (missing GROQ_API_KEY).")
            return "\n".join(summary_lines)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Role: {role}\n"
                    f"Question: {question}\n\n"
                    f"Context:\n{formatted_context}\n\n"
                    "Provide a concise answer and reference the relevant sources."
                ),
            },
        ]
        response = self._client.chat.completions.create(
            model=self.model_name,
            temperature=self.temperature,
            messages=messages,
        )
        return response.choices[0].message.content.strip()

    @staticmethod
    def _format_context(contexts: Sequence[dict]) -> str:
        parts: List[str] = []
        for idx, context in enumerate(contexts, start=1):
            document = context.get("document")
            source = context.get("source")
            score = context.get("score")
            header = f"Source {idx}: {source}"
            if score is not None:
                header += f" (score: {score:.2f})"
            parts.append(f"{header}\n{document}")
        return "\n\n".join(parts)
