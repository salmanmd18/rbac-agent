from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

from .schemas.chat import ChatRequest, ChatResponse, Reference
from .services.cache import RetrievalCache
from .services.llm_service import LLMService
from .services.metrics import MetricsTracker
from .services.query_classifier import QueryClassifier, QueryType
from .services.rag_service import RAGService
from .services.reranker import RerankerService
from .services.role_manager import RoleManager
from .services.sql_service import SQLExecutionError, SQLService, to_markdown_table


LOGGER = logging.getLogger("finsolve")
logging.basicConfig(level=logging.INFO)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = BASE_DIR / "resources" / "data"
VECTOR_STORE_DIR = BASE_DIR / "storage" / "vector_store"


@asynccontextmanager
async def lifespan(app: FastAPI):
    rag_service = RAGService(
        data_root=DATA_ROOT,
        persist_directory=VECTOR_STORE_DIR,
    )
    rag_service.build()
    llm_service = LLMService()
    sql_service = SQLService(data_root=DATA_ROOT)
    enable_reranker = os.getenv("ENABLE_RERANKER", "false").lower() == "true"
    reranker_service = RerankerService(enabled=enable_reranker)
    cache_service = RetrievalCache()
    metrics_service = MetricsTracker()

    app.state.rag_service = rag_service
    app.state.llm_service = llm_service
    app.state.sql_service = sql_service
    app.state.reranker_service = reranker_service
    app.state.cache_service = cache_service
    app.state.metrics_service = metrics_service

    try:
        yield
    finally:
        cache_service.clear()


app = FastAPI(
    title="FinSolve RBAC Chatbot",
    description="Role-aware RAG chatbot for FinSolve Technologies.",
    version="0.1.0",
    lifespan=lifespan,
)
security = HTTPBasic()
role_manager = RoleManager()
query_classifier = QueryClassifier()

users_db: Dict[str, Dict[str, str]] = {
    "Tony": {"password": "password123", "role": "engineering"},
    "Bruce": {"password": "securepass", "role": "marketing"},
    "Sam": {"password": "financepass", "role": "finance"},
    "Peter": {"password": "pete123", "role": "engineering"},
    "Sid": {"password": "sidpass123", "role": "marketing"},
    "Natasha": {"password": "hrpass123", "role": "hr"},
    "Priya": {"password": "cboard123", "role": "c_level"},
    "Anita": {"password": "employee123", "role": "employee"},
}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def authenticate(credentials: HTTPBasicCredentials = Depends(security)) -> Dict[str, str]:
    username = credentials.username
    password = credentials.password
    user = users_db.get(username)
    if not user or not secrets.compare_digest(user["password"], password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return {"username": username, "role": user["role"]}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/login")
def login(user: Dict[str, str] = Depends(authenticate)) -> Dict[str, str]:
    return {"message": f"Welcome {user['username']}!", "role": user["role"]}


@app.get("/roles")
def roles() -> Dict[str, Dict[str, str]]:
    return {
        "roles": {
            role: role_manager.departments_for_role(role)
            for role in sorted({
                entry["role"]
                for entry in users_db.values()
            })
        }
    }


@app.get("/structured-tables")
def structured_tables(user: Dict[str, str] = Depends(authenticate)) -> Dict[str, List[str]]:
    sql_service: SQLService = getattr(app.state, "sql_service", None)
    if not sql_service:
        return {"tables": []}
    allowed_departments = role_manager.departments_for_role(user["role"])
    tables = sql_service.available_tables(allowed_departments)
    return {"tables": sorted(tables.keys())}


@app.get("/analytics")
def analytics(user: Dict[str, str] = Depends(authenticate)) -> Dict[str, object]:
    if user["role"] != "c_level":
        raise HTTPException(status_code=403, detail="Analytics available to C-level only.")
    metrics_service: MetricsTracker = getattr(app.state, "metrics_service", None)
    cache_service: RetrievalCache = getattr(app.state, "cache_service", None)
    reranker_service: RerankerService = getattr(app.state, "reranker_service", None)
    return {
        "queries": metrics_service.snapshot() if metrics_service else {},
        "cache_entries": cache_service.size() if cache_service else 0,
        "reranker_enabled": bool(reranker_service and reranker_service.enabled),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: Dict[str, str] = Depends(authenticate),
) -> ChatResponse:
    rag_service: RAGService = getattr(app.state, "rag_service", None)
    llm_service: LLMService = getattr(app.state, "llm_service", None)
    sql_service: SQLService = getattr(app.state, "sql_service", None)
    reranker_service: RerankerService = getattr(app.state, "reranker_service", None)
    cache_service: RetrievalCache = getattr(app.state, "cache_service", None)
    metrics_service: MetricsTracker = getattr(app.state, "metrics_service", None)
    if not rag_service or not llm_service:
        raise HTTPException(status_code=500, detail="RAG service is not initialized.")

    role = user["role"]
    allowed_departments = role_manager.departments_for_role(role)
    if not allowed_departments:
        raise HTTPException(status_code=403, detail="Role is not authorized for any departments.")

    structured_tables = []
    if sql_service:
        structured_tables = list(sql_service.available_tables(allowed_departments).keys())

    query_type = query_classifier.classify(payload.message, structured_tables)

    fallback_query = payload.message

    metrics_mode = "rag"

    if query_type == QueryType.SQL and sql_service:
        try:
            rows, columns, table_metadata = sql_service.execute(payload.message, allowed_departments)
        except SQLExecutionError as exc:
            fallback_query = (
                f"{payload.message}\n\n"
                f"(Structured query fallback triggered: {exc})"
            )
            metrics_mode = "sql_fallback"
        else:
            table_markdown = to_markdown_table(rows, columns)
            references = [
                Reference(
                    source=metadata.path.relative_to(DATA_ROOT.parent).as_posix(),
                    department=metadata.department,
                )
                for metadata in table_metadata
            ]
            answer = "Structured query result:\n\n" + table_markdown
            if metrics_service:
                metrics_service.record(role, "sql")
            LOGGER.info("chat_request role=%s mode=%s source=sql cache_hit=%s", role, "sql", False)
            return ChatResponse(answer=answer, role=role, references=references)

    cached_contexts = None
    cache_hit = False
    if cache_service:
        cached_contexts = cache_service.get(role, fallback_query)
        cache_hit = cached_contexts is not None

    if cached_contexts is not None:
        retrieved_contexts = cached_contexts
    else:
        retrieved_contexts = rag_service.query(
            question=fallback_query,
            departments=allowed_departments,
            top_k=payload.top_k,
        )
        if cache_service and retrieved_contexts:
            cache_service.set(role, fallback_query, retrieved_contexts)
    if not cache_service:
        cache_hit = False

    if reranker_service:
        retrieved_contexts = reranker_service.reorder(payload.message, retrieved_contexts)

    if not retrieved_contexts:
        return ChatResponse(
            answer="I could not find relevant information in the accessible documents.",
            role=role,
            references=[],
        )

    answer = llm_service.generate(
        question=payload.message,
        role=role,
        contexts=retrieved_contexts,
    )

    references = [
        Reference(
            source=context["source"],
            department=context["department"],
            score=context.get("score"),
        )
        for context in retrieved_contexts
        if context.get("source")
    ]
    if metrics_service:
        metrics_service.record(role, metrics_mode)
    LOGGER.info(
        "chat_request role=%s mode=%s source=rag cache_hit=%s reranker=%s",
        role,
        metrics_mode,
        cache_hit,
        bool(reranker_service and reranker_service.enabled),
    )
    return ChatResponse(answer=answer, role=role, references=references)
