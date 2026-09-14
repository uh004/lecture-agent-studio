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
import textwrap
from pathlib import Path
from typing import Any, Dict, List

from src.core.config import FFMPEG_CMD, FFPROBE_CMD, PDFTOPPM_CMD, SOFFICE_CMD
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
    if not command_available(FFPROBE_CMD) and command_available(FFMPEG_CMD):
        # imageio-ffmpeg includes ffmpeg but not ffprobe. FFmpeg still prints
        # the duration and stream types without decoding the full media file.
        result = subprocess.run(
            [FFMPEG_CMD, "-hide_banner", "-i", path],
            capture_output=True,
            text=True,
        )
        metadata = f"{result.stdout}\n{result.stderr}"
        duration_match = re.search(
            r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", metadata
        )
        duration = 0.0
        if duration_match:
            hours, minutes, seconds = duration_match.groups()
            duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        has_video = bool(re.search(r"Stream .*Video:", metadata))
        has_audio = bool(re.search(r"Stream .*Audio:", metadata))
        if duration <= 0 and not (has_video or has_audio):
            raise RuntimeError(metadata.strip() or "FFmpeg 미디어 정보 확인 실패")
        return {
            "duration": duration,
            "has_video": has_video,
            "has_audio": has_audio,
            "streams": [],
        }
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


def render_slide_fallback(
    *,
    title: str,
    body_texts: List[str],
    tables: List[Any],
    images: List[str],
    output_path: str,
) -> str:
    """Create a readable slide image when LibreOffice is unavailable.

    This renderer intentionally favors reliability over pixel-perfect PPTX
    fidelity. It keeps Vercel deployments functional while local runs continue
    to use LibreOffice/Poppler when those tools are installed.
    """
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1920, 1080
    canvas = Image.new("RGB", (width, height), "#F7FAFF")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, width, 24), fill="#2563EB")
    draw.rounded_rectangle((70, 65, width - 70, height - 65), 34, fill="white")

    font_candidates = [
        os.getenv("SLIDE_FONT_PATH", ""),
        r"C:\Windows\Fonts\malgun.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    def load_font(size: int) -> Any:
        for candidate in font_candidates:
            if candidate and Path(candidate).exists():
                try:
                    return ImageFont.truetype(candidate, size=size)
                except OSError:
                    continue
        return ImageFont.load_default()

    title_font = load_font(64)
    body_font = load_font(34)
    small_font = load_font(27)
    safe_title = clean_text(title) or "강의 슬라이드"
    draw.text((125, 115), safe_title, font=title_font, fill="#172554")
    draw.line((125, 210, width - 125, 210), fill="#DBEAFE", width=4)

    text_right = 1780
    image_box = None
    usable_images = [Path(path) for path in images if path and Path(path).exists()]
    if usable_images:
        text_right = 1080
        image_box = (1135, 275, 1745, 895)

    y = 270
    max_chars = 43 if image_box else 72
    lines: List[str] = []
    for paragraph in body_texts:
        value = clean_text(paragraph)
        if not value:
            continue
        wrapped = textwrap.wrap(value, width=max_chars) or [value]
        lines.extend([f"• {wrapped[0]}", *[f"  {line}" for line in wrapped[1:]]])

    for table in tables[:1]:
        for row in table[:5]:
            row_text = "  |  ".join(clean_text(cell) for cell in row if clean_text(cell))
            if row_text:
                lines.extend(textwrap.wrap(row_text, width=max_chars) or [row_text])

    if not lines:
        lines = ["슬라이드의 시각 자료를 중심으로 설명합니다."]
    for line in lines[:15]:
        draw.text((135, y), line, font=body_font, fill="#1E293B")
        y += 51
        if y > 940:
            break

    if image_box:
        try:
            with Image.open(usable_images[0]) as source_image:
                source = source_image.convert("RGB")
                max_w = image_box[2] - image_box[0]
                max_h = image_box[3] - image_box[1]
                source.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                x = image_box[0] + (max_w - source.width) // 2
                image_y = image_box[1] + (max_h - source.height) // 2
                draw.rounded_rectangle(image_box, 24, fill="#EFF6FF")
                canvas.paste(source, (x, image_y))
        except OSError:
            pass

    draw.text(
        (125, 980),
        "Lecture Agent Studio · Vercel compatible rendering",
        font=small_font,
        fill="#64748B",
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", optimize=True)
    return str(destination)


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
        profile_dir = output_dir / "libreoffice_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        command = [
            soffice_cmd,
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--headless", "--nologo", "--nodefault", "--nolockcheck",
            "--convert-to", "pdf:impress_pdf_Export",
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
