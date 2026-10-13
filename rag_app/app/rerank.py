"""Efficient Cross-Encoder Reranker using FlashRank (ONNX-optimized)."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from flashrank import Ranker, RerankRequest

from . import config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_ranker() -> Ranker:
    """Cached singleton instance of FlashRank cross-encoder ranker."""
    logger.info("Initializing FlashRank ranker with model: %s", config.RERANK_MODEL)
    return Ranker(model_name=config.RERANK_MODEL, cache_dir=str(config.PROJECT_DIR / "data" / "cache"))


def rerank_documents(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int = config.TOP_K,
) -> list[dict[str, Any]]:
    """Rerank candidate documents against the query using cross-attention.

    Each candidate dict must contain:
      - 'text' or 'content'
      - metadata (source, page, topic, chunk_id, etc.)

    Returns:
      Top-k candidate documents sorted descending by cross-encoder relevance score,
      with an added 'rerank_score' float field.
    """
    if not candidates:
        return []

    ranker = get_ranker()

    passages = []
    for i, c in enumerate(candidates):
        text = c.get("text") or c.get("content") or ""
        passages.append({
            "id": i,
            "text": text,
            "meta": c,
        })

    request = RerankRequest(query=query, passages=passages)
    results = ranker.rerank(request)

    reranked: list[dict[str, Any]] = []
    for item in results[:top_k]:
        original = item["meta"]
        original["rerank_score"] = round(float(item.get("score", 0.0)), 4)
        reranked.append(original)

    return reranked
