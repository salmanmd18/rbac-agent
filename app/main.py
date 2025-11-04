from __future__ import annotations

import secrets
from pathlib import Path
from typing import Dict, List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

from .schemas.chat import ChatRequest, ChatResponse, Reference
from .services.llm_service import LLMService
from .services.query_classifier import QueryClassifier, QueryType
from .services.rag_service import RAGService
from .services.role_manager import RoleManager
from .services.sql_service import SQLExecutionError, SQLService, to_markdown_table


app = FastAPI(
    title="FinSolve RBAC Chatbot",
    description="Role-aware RAG chatbot for FinSolve Technologies.",
    version="0.1.0",
)
security = HTTPBasic()
role_manager = RoleManager()
query_classifier = QueryClassifier()
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = BASE_DIR / "resources" / "data"
VECTOR_STORE_DIR = BASE_DIR / "storage" / "vector_store"

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


@app.on_event("startup")
def startup_event() -> None:
    app.state.rag_service = RAGService(
        data_root=DATA_ROOT,
        persist_directory=VECTOR_STORE_DIR,
    )
    app.state.rag_service.build()
    app.state.llm_service = LLMService()
    app.state.sql_service = SQLService(data_root=DATA_ROOT)


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


@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: Dict[str, str] = Depends(authenticate),
) -> ChatResponse:
    rag_service: RAGService = getattr(app.state, "rag_service", None)
    llm_service: LLMService = getattr(app.state, "llm_service", None)
    sql_service: SQLService = getattr(app.state, "sql_service", None)
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

    if query_type == QueryType.SQL and sql_service:
        try:
            rows, columns, table_metadata = sql_service.execute(payload.message, allowed_departments)
        except SQLExecutionError as exc:
            fallback_query = (
                f"{payload.message}\n\n"
                f"(Structured query fallback triggered: {exc})"
            )
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
            return ChatResponse(answer=answer, role=role, references=references)

    retrieved_contexts = rag_service.query(
        question=fallback_query,
        departments=allowed_departments,
        top_k=payload.top_k,
    )

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
    return ChatResponse(answer=answer, role=role, references=references)
