"""여러 노드가 공유하는 텍스트·상태·미디어 유틸리티."""

from __future__ import annotations

import base64
import builtins
import json
import mimetypes
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from src.core.config import FFPROBE_CMD, PDFTOPPM_CMD, SOFFICE_CMD
from src.core.state import AgentState


def safe_print(*values: Any, **kwargs: Any) -> None:
    """Windows CP949 콘솔에서도 Unicode 로그 때문에 실행이 중단되지 않게 출력합니다."""
    try:
        builtins.print(*values, **kwargs)
    except UnicodeEncodeError:
        stream = kwargs.get("file")
        encoding = getattr(stream, "encoding", None) or "cp949"
        sanitized = [
            str(value).encode(encoding, errors="replace").decode(encoding)
            for value in values
        ]
        builtins.print(*sanitized, **kwargs)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def split_sents(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", clean_text(text))
    return [part.strip() for part in parts if part.strip()]


def record_error(state: AgentState, message: str) -> None:
    state.setdefault("errors", [])
    if message not in state["errors"]:
        state["errors"].append(message)
    safe_print(f"⚠️ {message}")


def add_failed_slide(state: AgentState, slide_index: int) -> None:
    state.setdefault("failed_slides", [])
    if slide_index not in state["failed_slides"]:
        state["failed_slides"].append(slide_index)


def get_current_slide(state: AgentState) -> Dict[str, Any]:
    index = int(state.get("slide_index", 0))
    slides = state.get("slides", [])
    if index < 0 or index >= len(slides):
        raise IndexError(f"슬라이드 인덱스 범위 오류: {index}/{len(slides)}")
    return slides[index]


def reset_slide_runtime(state: AgentState) -> None:
    state["slide_analysis"] = {}
    state["search_needed"] = False
    state["search_tasks"] = []
    state["search_results"] = []
    state["evidence"] = []
    state["script_draft"] = ""
    state["script_draft_meta"] = {}
    state["script_final"] = ""
    state["validation_result"] = {}
    state["validation_feedback"] = []
    state["validation_attempt"] = 0
    state["validation_system_error"] = False
    state["validation_error_attempt"] = 0
    state["audio_path"] = ""
    state["video_path"] = ""


def build_visible_slide_context(slide: Dict[str, Any]) -> Dict[str, Any]:
    """LLM에는 발표자 노트·링크·경로를 제외한 가시 정보만 전달합니다."""
    body_text = clean_text(slide.get("body_text", slide.get("text", "")))
    return {
        "title": clean_text(slide.get("title", "")),
        "body_text": body_text,
        "tables": slide.get("tables", []),
        "charts": slide.get("charts", []),
        "shape_texts": slide.get("shape_texts", []),
        "embedded_image_count": len(slide.get("images", [])),
        "has_slide_image": bool(slide.get("slide_image", "")),
    }


def command_available(command: str) -> bool:
    return Path(command).exists() or shutil.which(command) is not None


def img_to_data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def ffprobe_media(path: str) -> Dict[str, Any]:
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"미디어 파일 없음: {path}")
    command = [
        FFPROBE_CMD,
        "-v", "error",
        "-show_entries", "format=duration",
        "-show_streams",
        "-of", "json",
        path,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe 실행 실패")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", []) or []
    duration = float((payload.get("format", {}) or {}).get("duration") or 0.0)
    return {
        "duration": duration,
        "has_video": any(stream.get("codec_type") == "video" for stream in streams),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "streams": streams,
    }


def ffprobe_duration(path: str) -> float:
    return float(ffprobe_media(path)["duration"])


def resolve_soffice() -> str:
    return SOFFICE_CMD


def export_slide_as_png(pptx_path: str, work_dir: str, slide_index: int, dpi: int = 220) -> str:
    pptx = Path(pptx_path).expanduser().resolve()
    output_dir = Path(work_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not pptx.exists():
        raise FileNotFoundError(f"PPTX 없음: {pptx}")

    soffice_cmd = resolve_soffice()
    pdftoppm_cmd = PDFTOPPM_CMD
    if not command_available(soffice_cmd):
        raise RuntimeError("LibreOffice soffice 실행 파일을 찾을 수 없습니다.")
    if not command_available(pdftoppm_cmd):
        raise RuntimeError("Poppler pdftoppm 실행 파일을 찾을 수 없습니다.")

    pdf_path = output_dir / f"{pptx.stem}.pdf"
    pdf_is_stale = not pdf_path.exists() or pdf_path.stat().st_mtime < pptx.stat().st_mtime
    if pdf_is_stale:
        command = [
            soffice_cmd, "--headless", "--convert-to", "pdf:impress_pdf_Export",
            "--outdir", str(output_dir), str(pptx),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0 or not pdf_path.exists():
            raise RuntimeError(result.stderr.strip() or "PPTX → PDF 변환 실패")

    page_number = int(slide_index) + 1
    output_prefix = output_dir / "slide_render"
    png_path = output_dir / f"slide_render-{page_number}.png"
    command = [
        pdftoppm_cmd, "-f", str(page_number), "-l", str(page_number),
        "-png", "-r", str(dpi), str(pdf_path), str(output_prefix),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not png_path.exists():
        raise RuntimeError(result.stderr.strip() or f"슬라이드 {page_number} PNG 변환 실패")
    return str(png_path)
