# FinSolve RBAC Chatbot

Role-aware Retrieval Augmented Generation (RAG) chatbot for multi-role enterprise teams. The assistant delivers department-scoped answers by combining secure authentication, document retrieval, and structured analytics, eliminating data silos while keeping access compliant.

![Architecture](resources/architecture.png)

**How It Works (refer to diagram above)**
- **Streamlit UI** handles login, chat, and admin analytics. After authentication, the sidebar lists SQL tables available to the role and, for C-level users, shows usage metrics fed by the backend.
- **FastAPI backend** verifies credentials through HTTP Basic and identifies the caller's role. Each chat request flows through the Query Classifier to decide between structured SQL handling or unstructured RAG retrieval. Requests that violate policy receive immediate 403 responses.
- **SQL path (DuckDB)** exposes department CSVs as role-filtered views. Only single `SELECT` statements are allowed; results are formatted into markdown tables. Any SQL error or unauthorized table reference triggers an automatic fallback to the RAG path with an explanatory note.
- **RAG path (Chroma + LLM)** uses the vector store to fetch document chunks tagged with department metadata. An in-memory LRU cache avoids re-running identical searches, and an optional reranker (enabled via `ENABLE_RERANKER=true`) reorders the chunks before the LLM synthesizes the final answer. When no Groq API key is set, a deterministic summary fallback is returned for local testing.
- **LLM service & analytics** generate the final response, attach source citations, and log the interaction. The Metrics Tracker aggregates per-role totals (RAG vs SQL vs fallback), cache size, and reranker status; the `/analytics` endpoint exposes these insights to C-level accounts and the Streamlit dashboard.
- **Knowledge sources** live under `resources/data/<department>/`. Markdown/text files power the RAG workflow, while CSVs feed DuckDB. The strict directory layout ensures RBAC is enforced at ingestion, retrieval, and execution time.

## Features
- FastAPI backend with HTTP Basic authentication, centralized role mapping, and RBAC enforcement at retrieval time.
- Chroma vector store with `all-MiniLM-L6-v2` embeddings for scoped RAG responses.
- Groq LLM integration (`llama-3.1-8b-instant`) with a deterministic summary fallback when no API key is available.
- DuckDB-backed SQL path for department CSV files with strict table filtering and automatic fallback to RAG on policy or execution failures.
- Optional cross-encoder reranker (toggle with `ENABLE_RERANKER=true`) to reprioritise retrieved chunks, plus an in-memory LRU cache that avoids redundant lookups per role/message.
- Streamlit chat UI featuring login, chat history, configurable retrieval depth, surfaced SQL table list, and source citations.
- Built-in analytics endpoint (C-level only) reporting per-role usage, cache size, and reranker status; surface insights directly within the Streamlit sidebar.

## Quick Start
1. **Clone the repository**
   ```bash
   git clone https://github.com/<your-username>/rbac-agent.git
   cd rbac-agent
   ```
2. **Create a uv-managed virtual environment**
   ```bash
   uv venv .venv
   .venv\Scripts\activate          # Windows
   # source .venv/bin/activate     # macOS/Linux
   ```
3. **Install dependencies**
   ```bash
   uv pip sync requirements.lock
   # Regenerate the lock if you modify pyproject.toml:
   # uv pip compile pyproject.toml --output-file requirements.lock
   ```
4. **Configure environment variables**
   ```bash
   copy .env.example .env           # Windows
   # cp .env.example .env           # macOS/Linux
   ```
   Populate values such as:
   - `GROQ_API_KEY`: optional, enables Groq-hosted LLM responses.
   - `FINCHAT_BACKEND_URL`: backend URL used by the Streamlit app (defaults to `http://localhost:8000`).
   - `ENABLE_RERANKER`: set to `true` to load the optional cross-encoder reranker (defaults to `false`).

## Running the Backend
```bash
uvicorn app.main:app --reload
```
The API exposes:
- `GET /login`: validates credentials and returns the authenticated role.
- `POST /chat`: routes through SQL or RAG depending on the classifier while enforcing role permissions.
- `GET /roles`: lists roles with their accessible departments.
- `GET /structured-tables`: returns the SQL tables available to the caller's role.
- `GET /analytics`: usage metrics reserved for C-level accounts.
- `GET /health`: readiness probe.

SQL vector embeddings are rebuilt at startup from `resources/data/<department>/`, and structured CSV assets are loaded into DuckDB views per department.

## Streamlit Chat UI
Run the web UI in a separate terminal:
```bash
streamlit run streamlit_app.py
```
- Enter your username/password to authenticate against the FastAPI backend.
- Ask natural language questions; unstructured queries use the RAG path, while SQL-style queries (for example, `SELECT * FROM hr_hr_data WHERE performance_rating >= 4`) run against the allowed CSV tables.
- Adjust the `Top K` slider to control the number of RAG context chunks retrieved per request.
- C-level users see live analytics (query counts, cache size, reranker status) in the sidebar after each interaction.

### Sample Credentials
| Username | Password     | Role        |
|----------|--------------|-------------|
| Tony     | password123  | engineering |
| Bruce    | securepass   | marketing   |
| Sam      | financepass  | finance     |
| Natasha  | hrpass123    | hr          |
| Priya    | cboard123    | c_level     |
| Anita    | employee123  | employee    |

## Project Structure
```
app/
|-- main.py               # FastAPI entrypoint
|-- schemas/              # Pydantic request/response models
|-- services/             # RBAC, RAG, SQL, cache, reranker, metrics
resources/
|-- data/                 # Department-specific knowledge base (markdown + CSV)
`-- architecture.png      # System architecture diagram
streamlit_app.py          # Streamlit front-end
pyproject.toml            # Dependency management
requirements.lock         # Resolved dependency lock (generated by uv)
.env.example              # Sample environment configuration
tools/architecture.mmd    # Mermaid source for the architecture diagram
```

## Testing
```bash
uv run pytest
```
The suite covers the classifier heuristics, cache behaviour, analytics/authorization rules, SQL policy enforcement, and the `/chat` endpoint SQL happy path for the HR role.

## Offline Evaluation
Generate quick metrics using the built-in evaluator:
```bash
uv run python tools/offline_eval.py --dataset eval_samples.json --output results/eval.csv
```
Seed `eval_samples.json` with role-specific prompts and expected keywords to track groundedness/keyword precision. The evaluator runs entirely offline using FastAPI's TestClient.

## Extending the Solution
- Update role mappings in `app/services/role_manager.py` to add departments or tailor permissions.
- Add markdown documents to `resources/data/<department>` to expand the RAG knowledge base.
- Place CSV assets under the same department directory to expose them automatically through DuckDB.
- Swap the embedding model or vector store settings in `app/services/rag_service.py` if needed.
- Extend `app/services/reranker.py` to plug in production-grade rerankers (for example, Cohere) once API keys are available.
- Expand `app/services/metrics.py` or `/analytics` to persist metrics externally or drive richer dashboards.

> **Note:** Without a `GROQ_API_KEY`, the chatbot falls back to a deterministic summary composed from retrieved chunks, keeping the application usable for local development.
