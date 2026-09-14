"""Lecture Agent v4 LangGraph 조립."""

from langgraph.graph import END, StateGraph

from src.core.state import AgentState
from src.nodes.analyze import node_analyze_slide
from src.nodes.media import (
    node_accumulate_and_step,
    node_concat,
    node_final_qa,
    node_make_video,
    node_tts,
    slide_router,
)
from src.nodes.parser import node_parse_ppt
from src.nodes.script import node_generate_script
from src.nodes.search import node_web_search, search_router
from src.nodes.validation import (
    node_accept_script,
    node_mark_validation_failed,
    node_validate_script,
    validation_router,
)


def build_lecture_graph():
    """Notebook에서 검증한 v4 흐름을 컴파일해 반환합니다."""
    builder = StateGraph(AgentState)
    builder.add_node("parse_ppt", node_parse_ppt)
    builder.add_node("analyze_slide", node_analyze_slide)
    builder.add_node("web_search", node_web_search)
    builder.add_node("generate_script", node_generate_script)
    builder.add_node("validate_script", node_validate_script)
    builder.add_node("accept_script", node_accept_script)
    builder.add_node("mark_validation_failed", node_mark_validation_failed)
    builder.add_node("tts", node_tts)
    builder.add_node("make_video", node_make_video)
    builder.add_node("accumulate", node_accumulate_and_step)
    builder.add_node("concat", node_concat)
    builder.add_node("final_quality_check", node_final_qa)

    builder.set_entry_point("parse_ppt")
    builder.add_edge("parse_ppt", "analyze_slide")
    builder.add_conditional_edges(
        "analyze_slide",
        search_router,
        {"search": "web_search", "skip": "generate_script"},
    )
    builder.add_edge("web_search", "generate_script")
    builder.add_edge("generate_script", "validate_script")
    builder.add_conditional_edges(
        "validate_script",
        validation_router,
        {
            "pass": "accept_script",
            "retry": "generate_script",
            "exhausted": "mark_validation_failed",
            "recheck": "validate_script",
            "system_error": "mark_validation_failed",
        },
    )
    builder.add_edge("accept_script", "tts")
    builder.add_edge("tts", "make_video")
    builder.add_edge("make_video", "accumulate")
    builder.add_edge("mark_validation_failed", "accumulate")
    builder.add_conditional_edges(
        "accumulate",
        slide_router,
        {"next": "analyze_slide", "done": "concat"},
    )
    builder.add_edge("concat", "final_quality_check")
    builder.add_edge("final_quality_check", END)
    return builder.compile()
