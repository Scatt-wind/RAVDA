import json
from typing import Any, Literal

from openai import OpenAI

from app.config import LLM_MODEL, LLM_TIMEOUT_SEC, OPENAI_API_KEY, OPENAI_BASE_URL
from app.models.schemas import ConversationTurn, RagContext
from app.services.conversation_store import format_history_for_prompt
from app.services.rag_service import format_rag_context_for_prompt

SummarySource = Literal["llm", "rule"]


def _format_number(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}"
    text = f"{value:,.2f}"
    return text.rstrip("0").rstrip(".")


def _infer_unit(column_name: str) -> str:
    name = column_name.lower()
    if any(k in name for k in ("amount", "sales", "price", "revenue", "cost", "fee")):
        return "元"
    if any(k in column_name for k in ("额", "价", "费", "收入", "成本", "金额", "销售额")):
        return "元"
    if any(k in name for k in ("rate", "ratio", "percent", "pct")):
        return "%"
    if "率" in column_name or "占比" in column_name:
        return "%"
    return ""


def _friendly_label(column_name: str) -> str:
    mapping = {
        "sales_amount": "销售额",
        "amount": "金额",
        "price": "价格",
        "revenue": "收入",
        "cost": "成本",
        "count": "数量",
        "quantity": "数量",
        "region": "地区",
        "category": "类别",
        "product_name": "产品",
    }
    if column_name in mapping:
        return mapping[column_name]
    if column_name.lower() in mapping:
        return mapping[column_name.lower()]
    return column_name


def _format_result_summary(result: Any) -> str:
    if result is None:
        return "无结果"

    if isinstance(result, bool):
        return f"布尔结果: {'是' if result else '否'}"
    if isinstance(result, (int, float)):
        return f"数值结果: {_format_number(result)}"
    if isinstance(result, str):
        return f"文本结果: {result}"

    if isinstance(result, list):
        preview = result[:10]
        suffix = f"（共 {len(result)} 项" + ("，仅展示前 10 项" if len(result) > 10 else "") + "）"
        return "列表数据: " + json.dumps(preview, ensure_ascii=False) + suffix

    if not isinstance(result, dict):
        return f"结果: {result}"

    result_type = result.get("type")
    if result_type == "dataframe":
        rows = result.get("rows") or []
        total_rows = int(result.get("total_rows") or len(rows))
        if not rows:
            return "表格结果为空"
        lines = [
            ", ".join(f"{key}={value}" for key, value in row.items())
            for row in rows[:10]
        ]
        suffix = f"（共 {total_rows} 行"
        if total_rows > 10:
            suffix += "，仅展示前 10 行"
        suffix += "）"
        return "表格数据:\n" + "\n".join(lines) + suffix

    if result_type == "series":
        data = result.get("data") or {}
        total_items = int(result.get("total_items") or len(data))
        if not data:
            return "序列结果为空"
        preview_items = list(data.items())[:10]
        lines = [f"{key}={value}" for key, value in preview_items]
        suffix = f"（共 {total_items} 项"
        if total_items > 10:
            suffix += "，仅展示前 10 项"
        suffix += "）"
        return "序列数据:\n" + "\n".join(lines) + suffix

    preview = json.dumps(result, ensure_ascii=False)
    if len(preview) > 800:
        preview = preview[:800] + "..."
    return f"结构化结果: {preview}"


def _pick_numeric_key(row: dict[str, Any]) -> str | None:
    for key, value in row.items():
        if isinstance(value, (int, float)) and value is not None:
            return key
    return None


def _pick_dimension_key(row: dict[str, Any], metric_key: str | None) -> str | None:
    for key, value in row.items():
        if key == metric_key:
            continue
        if value is not None:
            return key
    return None


