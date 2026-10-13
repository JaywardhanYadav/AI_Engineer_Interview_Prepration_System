# AI Engineer Interview Preparation System 🚀

A production-grade, full-stack **Retrieval-Augmented Generation (RAG)** platform designed to help students, learners, and engineers master **AI/ML & Generative AI technical interviews**.

Built on **24 curated study PDFs** covering RAG, Agentic AI, LLMs, System Design, PyTorch, Deep Learning, Machine Learning, and SQL. Powered by **Dockerized Weaviate**, **FlashRank ONNX Reranking**, **PostgreSQL**, **FastAPI**, and an interactive glassmorphic web interface.

---

## 🌟 4 Interactive Practice Modes

### 1. 💬 Ask & Learn (Conversational RAG)
- Free-form Q&A grounded in your PDF study materials.
- Explanations written for students using the **Feynman technique**:
  - 💡 **Everyday Analogies**: Intuitive real-life comparisons.
  - 📌 **Plain English**: No confusing buzzwords.
  - ⚙️ **Step-by-Step Breakdowns**: Clear numbered mechanics.
  - 🗣️ **Interview Cheat-Sheet**: What to say out loud to an interviewer.
  - 📄 **Clickable Citations `[1]`**: Direct PDF source and page references.
- Saves multi-turn chat history to PostgreSQL when logged in.

### 2. 📖 Q & A (Interview Flashcard Deck)
- Select your **Topic** (RAG, Agentic AI, Fine-Tuning, Generative AI, LLM, System Design, ML, Deep Learning, SQL).
- Choose your **Difficulty** (**Easy**, **Medium**, **Hard**).
- Immediately presents an interview-oriented question paired with a clear, student-friendly answer and exact PDF page references.
- Flip back and forth through questions using **⬅️ Previous** and **Next ➡️** buttons.

### 3. 💻 Coding Practice (AI Engineer Deck)
- Tailored coding challenges designed for real-world AI Engineer interviews.
- Select from 7 industry-standard categories:
  - **DSA for AI**: Cosine similarity from scratch, Top-K heaps, sliding-window chunkers, BPE tokenization, matrix operations.
  - **Python Essentials**: Async generators for LLM streaming, custom retry decorators, context managers for memory/VRAM, Pydantic v2 validation.
  - **FastAPI & APIs**: Server-Sent Events (SSE) token streaming, async dependency injection, background workers, rate limiting.
  - **LangChain & LCEL**: RunnablePassthrough, custom document loaders, hybrid retrievers, tool-calling agents.
  - **LangGraph Workflows**: StateGraph architectures, cyclic loops, supervisor multi-agent routing, conditional edges with error recovery.
  - **RAG & Vector Search**: Reciprocal Rank Fusion (RRF), cross-encoder rerankers, semantic chunking, cosine vs. dot product search.
  - **PyTorch & Modeling**: Scaled Dot-Product Attention from scratch, custom Datasets/DataLoaders with dynamic padding, custom loss functions.
- Includes **📋 One-Click Copy**, runnable Python code solutions with inline comments, and step-by-step intuition/complexity explanations.

### 4. 🎯 Mock Interview (Timed Simulation)
- Simulates real interview conditions with a timer.
- Type your answer and receive a fair **0–10 score**, strengths, missing gaps, and a model answer.
- Practice interviewer follow-up questions.

---

## 🏗️ Architecture & Technology Stack

| Component | Technology | Description |
|---|---|---|
| **Vector Database** | **Weaviate** `1.28.4` (Docker) | Hybrid search (BM25 + Dense embeddings) with HNSW index |
| **Embeddings** | **OpenAI `text-embedding-3-small`** | 1,536-dimensional semantic embeddings |
| **Cross-Encoder Reranker** | **FlashRank (`ms-marco-TinyBERT-L-2-v2`)** | Ultra-fast local ONNX reranker running on CPU |
| **Relational Database** | **PostgreSQL 16** (Docker) | Stores users, session auth, conversation histories, and scores |
| **Backend Framework** | **FastAPI** + **Uvicorn** | High-performance asynchronous REST API |
| **LLM Reasoning** | **OpenAI `gpt-4o-mini`** | Structured output generation for Q&A, grading, and coding |
| **Frontend UI** | **Vanilla HTML5, CSS3, JavaScript** | Fast, responsive, dark-mode glassmorphic UI |

---

## 📁 Repository Structure

