from __future__ import annotations

import secrets
from pathlib import Path
from typing import Dict

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .schemas.chat import ChatRequest, ChatResponse, Reference
from .services.llm_service import LLMService
from .services.rag_service import RAGService
from .services.role_manager import RoleManager


app = FastAPI(
    title="FinSolve RBAC Chatbot",
    description="Role-aware RAG chatbot for FinSolve Technologies.",
    version="0.1.0",
)
security = HTTPBasic()
role_manager = RoleManager()

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


@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: Dict[str, str] = Depends(authenticate),
) -> ChatResponse:
    rag_service: RAGService = getattr(app.state, "rag_service", None)
    llm_service: LLMService = getattr(app.state, "llm_service", None)
    if not rag_service or not llm_service:
        raise HTTPException(status_code=500, detail="RAG service is not initialized.")

    role = user["role"]
    allowed_departments = role_manager.departments_for_role(role)
    if not allowed_departments:
        raise HTTPException(status_code=403, detail="Role is not authorized for any departments.")

    retrieved_contexts = rag_service.query(
        question=payload.message,
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
