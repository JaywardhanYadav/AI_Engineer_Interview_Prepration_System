"""Retrieval-Augmented Generation (Hybrid Weaviate + FlashRank Reranker)."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from . import config
from .rerank import rerank_documents
from .store import get_llm, hybrid_search

PROPER_INTERVIEW_SYSTEM_PROMPT = """You are a warm, encouraging, and brilliant AI/ML Teacher and Mentor helping a student prepare for interviews.
Your mission is to explain AI/ML and GenAI concepts in very simple, plain English so that ANY learner can easily understand, remember, and explain them.

==================================================
CORE TEACHING RULES
==================================================
1. **Simple, Everyday Language**: Explain concepts clearly without heavy academic jargon. If you introduce a technical term (like "loss function", "weights", "vector embedding", "quantization"), immediately explain what it means in simple words.
2. **Use Everyday Real-World Analogies**: Always start with a relatable real-life analogy (like an open textbook, a library catalog, a kitchen chef, phone storage, etc.) so the student gets an instant intuitive picture.
3. **Bite-Sized Steps**: Break down mechanisms into clear, short Step 1, Step 2, Step 3 bullets.
4. **Be Encouraging & Practical**: Give the student exact phrases they can comfortably say aloud in an interview.

==================================================
STUDENT-FRIENDLY RESPONSE STRUCTURE
==================================================
Organize your response with these clear sections:

### 💡 Simple Intuition (The Everyday Analogy)
- Give a quick, relatable real-life analogy that makes the concept click immediately.

### 📌 What It Is in Plain English
- 1 to 2 clear, simple sentences defining what it is and the exact problem it solves. No confusing buzzwords.

### ⚙️ How It Works (Step-by-Step)
- Walk through how it works under the hood in 3 or 4 simple, numbered steps.
- Use simple words and bold key concepts.

### ⚖️ Easy Comparison (When to Use It)
- If this concept compares with another (e.g., RAG vs Fine-tuning, LoRA vs Full Fine-tuning, CNN vs RNN):
  - Give a simple, easy-to-read comparison table or quick bullet points.
  - Explain simply: "When should you use this?" vs "When should you NOT use this?".

### 🗣️ How to Say it in an Interview (Your Cheat-Sheet)
- A short, confident 2 to 3 sentence answer written in natural spoken English that the student can memorize and say to an interviewer with confidence.

==================================================
CITATION & GROUNDING RULES
==================================================
1. Add bracketed numbers like [1], [2] next to facts that come directly from the student's study notes.
2. If the user asks something not found in the notes, explain it simply anyway, but place it under:
   `### 🌐 Extra Knowledge (Beyond Study Notes)`
"""


def retrieve(
    query: str,
    topic: str | None = None,
    candidate_limit: int = config.RETRIEVAL_CANDIDATES,
    top_k: int = config.TOP_K,
) -> list[dict[str, Any]]:
    """Retrieve candidate chunks via Weaviate Hybrid Search and rerank with FlashRank."""
    # Step 1: Hybrid Search in Weaviate (BM25 keyword + Dense vector)
    candidates = hybrid_search(
        query=query,
        topic=topic,
        limit=candidate_limit,
        alpha=config.HYBRID_ALPHA,
    )

    if not candidates:
        return []

    # Step 2: Cross-Encoder Reranking via FlashRank (fast ONNX scoring)
    reranked = rerank_documents(query=query, candidates=candidates, top_k=top_k)
    return reranked


def format_context(chunks: list[dict[str, Any]]) -> str:
    """Format reranked chunks into clean numbered context blocks."""
    lines = []
    for i, c in enumerate(chunks, start=1):
        score_info = f" [rerank_score: {c.get('rerank_score')}]" if "rerank_score" in c else ""
        lines.append(
            f"[{i}] (Source: {c.get('source')}, Page: {c.get('page')}, Topic: {c.get('topic')}{score_info})\n"
            f"{c.get('text', '')}"
        )
    return "\n\n".join(lines)


def to_sources(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert chunks to frontend citation metadata."""
    return [
        {
            "id": i,
            "source": c.get("source"),
            "page": c.get("page"),
            "topic": c.get("topic"),
            "rerank_score": c.get("rerank_score"),
            "snippet": c.get("text", "")[:450],
        }
        for i, c in enumerate(chunks, start=1)
    ]


def answer(
    question: str,
    topic: str | None = None,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Generate grounded, high-bar interview answer using Weaviate + Reranker + Proper System Prompt."""
    search_query = question
    if history:
        last_user = next((h["content"] for h in reversed(history) if h.get("role") == "user"), "")
        if last_user and len(question.split()) < 8:
            search_query = f"{last_user}\n{question}"

    chunks = retrieve(query=search_query, topic=topic)

    messages = [SystemMessage(PROPER_INTERVIEW_SYSTEM_PROMPT)]
    for h in (history or [])[-6:]:
        cls = HumanMessage if h.get("role") == "user" else AIMessage
        messages.append(cls(h.get("content", "")))

    context_str = format_context(chunks) if chunks else "No relevant excerpts found in your study notes."
    user_payload = f"Context Excerpts:\n{context_str}\n\nInterview Question: {question}"
    messages.append(HumanMessage(user_payload))

    reply = get_llm(temperature=0.2).invoke(messages)
    return {
        "answer": reply.content,
        "sources": to_sources(chunks),
    }
