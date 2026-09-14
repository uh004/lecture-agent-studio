"""Notebook과 API가 공유하는 Lecture Agent 실행 서비스."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from src.core.runtime import build_initial_state, create_run_directory
from src.core.state import AgentState
from src.graph import build_lecture_graph
from src.infrastructure.job_store import JobStore
from src.infrastructure.object_storage import ObjectStorage


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


def update_job_progress(
    job_store: JobStore,
    job_id: str,
    node_name: str,
    state: Dict[str, Any],
) -> None:
    """Persist graph progress so the existing frontend can keep polling."""
    total_slides = max(0, int(state.get("total_slides", 0)))
    slide_index = max(0, int(state.get("slide_index", 0)))
    if node_name == "accumulate":
        current_slide = slide_index
    elif node_name in {"concat", "final_quality_check"}:
        current_slide = total_slides
    else:
        current_slide = min(total_slides, slide_index + 1) if total_slides else 0
    job_store.update(
        job_id,
        current_node=node_name,
        current_slide=current_slide,
        total_slides=total_slides,
    )


def process_lecture_job(
    job_id: str,
    job_store: JobStore,
    object_storage: ObjectStorage,
    *,
    work_root: Optional[PathLike] = None,
    cleanup: bool = True,
) -> None:
    """Run one queued lecture job outside the request/response lifecycle."""
    job = job_store.get(job_id)
    if job is None:
        raise KeyError(f"작업을 찾을 수 없습니다: {job_id}")
    if job.get("status") == "completed":
        return

    base_root = Path(
        work_root
        or os.getenv("WORKER_WORK_ROOT", "")
        or (Path(tempfile.gettempdir()) / "lecture-agent-worker")
    ).expanduser().resolve()
    job_root = base_root / job_id
    input_dir = job_root / "input"
    work_dir = job_root / "work"
    input_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    job_store.update(job_id, status="running", current_node="download_source")
    try:
        original_name = Path(str(job.get("original_name") or "lecture.pptx")).name
        source_url = str(job.get("source_url") or "")
        source_path = str(job.get("source_path") or "")
        if source_url:
            pptx_path = object_storage.download(source_url, input_dir / original_name)
        elif source_path:
            pptx_path = Path(source_path).expanduser().resolve()
        else:
            raise RuntimeError("작업에 원본 PPTX 위치가 없습니다.")

        final_state = run_lecture_agent(
            pptx_path,
            lecture_config=dict(job.get("settings", {}) or {}),
            work_dir=work_dir,
            recursion_limit=1000,
            on_node=lambda node, state: update_job_progress(
                job_store, job_id, node, state
            ),
        )

        final_video = str(final_state.get("final_video", ""))
        final_status = str(final_state.get("final_status", "failed"))
        final_qa = dict(final_state.get("final_qa", {}) or {})
        errors = list(final_state.get("errors", []) or [])
        total_slides = int(final_state.get("total_slides", 0))

        if final_video and final_status in {"completed", "partial_completed"}:
            published = object_storage.publish_video(Path(final_video), job_id)
            job_store.update(
                job_id,
                status="completed",
                final_status=final_status,
                final_qa=final_qa,
                errors=errors,
                current_slide=total_slides,
                total_slides=total_slides,
                final_video_path=(
                    final_video if published["storage"] == "local" else None
                ),
                final_video_url=published["url"],
                final_download_url=published["download_url"],
                storage=published["storage"],
            )
        else:
            job_store.update(
                job_id,
                status="error",
                final_status=final_status,
                final_qa=final_qa,
                errors=errors,
                current_slide=total_slides,
                total_slides=total_slides,
                error_message=(
                    errors[-1] if errors else "최종 영상을 생성하지 못했습니다."
                ),
            )
    except Exception as exc:
        job_store.update(job_id, status="error", error_message=str(exc))
        raise
    finally:
        if cleanup:
            shutil.rmtree(job_root, ignore_errors=True)
