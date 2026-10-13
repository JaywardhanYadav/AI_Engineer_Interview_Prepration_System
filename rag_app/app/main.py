"""FastAPI server: JSON API + Auth + PostgreSQL Conversations + Weaviate RAG.

Run:  uvicorn app.main:app --port 8090 --reload   (from the rag_app folder)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .db import (
    add_message,
    authenticate_user,
    create_conversation,
    create_session,
    create_user,
    delete_conversation,
    delete_session,
    get_conversation,
    get_user_by_session,
    get_user_interview_stats,
    init_db,
    list_conversations,
    save_interview_result,
    update_conversation_title,
)
from .ingest import load_manifest
from .store import get_weaviate_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize PostgreSQL tables
    try:
        init_db()
    except Exception as e:
        print(f"Warning: Could not connect to PostgreSQL on startup: {e}")
    yield


app = FastAPI(title="Interview RAG Coach", lifespan=lifespan)


# ================= Auth Models & Helpers =================

class AuthIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=100)


def get_current_user_optional(
    session_token: Optional[str] = Cookie(None, alias=config.SESSION_COOKIE_NAME),
    authorization: Optional[str] = Header(None),
) -> Optional[dict]:
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    if not token:
        return None
    return get_user_by_session(token)


def get_current_user_required(user: Optional[dict] = Depends(get_current_user_optional)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")
    return user


# ================= Request Models =================

class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    topic: str | None = None
    conversation_id: int | None = None
    history: list[dict] = []


class QuestionIn(BaseModel):
    topic: str | None = None
    difficulty: str = "medium"
    avoid: list[str] = []


class CodingIn(BaseModel):
    category: str | None = "All"
    difficulty: str = "medium"
    avoid: list[str] = []


class GradeIn(BaseModel):
    question: str
    answer: str = Field(default="", max_length=8000)
    topic: str | None = None
    difficulty: str = "medium"
    seed_id: str | None = None


class NewConvIn(BaseModel):
    title: str = "New Chat"


def _guard():
    if not config.OPENAI_API_KEY:
        raise HTTPException(400, "OPENAI_API_KEY is not set. Add it to rag_app/.env and restart.")

    try:
        client = get_weaviate_client()
        ready = client.is_ready()
        has_collection = client.collections.exists(config.WEAVIATE_COLLECTION)
        count = 0
        if has_collection:
            col = client.collections.get(config.WEAVIATE_COLLECTION)
            agg = col.aggregate.over_all(total_count=True)
            count = agg.total_count or 0
        client.close()
        if not ready:
            raise HTTPException(503, "Weaviate is not responding. Run `docker compose up -d`.")
        if count == 0:
            raise HTTPException(400, "Weaviate knowledge base is empty. Run: python -m app.ingest")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Cannot connect to Weaviate: {e}") from e


# ================= Status Endpoint =================

@app.get("/api/status")
def status(user: Optional[dict] = Depends(get_current_user_optional)):
    weaviate_ok = False
    weaviate_objects = 0
    try:
        client = get_weaviate_client()
        if client.is_ready():
            weaviate_ok = True
            if client.collections.exists(config.WEAVIATE_COLLECTION):
                col = client.collections.get(config.WEAVIATE_COLLECTION)
                agg = col.aggregate.over_all(total_count=True)
                weaviate_objects = agg.total_count or 0
        client.close()
    except Exception:
        weaviate_ok = False

    m = load_manifest()
    files = [
        {"name": k, **{x: v.get(x) for x in ("topic", "chunks", "pages_total", "pages_with_text", "duplicate_of")}}
        for k, v in sorted(m.get("files", {}).items())
    ]
    topics: dict[str, int] = {}
    for f in files:
        if f.get("chunks"):
            topics[f["topic"]] = topics.get(f["topic"], 0) + f["chunks"]

    return {
        "api_key_set": bool(config.OPENAI_API_KEY),
        "model": config.CHAT_MODEL,
        "reranker": config.RERANK_MODEL,
        "weaviate_connected": weaviate_ok,
        "weaviate_objects": weaviate_objects,
        "ready": bool(weaviate_ok and weaviate_objects > 0),
        "total_chunks": weaviate_objects,
        "topics": dict(sorted(topics.items())),
        "files": files,
        "user": {"id": user["id"], "username": user["username"]} if user else None,
    }


# ================= Auth Endpoints =================

@app.post("/api/auth/register")
def register(body: AuthIn, response: Response):
    try:
        user = create_user(body.username, body.password)
        token = create_session(user["id"])
        response.set_cookie(
            key=config.SESSION_COOKIE_NAME,
            value=token,
            max_age=config.SESSION_EXPIRE_DAYS * 86400,
            httponly=True,
            samesite="lax",
        )
        return {"status": "ok", "user": {"id": user["id"], "username": user["username"]}, "token": token}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/auth/login")
def login(body: AuthIn, response: Response):
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = create_session(user["id"])
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        max_age=config.SESSION_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite="lax",
    )
    return {"status": "ok", "user": user, "token": token}


@app.post("/api/auth/logout")
def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None, alias=config.SESSION_COOKIE_NAME),
):
    if session_token:
        delete_session(session_token)
    response.delete_cookie(key=config.SESSION_COOKIE_NAME)
    return {"status": "ok"}


@app.get("/api/auth/me")
def me(user: Optional[dict] = Depends(get_current_user_optional)):
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": {"id": user["id"], "username": user["username"]}}


# ================= Conversation Management Endpoints =================

@app.get("/api/conversations")
def get_conversations(user: dict = Depends(get_current_user_required)):
    return list_conversations(user["id"])


@app.post("/api/conversations")
def new_conversation(body: NewConvIn, user: dict = Depends(get_current_user_required)):
    return create_conversation(user["id"], title=body.title)


@app.get("/api/conversations/{conv_id}")
def get_single_conversation(conv_id: int, user: dict = Depends(get_current_user_required)):
    conv = get_conversation(conv_id, user["id"])
    if not conv:
        raise HTTPException(404, "Conversation not found.")
    return conv


@app.delete("/api/conversations/{conv_id}")
def remove_conversation(conv_id: int, user: dict = Depends(get_current_user_required)):
    ok = delete_conversation(conv_id, user["id"])
    if not ok:
        raise HTTPException(404, "Conversation not found.")
    return {"status": "deleted"}


# ================= RAG & Interview Endpoints =================

@app.post("/api/ask")
def ask(body: AskIn, user: Optional[dict] = Depends(get_current_user_optional)):
    _guard()
    from .rag import answer

    # Build history from PostgreSQL conversation if specified
    history = body.history
    conv_id = body.conversation_id
    if user and conv_id:
        conv = get_conversation(conv_id, user["id"])
        if conv and conv.get("messages"):
            history = [{"role": m["role"], "content": m["content"]} for m in conv["messages"][-6:]]

    try:
        res = answer(body.question, body.topic, history)

        # Persist turns into PostgreSQL if logged in and conversation is active
        if user:
            if not conv_id:
                # auto-create a conversation
                title = body.question[:45] + ("..." if len(body.question) > 45 else "")
                new_c = create_conversation(user["id"], title=title)
                conv_id = new_c["id"]
            else:
                # Update title on first message
                conv = get_conversation(conv_id, user["id"])
                if conv and len(conv.get("messages", [])) == 0:
                    update_conversation_title(conv_id, user["id"], body.question[:45])

            add_message(conv_id, "user", body.question)
            add_message(conv_id, "assistant", res["answer"], sources=res.get("sources", []))
            res["conversation_id"] = conv_id

        return res
    except Exception as e:
        raise HTTPException(500, f"Answer generation failed: {e}") from e


@app.post("/api/interview/question")
def interview_question(body: QuestionIn):
    _guard()
    from .interview import generate_question
    try:
        return generate_question(body.topic, body.difficulty, body.avoid)
    except Exception as e:
        raise HTTPException(500, f"Question generation failed: {e}") from e


@app.post("/api/qa/card")
def qa_card(body: QuestionIn):
    _guard()
    from .interview import generate_qa_card
    try:
        return generate_qa_card(body.topic, body.difficulty, body.avoid)
    except Exception as e:
        raise HTTPException(500, f"Q&A generation failed: {e}") from e


@app.post("/api/coding/card")
def coding_card(body: CodingIn):
    _guard()
    from .coding import generate_coding_card
    try:
        return generate_coding_card(body.category, body.difficulty, body.avoid)
    except Exception as e:
        raise HTTPException(500, f"Coding card generation failed: {e}") from e


@app.post("/api/interview/grade")
def interview_grade(body: GradeIn, user: Optional[dict] = Depends(get_current_user_optional)):
    _guard()
    from .interview import grade_answer
    try:
        result = grade_answer(body.question, body.answer, body.topic, body.seed_id)
        if user:
            save_interview_result(user["id"], {
                "topic": body.topic,
                "difficulty": body.difficulty,
                "question": body.question,
                "user_answer": body.answer,
                "score": result.get("score"),
                "verdict": result.get("verdict"),
                "strengths": result.get("strengths"),
                "gaps": result.get("gaps"),
                "model_answer": result.get("model_answer"),
                "follow_up": result.get("follow_up"),
            })
        return result
    except Exception as e:
        raise HTTPException(500, f"Grading failed: {e}") from e


@app.get("/api/interview/stats")
def interview_stats(user: dict = Depends(get_current_user_required)):
    return get_user_interview_stats(user["id"])


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
