# FinSolve RBAC Chatbot

Role-aware Retrieval Augmented Generation (RAG) chatbot built for the Codebasics [DS RPC-01 challenge](https://codebasics.io/challenge/codebasics-gen-ai-data-science-resume-project-challenge). The solution empowers FinSolve teams to query internal data with fine-grained role based access control (RBAC).

![FinSolve Overview](resources/RPC_01_Thumbnail.jpg)

## Features
- FastAPI backend with HTTP Basic authentication and centralized role management.
- Chroma vector store with `all-MiniLM-L6-v2` embeddings to power role-scoped retrieval.
- Groq LLM integration (`llama-3.1-8b-instant`) with a deterministic fallback when no API key is provided.
- Streamlit chat UI featuring login, configurable retrieval depth, chat history, and source citations.
- Extensible role mapping supporting engineering, finance, HR, marketing, employees, and C-level usage.

## Quick Start
1. **Clone the repository**
   ```bash
   git clone https://github.com/<your-username>/ds-rpc-01.git
   cd ds-rpc-01
   ```
2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # macOS/Linux
   pip install -e .
   ```
3. **(Optional) Configure environment variables**
   - `GROQ_API_KEY`: enables Groq-hosted LLM generation.
   - `FINCHAT_BACKEND_URL`: backend URL used by the Streamlit app (defaults to `http://localhost:8000`).

## Running the Backend
```bash
uvicorn app.main:app --reload
```
The API exposes:
- `GET /login`: validates credentials and returns the authenticated role.
- `POST /chat`: processes a question with RAG + LLM, respecting role permissions.
- `GET /roles`: lists the available roles and their department scopes.
- `GET /health`: simple readiness probe.

Vector embeddings are generated at startup from the documents under `resources/data` and stored in `storage/vector_store`.

### Sample Credentials
| Username | Password     | Role        |
|----------|--------------|-------------|
| Tony     | password123  | engineering |
| Bruce    | securepass   | marketing   |
| Sam      | financepass  | finance     |
| Natasha  | hrpass123    | hr          |
| Priya    | cboard123    | c_level     |
| Anita    | employee123  | employee    |

## Streamlit Chat UI
Run the web UI in a separate terminal:
```bash
streamlit run streamlit_app.py
```
- Enter your username/password to authenticate against the FastAPI backend.
- Ask natural language questions; the assistant will respond with contextual answers and cite the underlying documents.
- Adjust the `Top K` slider to control how many knowledge-base chunks are retrieved for each query.

## Project Structure
```
app/
├── main.py               # FastAPI entrypoint
├── schemas/              # Pydantic request/response models
└── services/             # RBAC, RAG, and LLM service implementations
resources/
└── data/                 # Department-specific knowledge base
streamlit_app.py          # Streamlit front-end
pyproject.toml            # Dependency management
```

## Extending the Solution
- Add or modify roles via `app/services/role_manager.py`.
- Place new documents under `resources/data/<department>`; the vector store rebuilds on startup.
- Swap the embedding model or vector store settings in `app/services/rag_service.py` if needed.

> **Note:** Without a `GROQ_API_KEY`, the chatbot falls back to a deterministic summary composed from the retrieved chunks, ensuring the app remains functional for local testing.
