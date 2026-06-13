from typing import Any

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_rate: float = Field(ge=0, le=1)
    unique_count: int = Field(ge=0)
    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None
    top_values: list[dict[str, Any]] | None = None
    date_min: str | None = None
    date_max: str | None = None


class DatasetProfile(BaseModel):
    dataset_id: str
    filename: str
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    columns: list[ColumnProfile]
    preview: list[dict[str, Any]]


class UploadResponse(BaseModel):
    message: str
    profile: DatasetProfile
    rag_index_status: str = Field(
        default="pending",
        description="RAGFlow index status: pending, indexing, ready, failed, skipped",
    )
    deduplicated: bool = Field(
        default=False,
        description="True when upload matched an existing file by content hash",
    )


class DatasetSummary(BaseModel):
    dataset_id: str
    original_filename: str
    file_size_bytes: int = Field(ge=0)
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    created_at: str
    rag_index_status: str = "pending"


class DatasetListResponse(BaseModel):
    datasets: list[DatasetSummary]
    total: int = Field(ge=0)


class DatasetDetailResponse(BaseModel):
    profile: DatasetProfile
    rag_index_status: str = "pending"


class DatasetRagStatusResponse(BaseModel):
    dataset_id: str
    rag_index_status: str
    ragflow_kb_id: str | None = None
    rag_index_error: str | None = None
    rag_configured: bool = False


class HealthResponse(BaseModel):
    status: str
    service: str
    rag_configured: bool = False


class RagChunk(BaseModel):
    content: str
    document_name: str = ""
    similarity: float = Field(default=0.0, ge=0)


class RagContext(BaseModel):
    chunks: list[RagChunk] = Field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, description="Optional conversation session id")


class ConversationTurn(BaseModel):
    question: str
    summary: str = ""
    generated_code: str | None = None
    success: bool = True
    has_charts: bool = False
    result: Any | None = None
    charts: list["ChartArtifact"] = Field(default_factory=list)
    error: str | None = None


class ConversationSession(BaseModel):
    session_id: str
    dataset_id: str
    created_at: str
    updated_at: str
    turns: list[ConversationTurn] = Field(default_factory=list)


class CreateSessionResponse(BaseModel):
    session_id: str
    dataset_id: str


class SessionResponse(BaseModel):
    session: ConversationSession


class ChartArtifact(BaseModel):
    format: str = "png"
    data: str = Field(description="Base64-encoded image data")
    width: int | None = None
    height: int | None = None


class QueryResponse(BaseModel):
    question: str
    generated_code: str
    codegen_source: str = Field(description="llm or rule")
    result: Any | None = None
    charts: list[ChartArtifact] = Field(default_factory=list)
    stdout: str = ""
    success: bool
    error: str | None = None
    attempts: int = Field(default=0, ge=0, description="Number of retries after failed execution")
    summary: str = ""
    summary_source: str = Field(default="rule", description="llm or rule")
    session_id: str | None = None
    turn_index: int = Field(default=0, ge=0, description="Zero-based index of this turn in the session")
    rag_used: bool = Field(default=False, description="Whether RAG retrieval contributed context")
    rag_chunk_count: int = Field(default=0, ge=0, description="Number of RAG chunks injected into codegen")
    rag_skip_reason: str | None = Field(
        default=None,
        description="Why RAG was skipped, e.g. index_pending, not_configured",
    )


ConversationTurn.model_rebuild()
