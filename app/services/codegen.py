import re
from typing import Literal

from openai import OpenAI

from app.config import (
    LLM_MODEL,
    LLM_TIMEOUT_SEC,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
)
from app.models.schemas import ColumnProfile, ConversationTurn, DatasetProfile, RagContext
from app.services.conversation_store import format_history_for_prompt
from app.services.rag_service import format_rag_context_for_prompt

CodegenSource = Literal["llm", "rule"]


def _extract_code_block(text: str) -> str:
    fenced = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def _format_profile_context(profile: DatasetProfile) -> str:
    column_lines: list[str] = []
    for col in profile.columns:
        parts = [f"- {col.name} ({col.dtype})"]
        if col.min_value is not None:
            parts.append(f"min={col.min_value}, max={col.max_value}, mean={col.mean_value}")
        if col.top_values:
            tops = ", ".join(f"{v['value']}({v['count']})" for v in col.top_values[:3])
            parts.append(f"top: {tops}")
        column_lines.append(" ".join(parts))

    preview_text = str(profile.preview[:3])
    return (
        f"Dataset: {profile.filename} ({profile.row_count} rows, {profile.column_count} columns)\n"
        f"Columns:\n" + "\n".join(column_lines) + "\n"
        f"Preview (first rows): {preview_text}"
    )


def _build_llm_prompt(
    profile: DatasetProfile,
    question: str,
    *,
    history: list[ConversationTurn] | None = None,
    rag_context: RagContext | None = None,
) -> str:
    history_block = format_history_for_prompt(history or [])
    rag_block = format_rag_context_for_prompt(rag_context)
    return (
        "You are a data analysis assistant. Generate Python code to answer the user's question.\n"
        "If the user refers to prior results (e.g. change chart type, filter region, top N), "
        "use the conversation history below.\n\n"
        f"{_format_profile_context(profile)}\n\n"
        f"{rag_block}"
        "Available in the execution environment (do NOT import):\n"
        "- df: the pandas DataFrame\n"
        "- pd: pandas\n"
        "- np: numpy\n"
        "- plt: matplotlib.pyplot\n\n"
        "Rules:\n"
        "1. Do not use import statements\n"
        "2. Assign the final tabular or scalar answer to variable `result`\n"
        "3. For charts, use plt.figure() then plot; do not call plt.show()\n"
        "4. No file I/O, network, os, sys, subprocess, or eval\n"
        "5. Return only executable Python code\n\n"
        f"{history_block}"
        f"Current question: {question}"
    )


def _generate_with_llm(
    profile: DatasetProfile,
    question: str,
    *,
    history: list[ConversationTurn] | None = None,
    rag_context: RagContext | None = None,
) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=LLM_TIMEOUT_SEC)
    prompt = _build_llm_prompt(profile, question, history=history, rag_context=rag_context)

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You write safe pandas/matplotlib analysis code."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
    except Exception as exc:
        raise ValueError(f"LLM request failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty response")

    return _extract_code_block(content)


def _build_retry_prompt(
    profile: DatasetProfile,
    question: str,
    failed_code: str,
    error: str,
    *,
    history: list[ConversationTurn] | None = None,
    rag_context: RagContext | None = None,
) -> str:
    history_block = format_history_for_prompt(history or [])
    rag_block = format_rag_context_for_prompt(rag_context)
    return (
        "You are a data analysis assistant. The previous code failed during execution.\n"
        "Fix the code using the dataset profile, conversation history, the original question, "
        "the failed code, and the error message.\n\n"
        f"{_format_profile_context(profile)}\n\n"
        f"{rag_block}"
        "Available in the execution environment (do NOT import):\n"
        "- df: the pandas DataFrame\n"
        "- pd: pandas\n"
        "- np: numpy\n"
        "- plt: matplotlib.pyplot\n\n"
        "Rules:\n"
        "1. Do not use import statements\n"
        "2. Assign the final tabular or scalar answer to variable `result`\n"
        "3. For charts, use plt.figure() then plot; do not call plt.show()\n"
        "4. No file I/O, network, os, sys, subprocess, or eval\n"
        "5. Return only executable Python code\n\n"
        f"{history_block}"
        f"Current question: {question}\n\n"
        f"Failed code:\n```python\n{failed_code}\n```\n\n"
        f"Error:\n{error}"
    )


def regenerate_pandas_code(
    profile: DatasetProfile,
    question: str,
    failed_code: str,
    error: str,
    *,
    history: list[ConversationTurn] | None = None,
    rag_context: RagContext | None = None,
) -> str:
    if not OPENAI_API_KEY:
        raise ValueError("LLM is not configured; cannot regenerate code after failure")

    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=LLM_TIMEOUT_SEC)
    prompt = _build_retry_prompt(
        profile,
        question,
        failed_code,
        error,
        history=history,
        rag_context=rag_context,
    )

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You fix failing pandas/matplotlib analysis code based on runtime errors.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
    except Exception as exc:
        raise ValueError(f"LLM retry request failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty response on retry")

    return _extract_code_block(content)


