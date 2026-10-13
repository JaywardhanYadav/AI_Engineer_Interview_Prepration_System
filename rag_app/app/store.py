"""Weaviate Vector Database + OpenAI Client Factories."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.query import Filter
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from . import config

logger = logging.getLogger(__name__)


def get_weaviate_client() -> weaviate.WeaviateClient:
    """Connect to local Weaviate Docker instance."""
    return weaviate.connect_to_local(
        host=config.WEAVIATE_HOST,
        port=config.WEAVIATE_HTTP_PORT,
        grpc_port=config.WEAVIATE_GRPC_PORT,
    )


def ensure_collection(client: weaviate.WeaviateClient):
    """Ensure the InterviewKnowledge collection exists with proper schema."""
    if client.collections.exists(config.WEAVIATE_COLLECTION):
        return client.collections.get(config.WEAVIATE_COLLECTION)

    logger.info("Creating Weaviate collection '%s'", config.WEAVIATE_COLLECTION)
    return client.collections.create(
        name=config.WEAVIATE_COLLECTION,
        properties=[
            Property(name="text", data_type=DataType.TEXT, description="Chunk text content"),
            Property(name="source", data_type=DataType.TEXT, description="Origin PDF file name"),
            Property(name="page", data_type=DataType.INT, description="PDF page number"),
            Property(name="topic", data_type=DataType.TEXT, description="Interview category"),
            Property(name="chunk_hash", data_type=DataType.TEXT, description="Content hash for deduplication"),
        ],
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE
        ),
        inverted_index_config=Configure.inverted_index(
            bm25_b=0.75,
            bm25_k1=1.2,
        ),
    )


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=config.EMBED_MODEL, api_key=config.OPENAI_API_KEY)


@lru_cache(maxsize=4)
def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(model=config.CHAT_MODEL, temperature=temperature, api_key=config.OPENAI_API_KEY)


def hybrid_search(
    query: str,
    query_vector: list[float] | None = None,
    topic: str | None = None,
    limit: int = config.RETRIEVAL_CANDIDATES,
    alpha: float = config.HYBRID_ALPHA,
) -> list[dict[str, Any]]:
    """Perform Weaviate Hybrid Search (BM25 keyword + dense cosine vector)."""
    client = get_weaviate_client()
    try:
        if not client.collections.exists(config.WEAVIATE_COLLECTION):
            return []

        collection = client.collections.get(config.WEAVIATE_COLLECTION)

        filters = None
        if topic and topic != "All":
            filters = Filter.by_property("topic").equal(topic)

        # If vector is not provided, embed the query text
        if query_vector is None and config.OPENAI_API_KEY:
            embeddings = get_embeddings()
            query_vector = embeddings.embed_query(query)

        response = collection.query.hybrid(
            query=query,
            vector=query_vector,
            alpha=alpha,
            limit=limit,
            filters=filters,
            return_metadata=["score", "explain_score"],
        )

        candidates = []
        for obj in response.objects:
            props = obj.properties
            candidates.append({
                "id": str(obj.uuid),
                "text": props.get("text", ""),
                "source": props.get("source", ""),
                "page": props.get("page", 0),
                "topic": props.get("topic", ""),
                "weaviate_score": getattr(obj.metadata, "score", None),
            })
        return candidates
    finally:
        client.close()
