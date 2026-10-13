"""Central configuration for the Interview RAG app (Weaviate + PostgreSQL + Reranker)."""
import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
load_dotenv(PROJECT_DIR / ".env")

# PDFs directory: check pdfs/ folder first, fallback to parent directory
def _resolve_pdf_dir() -> Path:
    env_dir = os.getenv("PDF_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    candidates = [
        PROJECT_DIR.parent / "pdfs",
        PROJECT_DIR / "pdfs",
        PROJECT_DIR.parent,
    ]
    for c in candidates:
        if c.exists() and any(c.glob("*.pdf")):
            return c.resolve()
    return (PROJECT_DIR.parent / "pdfs").resolve()

PDF_DIR = _resolve_pdf_dir()
MANIFEST_PATH = PROJECT_DIR / "data" / "manifest.json"
STATIC_DIR = PROJECT_DIR / "static"

# Weaviate Docker connection
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "127.0.0.1")
WEAVIATE_HTTP_PORT = int(os.getenv("WEAVIATE_HTTP_PORT", 8085))
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", 50052))
WEAVIATE_COLLECTION = os.getenv("WEAVIATE_COLLECTION", "InterviewKnowledge")

# PostgreSQL Docker connection (port 5435 avoids 5432, 5433, 5434)
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", 5435))
PG_USER = os.getenv("PG_USER", "interview_user")
PG_PASSWORD = os.getenv("PG_PASSWORD", "interview_password")
PG_DB = os.getenv("PG_DB", "interview_db")
PG_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

# Session Auth settings
SESSION_COOKIE_NAME = "session_token"
SESSION_EXPIRE_DAYS = int(os.getenv("SESSION_EXPIRE_DAYS", 7))

# Models
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

# Reranker configuration (FlashRank: ultra-efficient ONNX cross-encoder)
RERANK_MODEL = os.getenv("RERANK_MODEL", "ms-marco-TinyBERT-L-2-v2")

# Retrieval parameters
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))
HYBRID_ALPHA = float(os.getenv("HYBRID_ALPHA", 0.5))
RETRIEVAL_CANDIDATES = int(os.getenv("RETRIEVAL_CANDIDATES", 20))
TOP_K = int(os.getenv("TOP_K", 6))

# Topic mapping rules
TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("RAG", ("rag",)),
    ("Agentic AI", ("agent",)),
    ("Fine-Tuning", ("lora", "fine-tuning", "finetuning")),
    ("LLM System Design", ("desgin", "design", "desgning", "designing")),
    ("SQL", ("sql",)),
    ("Deep Learning", ("deep learning", "advance_ml_dl")),
    ("LLM", ("llm",)),
    ("Generative AI", ("genai", "gen_ai", "real_time", "reat_time", "ai_engineer")),
    ("Machine Learning", ("ml", "machine")),
]


def topic_for(filename: str) -> str:
    name = filename.lower()
    for topic, keys in TOPIC_RULES:
        if any(k in name for k in keys):
            return topic
    return "General AI/ML"
