"""数据集自然语言查询 API 模块。

提供会话管理与问答接口：将用户问题转为 Pandas 代码，在沙箱中执行，
并在失败时自动重试；最终将结果摘要与对话轮次持久化到会话存储。
"""

from fastapi import APIRouter, HTTPException

from app.config import MAX_RETRIES, OPENAI_API_KEY
from app.models.schemas import (
    ConversationTurn,
    CreateSessionResponse,
    QueryRequest,
    QueryResponse,
    SessionResponse,
)
from app.services.codegen import generate_pandas_code, regenerate_pandas_code
from app.services.conversation_store import (
    append_turn,
    create_session,
    get_latest_session_for_dataset,
    get_session,
)
from app.services.dataset_store import find_dataset_path, get_dataset_profile
from app.services.profiler import read_dataframe
from app.services.rag_service import ensure_dataset_indexed, retrieve_context
from app.services.sandbox import execute_pandas_code
from app.services.summary import generate_summary

router = APIRouter(prefix="/datasets", tags=["query"])


def _resolve_session(dataset_id: str, session_id: str | None) -> tuple[str, list[ConversationTurn]]:
    """解析或创建与数据集绑定的对话会话。

    Args:
        dataset_id: 目标数据集唯一标识。
        session_id: 已有会话 ID；为 None 时自动创建新会话。

    Returns:
        二元组 (session_id, history)：会话 ID 及该会话的历史对话轮次列表。

    Raises:
        HTTPException: 会话不存在、会话与数据集不匹配，或创建会话失败时抛出。
    """
    if session_id:
        session = get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
        # 防止客户端将会话 ID 误用于其他数据集，保证多轮上下文与数据一致
        if session.dataset_id != dataset_id:
            raise HTTPException(
                status_code=400,
                detail=f"Session '{session_id}' does not belong to dataset '{dataset_id}'",
            )
        return session_id, list(session.turns)

    try:
        new_session_id = create_session(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return new_session_id, []


@router.post("/{dataset_id}/sessions", response_model=CreateSessionResponse)
def create_dataset_session(dataset_id: str) -> CreateSessionResponse:
    """为指定数据集显式创建新的空对话会话。

    Args:
        dataset_id: 目标数据集唯一标识。

    Returns:
        包含新 session_id 与 dataset_id 的响应体。

    Raises:
        HTTPException: 数据集不存在或会话创建失败时抛出。
    """
    profile = get_dataset_profile(dataset_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")

    try:
        session_id = create_session(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return CreateSessionResponse(session_id=session_id, dataset_id=dataset_id)


@router.get("/{dataset_id}/sessions/latest", response_model=SessionResponse)
def get_latest_dataset_session(dataset_id: str) -> SessionResponse:
    """获取某数据集下最近一次创建的对话会话。

    Args:
        dataset_id: 目标数据集唯一标识。

    Returns:
        包含完整会话对象（含历史轮次）的响应体。

    Raises:
        HTTPException: 数据集不存在或尚无会话记录时抛出。
    """
    profile = get_dataset_profile(dataset_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")

    session = get_latest_session_for_dataset(dataset_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"No sessions found for dataset '{dataset_id}'")

    return SessionResponse(session=session)


@router.post("/{dataset_id}/query", response_model=QueryResponse)
def query_dataset(dataset_id: str, body: QueryRequest) -> QueryResponse:
    """对数据集发起自然语言查询的完整流水线。

    流程：校验输入 → 解析会话 → RAG 检索 → LLM 生成 Pandas 代码 →
    沙箱执行（失败则带错误信息重生成）→ 生成自然语言摘要 → 持久化对话轮次。

    Args:
        dataset_id: 目标数据集唯一标识。
        body: 查询请求体，含问题文本及可选 session_id。

    Returns:
        包含生成代码、执行结果、图表、摘要及 RAG 元信息的完整响应。

    Raises:
        HTTPException: 数据集/文件不存在、问题为空、代码生成或持久化失败时抛出。
    """
    profile = get_dataset_profile(dataset_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session_id, history = _resolve_session(dataset_id, body.session_id)
    # 查询前确保向量索引就绪，以便后续检索相关文档片段
    ensure_dataset_indexed(dataset_id)
    rag_context = retrieve_context(dataset_id, question)

    try:
        generated_code, codegen_source = generate_pandas_code(
            profile,
            question,
            history=history,
            rag_context=rag_context,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {exc}") from exc

    path = find_dataset_path(dataset_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Dataset file for '{dataset_id}' not found")

    try:
        df = read_dataframe(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    retry_count = 0
    sandbox_result = execute_pandas_code(generated_code, df)

    # 执行失败且未达重试上限、且配置了 API Key 时，将错误反馈给 LLM 重新生成代码
    while (
        not sandbox_result.success
        and retry_count < MAX_RETRIES
        and OPENAI_API_KEY
    ):
        try:
            generated_code = regenerate_pandas_code(
                profile,
                question,
                generated_code,
                sandbox_result.error or "Unknown execution error",
                history=history,
                rag_context=rag_context,
            )
            codegen_source = "llm"
        except Exception:
            # 重生成本身失败则终止重试，保留最后一次沙箱结果
            break

        retry_count += 1
        sandbox_result = execute_pandas_code(generated_code, df)

    has_charts = len(sandbox_result.charts) > 0
    try:
        summary, summary_source = generate_summary(
            question,
            sandbox_result.result,
            has_charts=has_charts,
            success=sandbox_result.success,
            error=sandbox_result.error,
            history=history,
            rag_context=rag_context,
        )
    except Exception:
        # 摘要生成失败不阻断主流程，降级为空摘要并由规则引擎兜底
        summary, summary_source = "", "rule"

    turn = ConversationTurn(
        question=question,
        summary=summary,
        generated_code=generated_code,
        success=sandbox_result.success,
        has_charts=has_charts,
        result=sandbox_result.result,
        charts=sandbox_result.charts,
        error=sandbox_result.error,
    )
    try:
        turn_index = append_turn(session_id, turn)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return QueryResponse(
        question=question,
        generated_code=generated_code,
        codegen_source=codegen_source,
        result=sandbox_result.result,
        charts=sandbox_result.charts,
        stdout=sandbox_result.stdout,
        success=sandbox_result.success,
        error=sandbox_result.error,
        attempts=retry_count,
        summary=summary,
        summary_source=summary_source,
        session_id=session_id,
        turn_index=turn_index,
        rag_used=not rag_context.skipped and len(rag_context.chunks) > 0,
        rag_chunk_count=len(rag_context.chunks),
        rag_skip_reason=rag_context.skip_reason if rag_context.skipped else None,
    )