def _dataframe_top_insight(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None

    metric_key = _pick_numeric_key(rows[0])
    if metric_key is None:
        return None

    dim_key = _pick_dimension_key(rows[0], metric_key)
    ranked = sorted(
        rows,
        key=lambda row: float(row.get(metric_key) or 0),
        reverse=True,
    )
    top_row = ranked[0]
    top_value = float(top_row.get(metric_key) or 0)
    total = sum(float(row.get(metric_key) or 0) for row in rows)
    unit = _infer_unit(metric_key)

    if dim_key and top_row.get(dim_key) is not None:
        dim_label = str(top_row[dim_key])
        metric_label = _friendly_label(metric_key)
        value_text = f"{_format_number(top_value)}{unit}"
        if total > 0:
            share = top_value / total * 100
            return (
                f"{dim_label}{metric_label}最高，为 {value_text}，"
                f"占总{metric_label} {share:.1f}%。"
            )
        return f"{dim_label}{metric_label}最高，为 {value_text}。"

    metric_label = _friendly_label(metric_key)
    value_text = f"{_format_number(top_value)}{unit}"
    if total > 0 and len(rows) > 1:
        share = top_value / total * 100
        return f"{metric_label}最高值为 {value_text}，占比 {share:.1f}%。"
    return f"{metric_label}为 {value_text}。"


def _series_top_insight(data: dict[Any, Any]) -> str | None:
    numeric_items: list[tuple[Any, float]] = []
    for key, value in data.items():
        if isinstance(value, (int, float)):
            numeric_items.append((key, float(value)))

    if not numeric_items:
        return None

    numeric_items.sort(key=lambda item: item[1], reverse=True)
    top_key, top_value = numeric_items[0]
    total = sum(value for _, value in numeric_items)
    value_text = f"{_format_number(top_value)}"
    if total > 0 and len(numeric_items) > 1:
        share = top_value / total * 100
        return f"{top_key} 数值最高，为 {value_text}，占比 {share:.1f}%。"
    return f"{top_key} 的数值为 {value_text}。"


def _generate_with_rules(
    question: str,
    result: Any,
    *,
    has_charts: bool,
    success: bool,
    error: str | None,
) -> str:
    sentences: list[str] = []

    if not success:
        sentences.append(f"分析未能完成：{error or '未知错误'}。")
        return " ".join(sentences)

    if isinstance(result, dict) and result.get("type") == "dataframe":
        insight = _dataframe_top_insight(result.get("rows") or [])
        if insight:
            sentences.append(insight)
    elif isinstance(result, dict) and result.get("type") == "series":
        insight = _series_top_insight(result.get("data") or {})
        if insight:
            sentences.append(insight)
    elif isinstance(result, (int, float)):
        sentences.append(f"查询结果为 {_format_number(result)}。")
    elif isinstance(result, str) and result.strip():
        sentences.append(f"查询结果为 {result.strip()}。")

    if not sentences:
        sentences.append("已根据您的问题完成数据统计。")

    if has_charts:
        sentences.append("已同步生成可视化图表，便于对比查看。")

    summary = " ".join(sentences[:3])
    if question.strip():
        return summary
    return summary


def _generate_with_llm(
    question: str,
    result_summary: str,
    *,
    has_charts: bool,
    history: list[ConversationTurn] | None = None,
    rag_context: RagContext | None = None,
) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=LLM_TIMEOUT_SEC)
    chart_hint = "是" if has_charts else "否"
    history_block = format_history_for_prompt(history or [])
    rag_block = format_rag_context_for_prompt(rag_context)
    prompt = (
        "你是数据分析助手。请根据对话历史、用户问题、执行结果摘要和是否出图，"
        "用 2-3 句简洁的中文写出分析结论。\n"
        "要求：直接陈述发现，不要标题、列表或 Markdown；"
        "涉及数值时可保留千分位；有图表时可在结论中简要提及；"
        "若用户问题引用上文（如「该地区」「换成折线图」），请结合历史理解；"
        "语义背景仅供参考，数值以执行结果为准。\n\n"
        f"{history_block}"
        f"{rag_block}"
        f"当前用户问题：{question}\n"
        f"是否出图：{chart_hint}\n"
        f"执行结果摘要：\n{result_summary}"
    )

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "你输出简短、准确的中文数据分析结论。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
    except Exception as exc:
        raise ValueError(f"LLM summary request failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("LLM returned empty summary")

    return content.strip()


def generate_summary(
    question: str,
    result: Any,
    *,
    has_charts: bool,
    success: bool,
    error: str | None = None,
    history: list[ConversationTurn] | None = None,
    rag_context: RagContext | None = None,
) -> tuple[str, SummarySource]:
    result_summary = _format_result_summary(result)

    if OPENAI_API_KEY and success:
        try:
            return (
                _generate_with_llm(
                    question,
                    result_summary,
                    has_charts=has_charts,
                    history=history,
                    rag_context=rag_context,
                ),
                "llm",
            )
        except Exception:
            pass

    return (
        _generate_with_rules(
            question,
            result,
            has_charts=has_charts,
            success=success,
            error=error,
        ),
        "rule",
    )
