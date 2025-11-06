from __future__ import annotations

import os
import re
import textwrap
from typing import List, Optional, Sequence, Tuple

try:
    from groq import Groq
except ImportError:  # pragma: no cover - Groq optional during local dev without install
    Groq = None  # type: ignore


DEFAULT_SYSTEM_PROMPT = """You are an internal assistant for FinSolve Technologies.
You must always respect the provided context and cite the specific document names used.
If the answer is unavailable, state that you cannot find the information in the accessible documents."""

STOPWORDS = {
    "what",
    "was",
    "were",
    "the",
    "this",
    "that",
    "with",
    "from",
    "into",
    "does",
    "have",
    "has",
    "had",
    "about",
    "which",
    "where",
    "when",
    "finsolve",
    "technologies",
    "please",
    "give",
    "show",
    "tell",
    "much",
    "many",
    "year",
    "years",
    "2024",
}


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
            answer_sentence, source = self._extract_answer(question, contexts)
            if answer_sentence:
                lines = [
                    answer_sentence.strip(),
                    f"(source: {source or 'unknown source'})",
                    "",
                    "LLM generation is unavailable (missing GROQ_API_KEY).",
                ]
                return "\n".join(lines)

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

    @staticmethod
    def _extract_answer(question: str, contexts: Sequence[dict]) -> Tuple[Optional[str], Optional[str]]:
        question_terms = {
            word
            for word in re.findall(r"\b\w+\b", question.lower())
            if len(word) > 3 and word not in STOPWORDS
        }
        if not question_terms:
            return None, None

        best_sentence: Optional[str] = None
        best_source: Optional[str] = None
        best_score = 0

        for context in contexts:
            document = context.get("document", "")
            source = context.get("source", "unknown source")
            sentences = re.split(r"(?<=[.!?])\s+", document)
            for sentence in sentences:
                cleaned = sentence.strip()
                if not cleaned:
                    continue
                lower_sentence = cleaned.lower()
                score = sum(1 for term in question_terms if term in lower_sentence)
                if score > best_score:
                    best_sentence = cleaned
                    best_score = score
                    best_source = source

        if best_sentence and best_score > 0:
            return best_sentence, best_source

        return None, None
