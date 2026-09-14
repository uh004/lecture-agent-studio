"""Node 6~10: TTS, 슬라이드 영상, 병합 및 Final QA."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import List

from src.core.config import FFMPEG_CMD, OPENAI_CLIENT, TTS_MODEL
from src.core.state import AgentState
from src.core.utils import (
    add_failed_slide,
    clean_text,
    command_available,
    ffprobe_duration,
    ffprobe_media,
    get_current_slide,
    record_error,
    reset_slide_runtime,
    safe_print,
)


print = safe_print


EDUCATION_VOICES = {
    "부드러운 설명형": "nova",
    "교수님 톤": "alloy",
    "친절한 튜토리얼": "shimmer",
    "명확한 설명형": "onyx",
}


def node_tts(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    print(f"\n--- Node 6: 슬라이드 {index + 1} TTS ---")
    state["audio_path"] = ""
    script = clean_text(state.get("script_final", ""))
    validation_status = (state.get("validation_result", {}) or {}).get("status")
    if validation_status != "PASS":
        record_error(state, f"슬라이드 {index + 1} 검증 PASS가 아님: TTS를 건너뜁니다.")
        return state
    if not script:
        record_error(state, f"슬라이드 {index + 1} 승인 Script 없음: TTS를 건너뜁니다.")
        return state
    if OPENAI_CLIENT is None:
        record_error(state, f"슬라이드 {index + 1} OpenAI API 키 없음: TTS를 실행할 수 없습니다.")
        return state

    config = state.get("lecture_config", {}) or {}
    requested_voice = clean_text(config.get("voice", "부드러운 설명형"))
    voice = EDUCATION_VOICES.get(requested_voice, "nova")
    speed = float(config.get("speed", 1.0))
    if not 0.5 <= speed <= 2.0:
        record_error(state, f"슬라이드 {index + 1} 지원하지 않는 배속 {speed}: 1.0을 사용합니다.")
        speed = 1.0

    work_dir = Path(state.get("work_dir", "./output_v4"))
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_path = work_dir / f"tts_raw_slide{index + 1}.mp3"
    adjusted_path = work_dir / f"tts_slide{index + 1}_{speed:g}x.mp3"

    try:
        response = OPENAI_CLIENT.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=script,
            response_format="mp3",
        )
    except Exception as first_error:
        print(f"⚠️ 첫 TTS 요청 실패, nova로 재시도: {first_error}")
        try:
            response = OPENAI_CLIENT.audio.speech.create(
                model=TTS_MODEL,
                voice="nova",
                input=script,
                response_format="mp3",
            )
        except Exception as second_error:
            record_error(state, f"슬라이드 {index + 1} TTS 재시도 실패: {second_error}")
            return state

    try:
        raw_path.write_bytes(response.read())
    except Exception as exc:
        record_error(state, f"슬라이드 {index + 1} TTS 파일 저장 실패: {exc}")
        return state

    final_path = raw_path
    if speed != 1.0:
        if command_available(FFMPEG_CMD):
            command = [
                FFMPEG_CMD, "-y", "-i", str(raw_path),
                "-filter:a", f"atempo={speed}", str(adjusted_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0 and adjusted_path.exists():
                final_path = adjusted_path
                raw_path.unlink(missing_ok=True)
            else:
                record_error(
                    state,
                    f"슬라이드 {index + 1} 오디오 배속 실패, 원본 사용: "
                    f"{result.stderr.strip() or 'FFmpeg 오류'}",
                )
        else:
            print("⚠️ FFmpeg를 찾지 못해 원본 TTS 속도를 사용합니다.")

    try:
        duration = ffprobe_duration(str(final_path))
        print(f"   오디오 길이: {duration:.2f}초")
    except Exception as exc:
        record_error(state, f"슬라이드 {index + 1} 오디오 길이 확인 실패: {exc}")

    state["audio_path"] = str(final_path)
    print(f"✅ TTS 완료: {final_path}")
    return state


def node_make_video(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    print(f"\n--- Node 7: 슬라이드 {index + 1} 영상 생성 ---")
    state["video_path"] = ""
    slide = get_current_slide(state)
    image_path = clean_text(slide.get("slide_image", ""))
    audio_path = clean_text(state.get("audio_path", ""))

    if not image_path or not Path(image_path).exists():
        record_error(state, f"슬라이드 {index + 1} 이미지 없음: 영상을 생성할 수 없습니다.")
        add_failed_slide(state, index)
        return state
    if not audio_path or not Path(audio_path).exists():
        record_error(state, f"슬라이드 {index + 1} 오디오 없음: 영상을 생성할 수 없습니다.")
        add_failed_slide(state, index)
        return state
    if not command_available(FFMPEG_CMD):
        record_error(state, "FFmpeg 실행 파일을 찾을 수 없습니다.")
        add_failed_slide(state, index)
        return state

    try:
        duration = ffprobe_duration(audio_path)
        if duration <= 0:
            raise ValueError("오디오 길이가 0초입니다.")
    except Exception as exc:
        record_error(state, f"슬라이드 {index + 1} ffprobe 실패, 기본 5초 적용: {exc}")
        duration = 5.0

    work_dir = Path(state.get("work_dir", "./output_v4"))
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = work_dir / f"slide{index + 1}_lecture.mp4"
    command = [
        FFMPEG_CMD, "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
        "-t", str(duration),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black",
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-shortest", str(output_path),
    ]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print("⚠️ 첫 영상 렌더링 실패, 1회 재시도")
        result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        record_error(
            state,
            f"슬라이드 {index + 1} 영상 생성 실패: "
            f"{result.stderr.strip() or '출력 파일 없음'}",
        )
        add_failed_slide(state, index)
        return state

    state["video_path"] = str(output_path)
    print(f"✅ 영상 생성 완료: {output_path}")
    return state


def node_accumulate_and_step(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    total = int(state.get("total_slides", len(state.get("slides", []))))
    video_path = clean_text(state.get("video_path", ""))
    state.setdefault("video_paths", [])

    if video_path and Path(video_path).exists():
        if video_path not in state["video_paths"]:
            state["video_paths"].append(video_path)
        print(f"✅ 슬라이드 {index + 1} 영상 누적 ({len(state['video_paths'])}/{total}개)")
    else:
        add_failed_slide(state, index)
        print(f"⚠️ 슬라이드 {index + 1}은 영상 없이 종료")

    state["slide_index"] = index + 1
    print(f"   진행률: {state['slide_index']}/{total}")
    if state["slide_index"] < total:
        reset_slide_runtime(state)
    return state


def slide_router(state: AgentState) -> str:
    current = int(state.get("slide_index", 0))
    total = int(state.get("total_slides", len(state.get("slides", []))))
    route = "done" if current >= total else "next"
    print(f"🔀 Slide Router: {route}")
    return route


def slide_number_from_path(path: str) -> int:
    match = re.search(r"slide(\d+)", Path(path).name, flags=re.IGNORECASE)
    return int(match.group(1)) if match else 10**9


def node_concat(state: AgentState) -> AgentState:
    print("\n--- Node 9: 최종 영상 병합 ---")
    state["final_video"] = ""
    requested_paths = state.get("video_paths", [])
    valid_paths = [
        path for path in requested_paths
        if path and Path(path).exists() and Path(path).stat().st_size > 0
    ]
    missing_count = len(requested_paths) - len(valid_paths)
    if missing_count:
        record_error(state, f"병합 대상 영상 {missing_count}개가 없거나 비어 있습니다.")
    if not valid_paths:
        record_error(state, "병합할 유효한 슬라이드 영상이 없습니다.")
        return state
    if not command_available(FFMPEG_CMD):
        record_error(state, "FFmpeg 실행 파일을 찾을 수 없어 병합할 수 없습니다.")
        return state

    valid_paths = sorted(valid_paths, key=slide_number_from_path)
    included_slide_numbers = [slide_number_from_path(path) for path in valid_paths]
    total_slides = int(state.get("total_slides", len(state.get("slides", []))))
    print(f"   병합 대상 슬라이드: {included_slide_numbers}")
    if len(valid_paths) < total_slides:
        print(
            f"⚠️ 전체 {total_slides}장 중 {len(valid_paths)}장만 병합합니다. "
            "Final QA에서 누락 사유를 확인하세요."
        )
    work_dir = Path(state.get("work_dir", "./output_v4"))
    work_dir.mkdir(parents=True, exist_ok=True)
    final_path = work_dir / "final_lecture.mp4"

    input_arguments: List[str] = []
    filter_inputs = ""
    for media_index, path in enumerate(valid_paths):
        input_arguments.extend(["-i", path])
        filter_inputs += f"[{media_index}:v][{media_index}:a]"
    concat_filter = f"{filter_inputs}concat=n={len(valid_paths)}:v=1:a=1[outv][outa]"
    command = [
        FFMPEG_CMD, "-y", *input_arguments,
        "-filter_complex", concat_filter,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(final_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not final_path.exists() or final_path.stat().st_size == 0:
        record_error(state, f"최종 영상 병합 실패: {result.stderr.strip() or '출력 파일 없음'}")
        return state

    state["final_video"] = str(final_path)
    print(f"✅ 최종 영상 병합 완료: {final_path}")
    return state


def node_final_qa(state: AgentState) -> AgentState:
    print("\n--- Node 10: Final QA ---")
    final_video = clean_text(state.get("final_video", ""))
    final_path = Path(final_video) if final_video else None
    exists = bool(final_path and final_path.exists())
    size_bytes = final_path.stat().st_size if exists and final_path else 0
    probe = {"duration": 0.0, "has_video": False, "has_audio": False, "streams": []}

    if exists and size_bytes > 0 and final_path:
        try:
            probe = ffprobe_media(str(final_path))
        except Exception as exc:
            record_error(state, f"Final QA ffprobe 실패: {exc}")

    expected_slides = int(state.get("total_slides", len(state.get("slides", []))))
    generated_paths = [
        path for path in state.get("video_paths", [])
        if path and Path(path).exists() and Path(path).stat().st_size > 0
    ]
    generated_clips = len(generated_paths)
    included_slide_numbers = sorted({slide_number_from_path(path) for path in generated_paths})
    expected_slide_numbers = list(range(1, expected_slides + 1))
    missing_slide_numbers = [
        number for number in expected_slide_numbers if number not in included_slide_numbers
    ]
    failed_slides = sorted(set(state.get("failed_slides", [])))
    media_valid = (
        exists
        and size_bytes > 0
        and float(probe.get("duration", 0.0)) > 0
        and bool(probe.get("has_video"))
        and bool(probe.get("has_audio"))
    )
    complete = media_valid and generated_clips == expected_slides and not failed_slides

    if complete:
        final_status = "completed"
    elif media_valid:
        final_status = "partial_completed"
    else:
        final_status = "failed"

    state["final_qa"] = {
        "passed": complete,
        "exists": exists,
        "size_bytes": size_bytes,
        "duration": float(probe.get("duration", 0.0)),
        "has_video": bool(probe.get("has_video")),
        "has_audio": bool(probe.get("has_audio")),
        "expected_slides": expected_slides,
        "generated_clips": generated_clips,
        "included_slide_numbers": included_slide_numbers,
        "missing_slide_numbers": missing_slide_numbers,
        "failed_slides": failed_slides,
        "failed_slide_details": list(state.get("failed_slide_details", [])),
        "errors": list(state.get("errors", [])),
    }
    state["final_status"] = final_status
    print(f"✅ Final QA 상태: {final_status}")
    print(json.dumps(state["final_qa"], ensure_ascii=False, indent=2))
    return state
