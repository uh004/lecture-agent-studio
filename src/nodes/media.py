import os
import re
import shutil
import subprocess

from src.core.state import State
from src.core.config import FFMPEG_CMD, TTS_MODEL, client
from src.core.utils import ffprobe_duration


def node_tts(state: dict) -> dict:
    """교육용 강의 스크립트를 TTS로 변환"""
    print("\n--- Node 5: TTS 변환 실행 ---")

    script = state.get("script", "").strip()
    prompt = state.get("prompt", {}) or {}
    work_dir = state.get("work_dir", "./")
    slide_idx = int(state.get("slide_index", 0))

    EDUCATION_VOICES = {
        "부드러운 설명형": "nova", "교수님 톤": "alloy",
        "친절한 튜토리얼": "shimmer", "명확한 설명형": "onyx",
    }
    raw_voice = prompt.get("voice", "부드러운 설명형")
    voice = EDUCATION_VOICES.get(raw_voice, "nova")
    speed = float(prompt.get("speed", 1.0))

    if not script:
        script = "현재 슬라이드에는 설명할 내용이 준비되어 있지 않습니다."

    os.makedirs(work_dir, exist_ok=True)
    raw_path = os.path.join(work_dir, f"tts_raw_slide{slide_idx}.mp3")
    final_path = os.path.join(work_dir, f"tts_slide{slide_idx}_{speed}x.mp3")

    try:
        print(f"  [TTS] 보이스('{voice}')로 음성 생성 중...")
        response = client.audio.speech.create(model=TTS_MODEL, voice=voice, input=script, response_format="mp3")
    except Exception as e:
        print(f"  [오류] TTS 생성 실패: {e}")
        print("  [재시도] 기본 보이스 'nova'로 재생성")
        response = client.audio.speech.create(model=TTS_MODEL, voice="nova", input=script, response_format="mp3")

    with open(raw_path, "wb") as f:
        f.write(response.read())

    # v3: FFMPEG_CMD 통일 변수 사용
    if speed != 1.0 and shutil.which(FFMPEG_CMD):
        print(f"  [FFmpeg] {speed}배속 변환 중...")
        cmd = [FFMPEG_CMD, "-y", "-i", raw_path, "-filter:a", f"atempo={speed}", final_path]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.path.exists(raw_path):
            os.remove(raw_path)
    else:
        final_path = raw_path

    try:
        duration = ffprobe_duration(final_path)
        print(f"  [TTS] 최종 오디오 길이: {round(duration, 2)}초")
    except:
        print("  ⚠️ 오디오 길이 계산 불가")

    state["audio"] = final_path
    print(f"  ✅ 음성 파일 저장 → {final_path}")
    return state


def node_make_video(state: dict) -> dict:
    """슬라이드 PNG + TTS 음성 → MP4 클립"""
    print("\n--- Node 6: 영상 생성(make_video) 실행 ---")

    slide_imgs = state.get("slide_image", [])
    audio_path = state.get("audio", "")
    work_dir = state.get("work_dir", "./")
    slide_index = int(state.get("slide_index", 0))

    if not slide_imgs or slide_index >= len(slide_imgs):
        print(f"  [경고] 슬라이드 이미지 없음 → index={slide_index}")
        return state
    if not os.path.exists(audio_path):
        print(f"  [경고] 오디오 파일 없음 → {audio_path}")
        return state

    image_path = slide_imgs[slide_index]
    if not os.path.exists(image_path):
        print(f"  [경고] 이미지 파일 없음 → {image_path}")
        return state

    os.makedirs(work_dir, exist_ok=True)
    out_mp4 = os.path.join(work_dir, f"slide{slide_index+1}_lecture.mp4")

    try:
        duration = ffprobe_duration(audio_path)
    except Exception as e:
        print(f"  [경고] ffprobe 실패 → 기본 5초 (오류: {e})")
        duration = 5

    ffmpeg_cmd = [
        FFMPEG_CMD, "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
        "-t", str(duration),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black",
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        out_mp4
    ]

    print(f"  [FFmpeg] 슬라이드 {slide_index+1} 렌더링 중...")
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode != 0:
        print("  [오류] 렌더링 실패 → 1회 재시도")
        retry = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if retry.returncode != 0:
            print("  [치명] 영상 생성 실패. 건너뜁니다.")
            return state

    state["video_path"] = out_mp4
    print(f"  ✅ 영상 생성 → {out_mp4}")
    return state


def node_accumulate_and_step(state: dict) -> dict:
    """영상 누적 + 다음 슬라이드 이동 (v3: 별도 노드)"""
    current_idx = state.get("slide_index", 0)
    total = state.get("total_slides", 1)
    current_video = state.get("video_path", None)

    if "video_paths" not in state or not isinstance(state["video_paths"], list):
        state["video_paths"] = []

    if current_video and os.path.exists(current_video):
        if current_video not in state["video_paths"]:
            state["video_paths"].append(current_video)
        print(f"  슬라이드 {current_idx+1} 완료 → {current_video}")
    else:
        print(f"  슬라이드 {current_idx+1} 영상 생성 실패")
        state.setdefault("failed_slides", []).append(current_idx)

    state["slide_index"] = current_idx + 1
    progress = (state["slide_index"] / total) * 100
    print(f"  진행률: {state['slide_index']}/{total} ({progress:.1f}%)")
    return state


def router_continue_or_done(state: dict) -> str:
    current = state.get("slide_index", 0)
    total = state.get("total_slides", 1)
    if current >= total:
        print("\n🎉 모든 슬라이드 처리 완료!")
        return "done"
    print(f"\n➡️ 다음 슬라이드: {current+1}/{total}")
    return "continue"


def node_concat(state: dict) -> dict:
    """모든 영상을 하나로 합침 (v3: 코덱 옵션 + duration/size 출력)"""
    video_paths = state.get("video_paths", [])
    work_dir = state.get("work_dir", "./")

    if not video_paths:
        print("❗ 합칠 영상이 없습니다.")
        return state

    print(f"총 {len(video_paths)}개 영상 병합 시작")
    video_paths = sorted(video_paths, key=lambda x: int(re.findall(r"slide(\d+)", x)[0]))
    final_video = os.path.join(work_dir, "final_lecture.mp4")

    input_cmd, filter_inputs = [], ""
    for i, path in enumerate(video_paths):
        input_cmd += ["-i", path]
        filter_inputs += f"[{i}:v][{i}:a]"
    filter_cmd = f"{filter_inputs}concat=n={len(video_paths)}:v=1:a=1[outv][outa]"

    cmd = [
        FFMPEG_CMD, "-y", *input_cmd,
        "-filter_complex", filter_cmd,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        final_video
    ]

    print("  FFmpeg 병합 중...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("[❌] 영상 병합 실패")
        print(result.stderr.decode(errors='ignore'))
        return state

    try:
        duration = ffprobe_duration(final_video)
    except:
        duration = 0.0
    size_mb = os.path.getsize(final_video) / (1024 * 1024)

    print("🎉 최종 강의 영상 생성 완료!")
    print(f"  경로: {final_video}")
    if duration > 0:
        print(f"  재생 시간: {duration:.1f}초")
    print(f"  파일 크기: {size_mb:.2f} MB")

    state["final_video"] = final_video
    return state
