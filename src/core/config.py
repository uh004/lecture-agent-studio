import os
import platform
from dotenv import load_dotenv
from openai import OpenAI

# ============================================================
# 환경변수 로드
# ============================================================
load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Models
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")

# OpenAI 클라이언트 (전역 1개)
client = OpenAI(api_key=OPENAI_API_KEY)

# ============================================================
# FFmpeg / FFprobe 경로 통일 (v3: Windows 자동 탐색)
# ============================================================
FFMPEG_CMD = "ffmpeg"
FFPROBE_CMD = "ffprobe"

if platform.system() == "Windows":
    winget_ffmpeg = r"C:\Users\USER\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
    winget_ffprobe = r"C:\Users\USER\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffprobe.exe"
    if os.path.exists(winget_ffmpeg):
        FFMPEG_CMD = winget_ffmpeg
    if os.path.exists(winget_ffprobe):
        FFPROBE_CMD = winget_ffprobe

# 작업 디렉토리 기본값
DEFAULT_WORKSPACE = "workspace/output_v3"
