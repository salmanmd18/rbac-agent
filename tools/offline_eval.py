"""Lightweight RAG evaluation runner.

Usage:
    uv run python tools/offline_eval.py --dataset eval_samples.json --output results.csv

The dataset file should contain an array of objects:
[
  {
    "role": "hr",
    "username": "Natasha",
    "password": "hrpass123",
    "question": "Summarize the performance review policy.",
    "expected_keywords": ["performance", "review"]
  }
]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List

from fastapi.testclient import TestClient

from app.main import app


def keyword_precision(answer: str, expected_keywords: Iterable[str]) -> float:
    if not expected_keywords:
        return 1.0
    present = sum(1 for keyword in expected_keywords if keyword.lower() in answer.lower())
    return present / len(list(expected_keywords))


def run_evaluation(dataset_path: Path, output_path: Path) -> None:
    samples: List[Dict[str, object]] = json.loads(dataset_path.read_text(encoding="utf-8"))
    rows: List[Dict[str, object]] = []

    with TestClient(app) as client:
        for item in samples:
            username = item.get("username")
            password = item.get("password")
            question = item.get("question")
            expected_keywords = item.get("expected_keywords", [])

            response = client.post(
                "/chat",
                json={"message": question, "top_k": item.get("top_k", 4)},
                auth=(username, password),
            )
            payload = response.json()
            answer = payload.get("answer", "")
            references = payload.get("references", [])

            rows.append(
                {
                    "username": username,
                    "role": payload.get("role"),
                    "question": question,
                    "answer": answer,
                    "references": ";".join(ref["source"] for ref in references),
                    "keyword_precision": keyword_precision(answer, expected_keywords),
                    "reference_count": len(references),
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run offline RAG evaluation.")
    parser.add_argument("--dataset", type=Path, required=True, help="Path to evaluation samples JSON.")
    parser.add_argument("--output", type=Path, default=Path("eval_results.csv"), help="Where to store results CSV.")
    args = parser.parse_args()

    run_evaluation(dataset_path=args.dataset, output_path=args.output)
    print(f"Evaluation complete. Results saved to {args.output}")
