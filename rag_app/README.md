# Interview RAG Coach (Weaviate + PostgreSQL + FlashRank Reranker)

A production-grade RAG application built on your AI/ML interview study materials in `D:\Study\AIML Interview Questions`.

## 🎓 4 Practice Modes
1. **💬 Ask & Learn**:
   - Ask any free-form AI/ML question.
   - Get plain-English explanations with analogies, step-by-step breakdowns, and PDF citations.
   - Saves conversations to PostgreSQL when logged in.
2. **📖 Q & A (Interview Practice Deck)**:
   - Select your **Topic** (RAG, Agentic AI, Fine-Tuning, Generative AI, LLM, System Design, ML, Deep Learning, SQL).
   - Select your **Difficulty** (Easy, Medium, Hard).
   - Directly displays interview-oriented questions paired with intuitive, student-friendly answers and exact PDF page references.
   - Includes **⬅️ Previous** and **Next ➡️** navigation buttons to easily flip through study cards.
3. **💻 Coding (AI Engineer Coding Deck)**:
   - Select your **Category**:
     - **DSA for AI** (Cosine similarity, Top-K heaps, sliding window, tokenizers, matrix ops)
     - **Python Essentials** (Async generators, custom decorators, context managers, Pydantic v2)
     - **FastAPI & APIs** (SSE LLM token streaming, async DI, background tasks, rate limiting)
     - **LangChain & LCEL** (Custom chains, retrievers, document splitters, tool agents)
     - **LangGraph Workflows** (StateGraph cyclic loops, supervisor routing, conditional edges)
     - **RAG & Vector Search** (Hybrid search, RRF fusion, cross-encoder reranking, chunking)
     - **PyTorch & Modeling** (Scaled dot-product attention, custom Datasets, loss functions)
   - Select your **Difficulty** (Easy, Medium, Hard).
   - Directly displays the realistic interview coding problem, runnable Python code solution with a 📋 Copy button, step-by-step explanation, complexity & edge-case notes, and PDF citations.
   - Includes **⬅️ Previous** and **Next ➡️** navigation buttons.
4. **🎯 Mock Interview**:
   - Tests you under interview conditions with a timer.
   - Type your answer and receive a fair 0–10 score, strengths, missing points, and a model answer.

---

## 🛠️ Quick Start (Windows Command Prompt - `cmd.exe`)

Open **Command Prompt (`cmd.exe`)**:

### 1. Navigate to Project & Activate Virtual Environment
```cmd
cd "D:\Study\AIML Interview Questions\rag_app"
..\.venv\Scripts\activate.bat
```

### 2. Install Dependencies (If not already installed)
```cmd
pip install -r requirements.txt
```

### 3. Start Docker Containers (Weaviate & PostgreSQL)
```cmd
docker compose up -d
```
Verify both containers are running:
```cmd
docker ps --filter name=interview
```
*(You will see `interview-weaviate` on port 8085 and `interview-postgres` on port 5435)*

### 4. Setup Environment File (`.env`)
```cmd
copy .env.example .env
```
Ensure your `OPENAI_API_KEY` is set in `.env`.

### 5. Run Ingestion (Only once or when adding new PDFs)
```cmd
python -m app.ingest
```

### 6. Start the Web Application (Port 8090)
```cmd
uvicorn app.main:app --port 8090 --reload
```
Open **http://127.0.0.1:8090** in your browser!

---

## 🔐 User Accounts & Conversations
1. Click **🔐 Sign In / Register** in the bottom-left sidebar.
2. Create an account or sign in with your username and password.
3. All your Q&A chats are automatically saved under **Chats** in the sidebar.
4. You can switch between conversations, start a **+ New Chat**, or delete older chats anytime.

---

## 🛑 How to Stop
- **Stop Web Server**: Press `Ctrl + C` in your command prompt.
- **Deactivate Environment**: `deactivate`
- **Stop Docker Containers**: `docker compose down` (data is preserved in Docker volumes).
