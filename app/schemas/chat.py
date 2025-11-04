from typing import List, Optional

from pydantic import BaseModel, Field


class Reference(BaseModel):
    source: str = Field(..., description="Relative path to the source document chunk.")
    department: str = Field(..., description="Document department (role scope).")
    score: Optional[float] = Field(
        default=None,
        description=(
            "Similarity score normalized to 0-1 range where higher means more relevant."
        ),
    )


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User's natural language query.")
    top_k: int = Field(
        default=4,
        ge=1,
        le=8,
        description="Number of knowledge base chunks to retrieve for context.",
    )


class ChatResponse(BaseModel):
    answer: str = Field(..., description="LLM generated response.")
    role: str = Field(..., description="Role inferred from the authenticated user.")
    references: List[Reference] = Field(default_factory=list)
