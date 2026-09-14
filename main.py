"""Lecture Agent Studio FastAPI entrypoint.

Local development uses process memory and local files. On Vercel, the same API
uses Upstash Redis for job state/queueing and Vercel Blob for source and output files.
"""

from __future__ import annotations

import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pptx import Presentation

from src.infrastructure import create_job_store, create_object_storage
from src.service import process_lecture_job


app = FastAPI(title="Lecture Agent Studio API", version="1.1.0")

configured_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
allowed_origins = [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX", "").strip() or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

job_store = create_job_store()
object_storage = create_object_storage()
is_vercel = bool(os.getenv("VERCEL"))


def _job_root(job_id: str) -> Path:
    return Path("workspace") / f"job_{job_id}"


def run_local_pipeline(job_id: str) -> None:
    """Keep the original background behavior for local development only."""
    try:
        process_lecture_job(
            job_id,
            job_store,
            object_storage,
            work_root=Path("workspace"),
            cleanup=False,
        )
    except Exception as exc:
        print(f"로컬 작업 실행 실패 ({job_id}): {exc}")


def wake_worker() -> None:
    """Wake a sleeping web-service worker; the Redis queue remains authoritative."""
    worker_url = os.getenv("WORKER_URL", "").strip().rstrip("/")
    if not worker_url:
        return
    request = Request(
        f"{worker_url}/health",
        method="GET",
        headers={"User-Agent": "lecture-agent-api/1.0"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            response.read(1)
    except (HTTPError, URLError, TimeoutError) as exc:
        # The job is already durable in Redis. A persistent worker, a later
        # health check, or a platform restart can still consume it.
        print(f"Worker wake request failed: {exc}")


def _require_vercel_integrations() -> None:
    missing = []
    if not job_store.is_durable:
        missing.append("Upstash Redis")
    if not object_storage.is_remote:
        missing.append("Vercel Blob")
    if is_vercel and missing:
        raise HTTPException(
            status_code=503,
            detail="Vercel 프로젝트에 다음 Storage 연동이 필요합니다: " + ", ".join(missing),
        )


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    ready = not is_vercel or (job_store.is_durable and object_storage.is_remote)
    return {
        "status": "ok" if ready else "needs_configuration",
        "runtime": "vercel" if is_vercel else "local",
        "job_store": job_store.backend,
        "object_storage": object_storage.backend,
        "execution": "redis_queue" if is_vercel else "local_background",
        "ready": ready,
    }


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
    """Accept a PPTX and start an asynchronous lecture-video job."""
    _require_vercel_integrations()

    original_name = Path(file.filename or "lecture.pptx").name
    if Path(original_name).suffix.lower() != ".pptx":
        raise HTTPException(status_code=400, detail=".pptx 파일만 업로드할 수 있습니다.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="업로드한 파일이 비어 있습니다.")
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기는 100MB 이하여야 합니다.")

    try:
        slide_count = len(Presentation(BytesIO(content)).slides)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"올바른 PPTX 파일이 아닙니다: {exc}") from exc
    if slide_count == 0:
        raise HTTPException(status_code=400, detail="PPTX에 슬라이드가 없습니다.")
    max_slides = max(1, int(os.getenv("MAX_SLIDES", "100")))
    if slide_count > max_slides:
        raise HTTPException(
            status_code=422,
            detail=f"한 작업에서 처리할 수 있는 최대 슬라이드는 {max_slides}장입니다.",
        )

    job_id = str(uuid.uuid4())
    settings = {
        "tone": tone,
        "style": style,
        "voice": voice,
        "speed": speed,
        "target_duration_sec": target_duration_sec,
    }
    job_store.create(
        job_id,
        {
            "status": "pending",
            "current_node": "init",
            "current_slide": 0,
            "total_slides": slide_count,
            "final_video_path": None,
            "final_video_url": None,
            "final_download_url": None,
            "storage": None,
            "final_status": "running",
            "final_qa": {},
            "errors": [],
            "error_message": None,
            "original_name": original_name,
            "settings": settings,
            "source_url": None,
            "source_path": None,
        },
    )

    if is_vercel:
        try:
            uploaded = object_storage.publish_source(content, job_id, original_name)
            job_store.update(job_id, source_url=uploaded["url"])
            job_store.enqueue(job_id)
            wake_worker()
        except Exception as exc:
            job_store.update(job_id, status="error", error_message=str(exc))
            raise HTTPException(
                status_code=503,
                detail=f"작업 큐에 등록하지 못했습니다: {exc}",
            ) from exc
    else:
        upload_dir = _job_root(job_id) / "input"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{job_id}_{original_name}"
        file_path.write_bytes(content)
        job_store.update(job_id, source_path=str(file_path.resolve()))
        background_tasks.add_task(run_local_pipeline, job_id)

    return {"job_id": job_id, "message": "강의 영상 생성을 시작했습니다."}


@app.get("/api/status/{job_id}")
def get_status(job_id: str) -> Dict[str, Any]:
    """Return durable progress for the frontend polling screen."""
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    response = {
        key: value
        for key, value in job.items()
        if key not in {
            "final_video_path",
            "final_video_url",
            "final_download_url",
            "source_path",
            "source_url",
            "settings",
        }
    }
    response["video_url"] = f"/api/video/{job_id}" if job["status"] == "completed" else None
    return response


@app.get("/api/video/{job_id}", response_model=None)
def get_video(job_id: str) -> FileResponse | RedirectResponse:
    """Return a local MP4 or redirect to its durable Vercel Blob URL."""
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="영상이 아직 준비되지 않았습니다.")

    remote_url = str(job.get("final_video_url") or "")
    if job.get("storage") == "vercel_blob" and remote_url:
        return RedirectResponse(remote_url, status_code=307)

    local_path = Path(str(job.get("final_video_path") or ""))
    if not local_path.exists():
        raise HTTPException(status_code=404, detail="영상 파일을 찾을 수 없습니다.")
    return FileResponse(
        local_path,
        media_type="video/mp4",
        filename=f"lecture_{job_id}.mp4",
    )
