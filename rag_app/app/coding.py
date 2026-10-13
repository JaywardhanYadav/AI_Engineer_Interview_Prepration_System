"""AI Engineer Coding Practice: Realistic interview coding questions, working solutions, and simple explanations."""
from __future__ import annotations

import random
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .rag import format_context, retrieve, to_sources
from .store import get_llm

CODING_CATEGORIES = [
    "DSA",
    "Python",
    "FastAPI",
    "LangChain",
    "LangGraph",
    "RAG & Vector DB",
    "PyTorch",
]

CATEGORY_PROMPTS = {
    "DSA": "Data Structures & Algorithms essential for AI/ML (e.g., cosine similarity from scratch, top-k sampling / min-heap, sliding window text chunker, BPE tokenizer logic, matrix multiplications)",
    "Python": "Python core & advanced engineering concepts (e.g., async generators, custom retry decorators, context managers for memory/resources, Pydantic v2 validation models, metaclasses or dataclasses)",
    "FastAPI": "FastAPI backend engineering for AI (e.g., streaming LLM tokens via Server-Sent Events (SSE), async dependency injection, streaming responses, background tasks, rate limiting for LLM APIs)",
    "LangChain": "LangChain & LCEL implementation (e.g., custom LCEL chain with RunnablePassthrough, custom document loader, hybrid retriever chain, tool-calling agent with structured output)",
    "LangGraph": "LangGraph workflows (e.g., StateGraph with cyclic loops, supervisor multi-agent routing, conditional edges with error recovery, state management with TypedDict)",
    "RAG & Vector DB": "RAG & Vector Search coding (e.g., Reciprocal Rank Fusion (RRF) for hybrid search, cross-encoder reranking function, sliding window chunking with metadata, cosine vs dot product vector search)",
    "PyTorch": "PyTorch deep learning coding (e.g., Scaled Dot-Product Attention from scratch, custom Dataset/DataLoader with dynamic batch padding, custom loss function, LoRA forward pass layer)",
}

DIFFICULTY_GUIDE = {
    "easy": "a clean, fundamental coding problem testing core understanding without tricky edge cases",
    "medium": "a realistic interview coding question testing practical implementation, clean architecture, and best practices",
    "hard": "an advanced scenario coding problem (e.g., distributed streaming, complex graph routing, custom attention, low-level optimization)",
}


class CodingChallenge(BaseModel):
    title: str = Field(description="Short descriptive problem title, e.g., 'Streaming LLM Tokens via FastAPI and SSE'")
    category: str = Field(description="Category of the coding problem (DSA, Python, FastAPI, LangChain, LangGraph, RAG & Vector DB, or PyTorch)")
    difficulty: str = Field(description="Difficulty level: easy, medium, or hard")
    problem_statement: str = Field(
        description="Clear, realistic interview problem description. State the objective, expected function or class signature, and sample input/output or scenario."
    )
    code_solution: str = Field(
        description="Complete, working, production-quality Python code. Include imports, docstrings, and inline comments explaining key lines."
    )
    explanation: str = Field(
        description=(
            "Beginner-friendly explanation in clear, simple English for students:\n"
            "1. 💡 Core Intuition & Everyday Analogy (What is happening in plain words)\n"
            "2. ⚙️ Step-by-Step Code Walkthrough (Explain key lines/blocks simply)\n"
            "3. ⏱️ Complexity & Best Practices (Time/space complexity for DSA, or production edge-cases & error handling for frameworks)\n"
            "4. 🎯 Interview Soundbite (A 2-sentence summary the student can say out loud to impress the interviewer)"
        )
    )


def generate_coding_card(
    category: str | None = None,
    difficulty: str = "medium",
    avoid: list[str] | None = None,
) -> dict[str, Any]:
    """Generate an AI Engineer coding challenge, working code solution, and student explanation."""
    cat = category
    if not cat or cat == "All":
        cat = random.choice(CODING_CATEGORIES)

    cat_desc = CATEGORY_PROMPTS.get(cat, f"{cat} for AI Engineering")
    diff_desc = DIFFICULTY_GUIDE.get(difficulty.lower(), DIFFICULTY_GUIDE["medium"])
    avoid_list = avoid or []
    avoid_text = "\n".join(f"- {a}" for a in avoid_list[-10:]) if avoid_list else "None"

    # Search knowledge base for grounding snippets if available
    query = f"{cat} interview coding question python implementation"
    chunks = []
    try:
        chunks = retrieve(query, topic=None, top_k=3)
    except Exception:
        chunks = []

    context_str = format_context(chunks) if chunks else "(No direct PDF snippet found; create an industry-standard problem from AI Engineer interview practices)"

    llm = get_llm(temperature=0.4).with_structured_output(CodingChallenge)

    challenge: CodingChallenge = llm.invoke([
        SystemMessage(
            "You are a Senior Principal AI Engineer and dedicated mentor creating practical, real-world coding interview problems "
            "for aspiring AI Engineers. Your problems must reflect genuine coding tests at top AI companies (OpenAI, Anthropic, Google, AI startups).\n\n"
            "Guidelines:\n"
            "- The problem statement must be concise, practical, and provide clear requirements.\n"
            "- The code solution MUST be runnable, production-quality Python code with proper type hints, docstrings, and clear comments.\n"
            "- The explanation must be crystal clear for a learner/student: use everyday analogies, break down the code step-by-step, explain complexities/edge cases, and provide an interview cheat-sheet soundbite."
        ),
        HumanMessage(
            f"Generate a {diff_desc} for the category: {cat} ({cat_desc}).\n\n"
            f"Recently covered questions to avoid repeating:\n{avoid_text}\n\n"
            f"Reference Material from Study Notes (if helpful):\n{context_str}\n\n"
            f"Craft a high-value coding problem with working Python code solution and comprehensive explanation."
        ),
    ])

    return {
        "title": challenge.title,
        "category": cat,
        "difficulty": difficulty.lower(),
        "problem_statement": challenge.problem_statement,
        "code_solution": challenge.code_solution,
        "explanation": challenge.explanation,
        "sources": to_sources(chunks) if chunks else [],
    }