```
AI_Engineer_Interview_Prepration_System/
├── pdfs/                         # 24 AI/ML & GenAI Interview Study PDFs
│   ├── 100+ genai interview question.pdf
│   ├── Agentic AI Interview Preparation Guide.pdf
│   ├── Deep Learning Notes.pdf
│   ├── Mastering Multi Agent.pdf
│   ├── Mastering RAG.pdf
│   └── ... (24 total PDFs)
├── rag_app/                      # Full-Stack Application
│   ├── app/                      # Backend Modules
│   │   ├── config.py             # Path auto-detection & settings
│   │   ├── main.py               # FastAPI server & Auth sessions
│   │   ├── rag.py                # Hybrid search & student-friendly RAG
│   │   ├── interview.py          # Mock interview generator & grader
│   │   ├── coding.py             # AI Engineer coding challenge engine
│   │   ├── ingest.py             # PDF chunking & Weaviate indexing pipeline
│   │   ├── store.py              # Weaviate & OpenAI factories
│   │   ├── rerank.py             # FlashRank ONNX cross-encoder
│   │   └── db.py                 # PostgreSQL schema & conversation storage
│   ├── static/                   # Frontend SPA
│   │   ├── index.html            # App layout & view definitions
│   │   ├── styles.css            # Custom CSS design system
│   │   └── app.js                # State management & interactive routing
│   ├── data/                     # Ingestion manifest & hashes
│   ├── docker-compose.yml        # Weaviate (port 8085) & Postgres (port 5435)
│   ├── requirements.txt          # Python dependencies
│   ├── README.md                 # App-specific documentation
│   └── .env.example              # Environment variables template
├── .gitignore                    # Git exclusions (.venv, .env, __pycache__)
└── README.md                     # Main repository documentation
```

---

## 🛠️ Quick Start Guide

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- Python 3.10+ installed
- OpenAI API Key

---

### Step 1: Clone the Repository

```bash
git clone https://github.com/JaywardhanYadav/AI_Engineer_Interview_Prepration_System.git
cd AI_Engineer_Interview_Prepration_System
```

---

### Step 2: Create & Activate Virtual Environment

**On Windows (Command Prompt - `cmd.exe`):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**On Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### Step 3: Install Dependencies

```bash
cd rag_app
pip install -r requirements.txt
```

---

### Step 4: Start Docker Services (Weaviate & PostgreSQL)

```bash
docker compose up -d
```

Verify containers are running:
```bash
docker ps --filter name=interview
```
- `interview-weaviate` runs on REST port **8085** and gRPC port **50052**.
- `interview-postgres` runs on port **5435** (to avoid conflicts with default PostgreSQL ports).

---

### Step 5: Configure Environment (`.env`)

Create `.env` from the template:

**On Windows (Command Prompt):**
```cmd
copy .env.example .env
```

**On Linux / macOS:**
```bash
cp .env.example .env
```

Open `.env` and add your OpenAI API key:
```ini
OPENAI_API_KEY=sk-...your-openai-api-key...
```

---

### Step 6: Ingest Study PDFs into Weaviate

Index the 24 study PDFs into the Weaviate vector database:

```bash
python -m app.ingest
```

*(This chunks the PDFs with overlap, computes SHA-256 deduplication hashes, and indexes vectors into Weaviate.)*

---

### Step 7: Launch the Web Application

Start the FastAPI application on port **8090**:

```bash
uvicorn app.main:app --port 8090 --reload
```

Open your browser and navigate to:
👉 **[http://localhost:8090](http://localhost:8090)**

---

## 📚 Study Material Included (`pdfs/`)

The repository includes 24 comprehensive interview preparation documents:
- **RAG**: *Mastering RAG*, advanced retrieval techniques, chunking, reranking.
- **Agentic AI**: *Mastering Multi Agent*, *Agentic AI Interview Preparation Guide*, *The Complete Agentic AI Engineer Interview Guide*.
- **LLM System Design**: *Designing Large Language Model Applications*, *Design ChatGPT*.
- **Fine-Tuning**: *LoRA vs QLoRA vs Full Fine-Tuning*, PEFT techniques.
- **Deep Learning & ML**: *Deep Learning Notes*, *Advance ML/DL Questions*, *Basic ML Interview Questions*.
- **Generative AI & Real-Time AI**: *100+ GenAI Interview Questions*, *150 Real-Time AI Interview Questions*, *GenAI Engineer Guide*.
- **SQL**: Database design, query optimization, and window functions.

---

## 🔒 Security Note
- `.env` files containing sensitive API keys are strictly excluded via `.gitignore`. Always use `.env.example` as a template for local configuration.

---

## 📄 License
This project is for educational and interview preparation purposes.
