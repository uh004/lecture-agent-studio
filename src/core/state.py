"""LangGraph 전체 노드가 공유하는 상태 계약."""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class AgentState(TypedDict, total=False):
    # 입력
    pptx_path: str
    work_dir: str
    lecture_config: Dict[str, Any]
    prompt: Dict[str, Any]  # 기존 FastAPI v3 입력과의 임시 호환 필드

    # PPT
    slides: List[Dict[str, Any]]
    total_slides: int
    slide_index: int

    # 슬라이드 이해
    slide_analysis: Dict[str, Any]
    search_needed: bool
    search_tasks: List[Dict[str, Any]]

    # 검색 / 근거
    search_results: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]

    # Script
    script_draft: str
    script_draft_meta: Dict[str, Any]
    script_final: str
    all_scripts: List[str]

    # Validation
    validation_result: Dict[str, Any]
    validation_feedback: List[str]
    validation_attempt: int
    max_validation_attempts: int
    validation_system_error: bool
    validation_error_attempt: int
    max_validation_error_retries: int

    # Media
    audio_path: str
    video_path: str
    video_paths: List[str]

    # 결과
    failed_slides: List[int]
    failed_slide_details: List[Dict[str, Any]]
    errors: List[str]
    final_video: str
    final_qa: Dict[str, Any]
    final_status: str


# v3에서 State를 import하던 외부 코드가 즉시 깨지지 않도록 유지합니다.
State = AgentState
