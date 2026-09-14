"""실행별 작업 폴더와 초기 State 생성."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from src.core.config import DEFAULT_LECTURE_CONFIG, DEFAULT_RUN_OUTPUT_ROOT
from src.core.state import AgentState


PathLike = Union[str, Path]


def create_run_directory(pptx_path: PathLike, output_root: Optional[PathLike] = None) -> Path:
    """PPT 이름과 현재 시각을 사용해 충돌하지 않는 새 실행 폴더를 만듭니다."""
    root = Path(output_root or DEFAULT_RUN_OUTPUT_ROOT).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = root / f"{Path(pptx_path).stem}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def build_initial_state(
    pptx_path: PathLike,
    work_dir: PathLike,
    lecture_config: Optional[Dict[str, Any]] = None,
) -> AgentState:
    """Notebook과 향후 API가 공유하는 초기 State를 생성합니다."""
    config = dict(DEFAULT_LECTURE_CONFIG)
    config.update(lecture_config or {})
    return {
        "pptx_path": str(pptx_path),
        "work_dir": str(Path(work_dir).expanduser().resolve()),
        "lecture_config": config,
        "slide_index": 0,
        "all_scripts": [],
        "video_paths": [],
        "failed_slides": [],
        "failed_slide_details": [],
        "errors": [],
        "validation_attempt": 0,
        "max_validation_attempts": 2,
        "validation_error_attempt": 0,
        "max_validation_error_retries": 1,
        "final_status": "running",
    }
