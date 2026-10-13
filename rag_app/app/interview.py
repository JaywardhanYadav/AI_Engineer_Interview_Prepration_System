"""Mock interview mode: question generation and grading powered by Weaviate + Reranker."""
from __future__ import annotations

import random
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from weaviate.classes.query import Filter

from . import config
from .rag import format_context, retrieve, to_sources
from .store import get_llm, get_weaviate_client

DIFFICULTY_HINT = {
    "easy": "a clear, foundational question suitable for a beginner/student to test basic understanding",
    "medium": "a conceptual 'how does it work and why' question testing understanding and simple trade-offs",
    "hard": "a practical scenario question asking how to solve a real problem step-by-step in an interview",
}


class GeneratedQuestion(BaseModel):
    question: str = Field(description="One clear, simple technical interview question without giving away the answer")
    concept: str = Field(description="Short name of the concept tested, e.g. 'LoRA vs QLoRA', 'Overfitting vs Underfitting'")
    usable: bool = Field(description="False if the source excerpt is low-quality index, TOC, or corrupted")


class Grade(BaseModel):
    score: int = Field(ge=0, le=10, description="0 to 10 score based on clarity, correctness, and understanding")
    verdict: str = Field(description="One encouraging sentence summarizing the student's answer")
    strengths: list[str] = Field(description="1-3 things the student understood and explained well")
    gaps: list[str] = Field(description="Important missing points explained gently in very simple plain English")
    model_answer: str = Field(description="A simple, beginner-friendly model answer using analogies and citations [1]")
    follow_up: str = Field(description="A friendly follow-up question to help the student practice further")


def _random_chunk(topic: str | None = None) -> dict[str, Any] | None:
    client = get_weaviate_client()
    try:
        if not client.collections.exists(config.WEAVIATE_COLLECTION):
            return None
        col = client.collections.get(config.WEAVIATE_COLLECTION)

        filters = None
        if topic and topic != "All":
            filters = Filter.by_property("topic").equal(topic)

        # Sample from candidate objects
        candidates = col.query.fetch_objects(limit=50, filters=filters)
        if not candidates.objects:
            return None

        chosen = random.choice(candidates.objects)
        props = chosen.properties
        return {
            "id": str(chosen.uuid),
            "text": props.get("text", ""),
            "source": props.get("source", ""),
            "page": props.get("page", 0),
            "topic": props.get("topic", ""),
        }
    finally:
        client.close()


def generate_question(
    topic: str | None = None,
    difficulty: str = "medium",
    avoid: list[str] | None = None,
) -> dict[str, Any]:
    llm = get_llm(temperature=0.7).with_structured_output(GeneratedQuestion)
    hint = DIFFICULTY_HINT.get(difficulty, DIFFICULTY_HINT["medium"])
    avoid_txt = "\n".join(f"- {q}" for q in (avoid or [])[-15:]) or "(none)"

    for _ in range(5):
        chunk = _random_chunk(topic)
        if chunk is None:
            raise ValueError("No indexed content in Weaviate for this topic. Run ingestion first: `python -m app.ingest`")

        out: GeneratedQuestion = llm.invoke([
            SystemMessage(
                "You are an encouraging AI/ML Teacher helping a student prepare for interviews. "
                "Craft a clear, thought-provoking technical interview question in simple, natural English. "
                "Never mention 'the excerpt', 'the notes', or 'the document'."
            ),
            HumanMessage(
                f"Craft {hint}.\n"
                f"Avoid repeating these recent questions:\n{avoid_txt}\n\n"
                f"Study Excerpt (Topic: {chunk.get('topic')}):\n{chunk.get('text')}"
            ),
        ])

        if out.usable:
            return {
                "question": out.question,
                "concept": out.concept,
                "difficulty": difficulty,
                "topic": chunk.get("topic"),
                "seed_id": chunk.get("id"),
                "seed_source": {"source": chunk.get("source"), "page": chunk.get("page")},
            }

    raise RuntimeError("Could not generate a suitable question from the current notes. Please try again.")


def grade_answer(
    question: str,
    user_answer: str,
    topic: str | None = None,
    seed_id: str | None = None,
) -> dict[str, Any]:
    chunks = retrieve(question, topic=topic, top_k=5)

    llm = get_llm(temperature=0.1).with_structured_output(Grade)
    grade: Grade = llm.invoke([
        SystemMessage(
            "You are a kind, motivating, and expert AI/ML Teacher grading a student's answer for interview prep.\n"
            "Grading Guidelines:\n"
            "- 9-10: Excellent! Clear explanation with correct intuition and good points.\n"
            "- 7-8: Good job! Gets the core idea right with a few small gaps.\n"
            "- 5-6: Partially right; understood the high-level concept but missed key details.\n"
            "- 3-4: Has confusion or misunderstands the core mechanism.\n"
            "- 0-2: Blank or incorrect answer.\n\n"
            "Keep feedback supportive and constructive. In gaps and model_answer, explain in very simple English "
            "with everyday intuition so the student learns immediately. Cite context excerpts as [1], [2]."
        ),
        HumanMessage(
            f"Reference Context Excerpts:\n{format_context(chunks)}\n\n"
            f"Interview Question: {question}\n\n"
            f"Student Answer:\n{user_answer or '(No answer provided)'}"
        ),
    ])

    return {**grade.model_dump(), "sources": to_sources(chunks)}


def generate_qa_card(
    topic: str | None = None,
    difficulty: str = "medium",
    avoid: list[str] | None = None,
) -> dict[str, Any]:
    """Generate an interview question along with its direct, student-friendly answer and PDF citations."""
    from .rag import answer

    q_data = generate_question(topic=topic, difficulty=difficulty, avoid=avoid)
    ans_data = answer(question=q_data["question"], topic=q_data.get("topic"))

    return {
        "question": q_data["question"],
        "concept": q_data.get("concept", ""),
        "topic": q_data.get("topic", "General"),
        "difficulty": difficulty,
        "answer": ans_data["answer"],
        "sources": ans_data.get("sources", []),
    }

