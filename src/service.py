"""Notebook과 API가 공유하는 Lecture Agent 실행 서비스."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from src.core.runtime import build_initial_state, create_run_directory
from src.core.state import AgentState
from src.graph import build_lecture_graph


PathLike = Union[str, Path]
NodeCallback = Callable[[str, AgentState], None]


def run_lecture_agent(
    pptx_path: PathLike,
    lecture_config: Optional[Dict[str, Any]] = None,
    *,
    output_root: Optional[PathLike] = None,
    work_dir: Optional[PathLike] = None,
    recursion_limit: int = 1000,
    on_node: Optional[NodeCallback] = None,
) -> AgentState:
    """새 실행 폴더를 만들고 v4 Graph를 끝까지 실행합니다."""
    source = Path(pptx_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"PPTX 파일이 존재하지 않습니다: {source}")

    run_dir = (
        Path(work_dir).expanduser().resolve()
        if work_dir is not None
        else create_run_directory(source, output_root)
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    state = build_initial_state(source, run_dir, lecture_config)
    graph = build_lecture_graph()

    final_state: Optional[AgentState] = None
    for graph_output in graph.stream(state, {"recursion_limit": recursion_limit}):
        for node_name, node_state in graph_output.items():
            final_state = node_state
            if on_node is not None:
                on_node(node_name, node_state)

    if final_state is None:
        raise RuntimeError("그래프가 최종 상태를 반환하지 않았습니다.")
    return final_state
