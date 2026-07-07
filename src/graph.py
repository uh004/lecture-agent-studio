from langgraph.graph import StateGraph, END
from src.core.state import State
from src.nodes.extract import node_parse_all
from src.nodes.search import node_tool_search
from src.nodes.content import node_generate_page_content
from src.nodes.script import node_generate_script
from src.nodes.media import node_tts, node_make_video, node_accumulate_and_step, node_concat, router_continue_or_done


def build_lecture_graph():
    """v3 노트북과 동일한 LangGraph 워크플로우를 조립하고 반환합니다."""
    builder = StateGraph(State)

    # 노드 등록
    builder.add_node("parse_ppt", node_parse_all)
    builder.add_node("tool_search", node_tool_search)
    builder.add_node("gen_page_content", node_generate_page_content)
    builder.add_node("gen_script", node_generate_script)
    builder.add_node("tts", node_tts)
    builder.add_node("make_video", node_make_video)
    builder.add_node("accumulate", node_accumulate_and_step)
    builder.add_node("concat", node_concat)

    # 엣지 연결
    builder.set_entry_point("parse_ppt")
    builder.add_edge("parse_ppt", "tool_search")
    builder.add_edge("tool_search", "gen_page_content")
    builder.add_edge("gen_page_content", "gen_script")
    builder.add_edge("gen_script", "tts")
    builder.add_edge("tts", "make_video")
    builder.add_edge("make_video", "accumulate")
    builder.add_conditional_edges("accumulate", router_continue_or_done, {"continue": "tool_search", "done": "concat"})
    builder.add_edge("concat", END)

    # 컴파일
    return builder.compile()
