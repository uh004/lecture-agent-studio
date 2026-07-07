import os
import time
import uuid
import threading
from typing import Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.graph import build_lecture_graph

app = FastAPI(title="Lecture Agent Studio API")

# CORS 허용 (프론트엔드 연동을 위함)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 인메모리 작업 상태 저장소
jobs: Dict[str, Dict[str, Any]] = {}

def run_pipeline(job_id: str, pptx_path: str, settings: dict):
    """비동기 파이프라인 실행 스레드 함수"""
    work_dir = f"workspace/job_{job_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    initial_state = {
        "pptx_path": pptx_path,
        "work_dir": work_dir,
        "prompt": settings,
        "slide_index": 0,
    }
    
    graph_app = build_lecture_graph()
    
    try:
        jobs[job_id]["status"] = "running"
        final_state = None
        
        # 스트리밍 형태로 노드 하나씩 실행 상태 모니터링
        for output in graph_app.stream(initial_state, {"recursion_limit": 100}):
            for key, value in output.items():
                final_state = value
                
                # 현재 상태 업데이트
                current_slide = value.get("slide_index", 0) + 1
                total_slides = value.get("total_slides", 1)
                if key == "accumulate":
                    current_slide -= 1
                    if current_slide == 0: current_slide = 1
                
                jobs[job_id]["current_node"] = key
                jobs[job_id]["current_slide"] = current_slide
                jobs[job_id]["total_slides"] = total_slides
                
        # 완료 처리
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["final_video"] = final_state.get("final_video")
        
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error_message"] = str(e)


@app.post("/api/generate")
async def generate_video(
    file: UploadFile = File(...),
    tone: str = Form(...),
    style: str = Form(...),
    voice: str = Form(...),
    speed: float = Form(...),
    target_duration_sec: int = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """PPT 파일과 설정을 받아 비디오 생성 작업 시작"""
    job_id = str(uuid.uuid4())
    
    os.makedirs("data", exist_ok=True)
    file_path = f"data/{job_id}_{file.filename}"
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    settings = {
        "tone": tone,
        "style": style,
        "voice": voice,
        "speed": speed,
        "target_duration_sec": target_duration_sec
    }
    
    jobs[job_id] = {
        "status": "pending",
        "current_node": "init",
        "current_slide": 0,
        "total_slides": 0,
        "final_video": None,
        "error_message": None
    }
    
    # 백그라운드 태스크로 실행
    background_tasks.add_task(run_pipeline, job_id, file_path, settings)
    
    return {"job_id": job_id, "message": "Video generation job started"}


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    """작업 진행 상태 조회"""
    if job_id not in jobs:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    return jobs[job_id]


@app.get("/api/video/{job_id}")
def get_video(job_id: str):
    """최종 영상 파일 반환"""
    if job_id not in jobs:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    
    job_info = jobs[job_id]
    if job_info["status"] != "completed" or not job_info["final_video"]:
        return JSONResponse(status_code=400, content={"message": "Video not ready yet"})
        
    video_path = job_info["final_video"]
    if not os.path.exists(video_path):
        return JSONResponse(status_code=404, content={"message": "Video file not found"})
        
    return FileResponse(video_path, media_type="video/mp4", filename=f"lecture_{job_id}.mp4")