def _is_numeric(col: ColumnProfile) -> bool:
    return col.min_value is not None or col.mean_value is not None


def _is_categorical(col: ColumnProfile) -> bool:
    return col.top_values is not None and not _is_numeric(col)


def _match_column(question: str, columns: list[ColumnProfile]) -> ColumnProfile | None:
    q_lower = question.lower()
    for col in columns:
        if col.name.lower() in q_lower:
            return col
    return None


def _pick_numeric_column(columns: list[ColumnProfile]) -> ColumnProfile | None:
    for col in columns:
        if _is_numeric(col):
            return col
    return None


def _pick_group_column(columns: list[ColumnProfile], exclude: str | None = None) -> ColumnProfile | None:
    for col in columns:
        if col.name == exclude:
            continue
        if _is_categorical(col):
            return col
    for col in columns:
        if col.name != exclude:
            return col
    return None


def _detect_chart_type(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ("饼图", "pie")):
        return "pie"
    if any(k in q for k in ("折线", "line")):
        return "line"
    return "bar"


def _detect_agg(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ("平均", "均值", "average", "mean", "avg")):
        return "mean"
    if any(k in q for k in ("数量", "计数", "count", "个数")):
        return "count"
    return "sum"


def _generate_with_rules(profile: DatasetProfile, question: str) -> str:
    columns = profile.columns
    numeric = _match_column(question, columns)
    if numeric is None or not _is_numeric(numeric):
        numeric = _pick_numeric_column(columns)

    group = _pick_group_column(columns, exclude=numeric.name if numeric else None)
    agg = _detect_agg(question)
    chart_type = _detect_chart_type(question)

    wants_chart = any(
        k in question.lower()
        for k in ("图", "chart", "plot", "可视化", "visual", "bar", "line", "pie")
    )
    wants_group = any(
        k in question.lower()
        for k in ("按", "分组", "group", "各", "每个", "per", "by")
    )

    lines: list[str] = []

    if numeric and group and (wants_group or wants_chart):
        num_col = numeric.name
        grp_col = group.name
        lines.append(f"result = df.groupby('{grp_col}')['{num_col}'].{agg}().reset_index()")
        if wants_chart:
            lines.append("plt.figure()")
            if chart_type == "pie":
                lines.append(f"plt.pie(result['{num_col}'], labels=result['{grp_col}'], autopct='%1.1f%%')")
                lines.append(f"plt.title('{num_col} by {grp_col}')")
            elif chart_type == "line":
                lines.append(f"plt.plot(result['{grp_col}'], result['{num_col}'], marker='o')")
                lines.append(f"plt.xlabel('{grp_col}')")
                lines.append(f"plt.ylabel('{num_col}')")
                lines.append(f"plt.title('{num_col} by {grp_col}')")
                lines.append("plt.xticks(rotation=45)")
            else:
                lines.append(f"plt.bar(result['{grp_col}'], result['{num_col}'])")
                lines.append(f"plt.xlabel('{grp_col}')")
                lines.append(f"plt.ylabel('{num_col}')")
                lines.append(f"plt.title('{num_col} by {grp_col}')")
                lines.append("plt.xticks(rotation=45)")
            lines.append("plt.tight_layout()")
    elif numeric:
        lines.append(f"result = df['{numeric.name}'].{agg}()")
        if wants_chart:
            lines.append("plt.figure()")
            lines.append(f"plt.hist(df['{numeric.name}'].dropna(), bins=10)")
            lines.append(f"plt.xlabel('{numeric.name}')")
            lines.append(f"plt.ylabel('count')")
            lines.append(f"plt.title('Distribution of {numeric.name}')")
            lines.append("plt.tight_layout()")
    elif group:
        lines.append(f"result = df['{group.name}'].value_counts().reset_index()")
        lines.append("result.columns = ['value', 'count']")
        if wants_chart:
            lines.append("plt.figure()")
            lines.append("plt.bar(result['value'], result['count'])")
            lines.append(f"plt.xlabel('{group.name}')")
            lines.append("plt.ylabel('count')")
            lines.append(f"plt.title('Count by {group.name}')")
            lines.append("plt.xticks(rotation=45)")
            lines.append("plt.tight_layout()")
    else:
        lines.append("result = df.describe()")

    return "\n".join(lines)


def generate_pandas_code(
    profile: DatasetProfile,
    question: str,
    *,
    history: list[ConversationTurn] | None = None,
    rag_context: RagContext | None = None,
) -> tuple[str, CodegenSource]:
    if OPENAI_API_KEY:
        try:
            return _generate_with_llm(profile, question, history=history, rag_context=rag_context), "llm"
        except Exception:
            return _generate_with_rules(profile, question), "rule"
    return _generate_with_rules(profile, question), "rule"
