"""Lecture Agent의 환경변수와 실행 도구 설정."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")


def resolve_binary(name: str, env_key: str) -> str:
    """환경변수, PATH, WinGet 설치 경로 순으로 실행 파일을 찾습니다."""
    configured = os.getenv(env_key, "").strip()
    if configured:
        return configured

    discovered = shutil.which(name)
    if discovered:
        return discovered

    if platform.system() == "Windows":
        local_app_data = os.getenv("LOCALAPPDATA", "")
        user_profile = Path(os.getenv("USERPROFILE", ""))
        python_dir = Path(sys.executable).resolve().parent
        known_candidates = {
            "soffice": [
                Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
                Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
            ],
            "pdftoppm": [
                Path(r"C:\Program Files\poppler\Library\bin\pdftoppm.exe"),
                Path(r"C:\Program Files\poppler\bin\pdftoppm.exe"),
                user_profile / "scoop" / "apps" / "poppler" / "current" / "Library" / "bin" / "pdftoppm.exe",
                python_dir / "pdftoppm.exe",
                python_dir.parent / "Library" / "bin" / "pdftoppm.exe",
            ],
        }
        for candidate in known_candidates.get(name, []):
            if candidate.exists():
                return str(candidate)

        packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if packages.exists() and name in {"ffmpeg", "ffprobe"}:
            matches = sorted(packages.glob(f"Gyan.FFmpeg*/*/bin/{name}.exe"))
            if matches:
                return str(matches[-1])
    return name


FFMPEG_CMD = resolve_binary("ffmpeg", "FFMPEG_CMD")
FFPROBE_CMD = resolve_binary("ffprobe", "FFPROBE_CMD")
SOFFICE_CMD = resolve_binary("soffice", "SOFFICE_CMD")
PDFTOPPM_CMD = resolve_binary("pdftoppm", "PDFTOPPM_CMD")
OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# 기존 Notebook 코드와의 호환성을 위한 별칭입니다.
client = OPENAI_CLIENT

MAX_SEARCH_TASKS = 2
MAX_CANDIDATES_PER_TASK = 4
MAX_EVIDENCE_PER_TASK = 2
MAX_RAW_CONTENT_CHARS = 6000

DEFAULT_RUN_OUTPUT_ROOT = PROJECT_ROOT / "notebooks" / "runs"
DEFAULT_LECTURE_CONFIG: Dict[str, Any] = {
    "tone": "에너지가 있으면서도 근거를 정확히 설명하는 전문 강사 톤",
    "style": "쉬운 비유를 사용하되 PPT와 Evidence에 없는 사례는 만들지 마세요.",
    "target_duration_sec": 70,
    "voice": "친절한 튜토리얼",
    "speed": 1.15,
}
