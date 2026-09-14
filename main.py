"""Lecture Agent Studio FastAPI entrypoint."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Annotated, Any, Dict

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.service import run_lecture_agent


app = FastAPI(title="Lecture Agent Studio API", version="1.0.0")

configured_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
allowed_origins = [origin.strip() for origin in configured_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 로컬 MVP용 메모리 저장소입니다. 서버가 재시작되면 작업 목록은 초기화됩니다.
jobs: Dict[str, Dict[str, Any]] = {}


def _update_job_progress(job_id: str, node_name: str, state: Dict[str, Any]) -> None:
    total_slides = max(0, int(state.get("total_slides", 0)))
    slide_index = max(0, int(state.get("slide_index", 0)))

    if node_name == "accumulate":
        current_slide = slide_index
    elif node_name in {"concat", "final_quality_check"}:
        current_slide = total_slides
    else:
        current_slide = min(total_slides, slide_index + 1) if total_slides else 0

    jobs[job_id].update(
        current_node=node_name,
        current_slide=current_slide,
        total_slides=total_slides,
    )


def run_pipeline(job_id: str, pptx_path: str, settings: Dict[str, Any]) -> None:
    """업로드된 PPT를 v4 서비스로 실행하고 공개할 작업 상태를 갱신합니다."""
    work_dir = Path("workspace") / f"job_{job_id}"
    jobs[job_id]["status"] = "running"

    try:
        final_state = run_lecture_agent(
            pptx_path,
            lecture_config=settings,
            work_dir=work_dir,
            recursion_limit=1000,
            on_node=lambda node, state: _update_job_progress(job_id, node, state),
        )

        final_video = str(final_state.get("final_video", ""))
        final_status = str(final_state.get("final_status", "failed"))
        final_qa = dict(final_state.get("final_qa", {}) or {})
        errors = list(final_state.get("errors", []) or [])

        jobs[job_id].update(
            final_video=final_video or None,
            final_status=final_status,
            final_qa=final_qa,
            errors=errors,
            current_slide=int(final_state.get("total_slides", 0)),
            total_slides=int(final_state.get("total_slides", 0)),
        )

        if final_video and final_status in {"completed", "partial_completed"}:
            jobs[job_id]["status"] = "completed"
        else:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error_message"] = (
                errors[-1] if errors else "최종 영상을 생성하지 못했습니다."
            )
    except Exception as exc:
        jobs[job_id].update(
            status="error",
            error_message=str(exc),
        )


@app.get("/api/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/generate")
async def generate_video(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="강의로 변환할 PPTX 파일")],
    tone: Annotated[str, Form(min_length=1, max_length=200)] = "친절하고 명료한 강사 톤",
    style: Annotated[str, Form(min_length=1, max_length=300)] = "핵심을 쉬운 표현으로 자연스럽게 설명",
    voice: Annotated[str, Form()] = "친절한 튜토리얼",
    speed: Annotated[float, Form(ge=0.5, le=2.0)] = 1.15,
    target_duration_sec: Annotated[int, Form(ge=15, le=180)] = 70,
) -> Dict[str, str]:
    """PPTX와 강의 설정을 받아 비동기 영상 생성 작업을 시작합니다."""
    original_name = Path(file.filename or "lecture.pptx").name
    if Path(original_name).suffix.lower() != ".pptx":
        raise HTTPException(status_code=400, detail=".pptx 파일만 업로드할 수 있습니다.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="업로드한 파일이 비어 있습니다.")
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기는 100MB 이하여야 합니다.")

    job_id = str(uuid.uuid4())
    upload_dir = Path("data")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{job_id}_{original_name}"
    file_path.write_bytes(content)

    settings = {
        "tone": tone,
        "style": style,
        "voice": voice,
        "speed": speed,
        "target_duration_sec": target_duration_sec,
    }
    jobs[job_id] = {
        "status": "pending",
        "current_node": "init",
        "current_slide": 0,
        "total_slides": 0,
        "final_video": None,
        "final_status": "running",
        "final_qa": {},
        "errors": [],
        "error_message": None,
    }

    background_tasks.add_task(run_pipeline, job_id, str(file_path), settings)
    return {"job_id": job_id, "message": "강의 영상 생성을 시작했습니다."}


@app.get("/api/status/{job_id}")
def get_status(job_id: str) -> Dict[str, Any]:
    """프론트엔드에서 사용할 작업 진행 상태를 반환합니다."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    response = {key: value for key, value in job.items() if key != "final_video"}
    response["video_url"] = f"/api/video/{job_id}" if job["status"] == "completed" else None
    return response


@app.get("/api/video/{job_id}")
def get_video(job_id: str) -> FileResponse:
    """완성된 MP4 파일을 재생하거나 다운로드할 수 있도록 반환합니다."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job["status"] != "completed" or not job.get("final_video"):
        raise HTTPException(status_code=400, detail="영상이 아직 준비되지 않았습니다.")

    video_path = Path(str(job["final_video"]))
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="영상 파일을 찾을 수 없습니다.")

    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"lecture_{job_id}.mp4",
    )
