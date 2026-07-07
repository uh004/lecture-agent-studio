import streamlit as st
import requests
import time
import os

st.set_page_config(page_title="Lecture Agent Studio", page_icon="🎥", layout="wide")

st.title("🎥 Lecture Agent Studio")
st.markdown("PPTX 파일을 업로드하면 AI가 대본을 작성하고 성우가 더빙한 강의 영상을 만들어 줍니다!")

# ---------------------------------------------------
# 사이드바 설정 (페르소나)
# ---------------------------------------------------
st.sidebar.header("⚙️ 강의 페르소나 설정")

preset = st.sidebar.selectbox("프리셋 선택", ["일타 강사 스타일", "TED 강연 스타일", "IT 유튜버 스타일", "직접 설정"])

if preset == "일타 강사 스타일":
    def_tone = "에너지가 넘치고 자신감 있는 1타 강사 톤"
    def_style = "딱딱한 설명은 버리고, 쉬운 비유와 실생활 예시를 적극 활용하세요. 가끔 청중에게 질문을 던지며 주의를 환기하세요."
    def_voice = "친절한 튜토리얼"
    def_speed = 1.15
    def_sec = 70
elif preset == "TED 강연 스타일":
    def_tone = "차분하지만 확신에 찬 전문가 톤"
    def_style = "전문 용어보다는 큰 그림(Big Picture)과 인사이트를 중심으로 설명하세요. 스티브 잡스처럼 여유롭게 말하듯 구성해 주세요."
    def_voice = "명확한 설명형"
    def_speed = 1.0
    def_sec = 80
elif preset == "IT 유튜버 스타일":
    def_tone = "친한 선배가 후배에게 알려주듯 친근하고 편안한 톤"
    def_style = "'~했는데요', '~거죠' 같이 입에 착 달라붙는 구어체를 사용하세요. 화면을 함께 보며 대화하는 듯한 현장감을 넣어주세요."
    def_voice = "부드러운 설명형"
    def_speed = 1.1
    def_sec = 60
else:
    def_tone = "친절하고 명료한 톤"
    def_style = "자연스럽고 설명적인 말투"
    def_voice = "부드러운 설명형"
    def_speed = 1.0
    def_sec = 60

tone = st.sidebar.text_area("강의 톤 (Tone)", value=def_tone)
style = st.sidebar.text_area("강의 스타일 (Style)", value=def_style)

voice = st.sidebar.selectbox(
    "AI 성우 목소리",
    ["부드러운 설명형", "교수님 톤", "친절한 튜토리얼", "명확한 설명형"],
    index=["부드러운 설명형", "교수님 톤", "친절한 튜토리얼", "명확한 설명형"].index(def_voice)
)
speed = st.sidebar.slider("말하기 속도", min_value=0.8, max_value=1.5, value=def_speed, step=0.05)
target_sec = st.sidebar.slider("슬라이드당 목표 시간(초)", min_value=30, max_value=120, value=def_sec, step=10)

# FastAPI 백엔드 URL
BACKEND_URL = "http://localhost:8000/api"

# ---------------------------------------------------
# 메인 화면 (파일 업로드 및 실행)
# ---------------------------------------------------
uploaded_file = st.file_uploader("PPTX 파일을 업로드하세요", type=["pptx"])

if uploaded_file and st.button("🚀 영상 제작 시작", type="primary"):
    with st.status("🚀 강의 영상 제작을 시작합니다...", expanded=True) as status:
        
        # 1. FastAPI 서버로 업로드 및 작업 시작 요청
        st.write("서버에 파일을 업로드하고 있습니다...")
        try:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
            data = {
                "tone": tone,
                "style": style,
                "voice": voice,
                "speed": speed,
                "target_duration_sec": target_sec
            }
            response = requests.post(f"{BACKEND_URL}/generate", files=files, data=data)
            
            if response.status_code == 200:
                job_id = response.json().get("job_id")
                st.write(f"✅ 작업이 성공적으로 시작되었습니다! (Job ID: {job_id})")
            else:
                st.error(f"서버 오류: {response.text}")
                st.stop()
        except requests.exceptions.ConnectionError:
            st.error("FastAPI 백엔드 서버(http://localhost:8000)가 실행 중이지 않습니다.")
            st.stop()
            
        # UI에 보여줄 노드 한글 이름
        node_names = {
            "init": "작업 준비 중...",
            "parse_ppt": "PPT 분석 및 이미지/텍스트 추출 중...",
            "tool_search": "외부 자료 검색 및 팩트 체크 중...",
            "gen_page_content": "슬라이드 요약 노트 작성 중...",
            "gen_script": "AI 강연 대본 작성 중...",
            "tts": "AI 성우 녹음 및 배속 편집 중...",
            "make_video": "화면과 소리 병합하여 슬라이드 영상 제작 중...",
            "accumulate": "결과물 취합 및 다음 슬라이드 준비 중...",
            "concat": "최종 전체 강의 영상 렌더링 중..."
        }
        
        # 2. 상태 폴링
        st.write("백그라운드에서 영상을 생성하는 중입니다...")
        
        status_placeholder = st.empty()
        
        while True:
            time.sleep(2)  # 2초마다 상태 확인
            try:
                res = requests.get(f"{BACKEND_URL}/status/{job_id}")
                if res.status_code == 200:
                    job_info = res.json()
                    status_text = job_info["status"]
                    
                    if status_text == "error":
                        st.error(f"작업 실패: {job_info.get('error_message')}")
                        status.update(label="❌ 오류 발생", state="error", expanded=True)
                        break
                        
                    elif status_text == "completed":
                        status_placeholder.markdown("### ✅ **처리 완료!** 영상을 가져옵니다...")
                        status.update(label="🎉 영상 제작 완료!", state="complete", expanded=False)
                        st.success("강의 영상이 성공적으로 제작되었습니다!")
                        
                        # 영상 다운로드/재생
                        video_url = f"{BACKEND_URL}/video/{job_id}"
                        st.video(video_url)
                        st.markdown(f"[📥 최종 영상 다운로드]({video_url})")
                        break
                        
                    else:
                        # 진행 중
                        current_node = job_info.get("current_node", "")
                        node_desc = node_names.get(current_node, f"{current_node} 노드 실행 중...")
                        current_slide = job_info.get("current_slide", 0)
                        total_slides = job_info.get("total_slides", 1)
                        
                        if current_node == "concat":
                            status_placeholder.markdown(f"**▶️ [최종 렌더링]** {node_desc}")
                        else:
                            status_placeholder.markdown(f"**▶️ [슬라이드 {current_slide}/{total_slides}]** {node_desc}")
                            
            except Exception as e:
                st.error(f"상태 조회 중 오류 발생: {e}")
                break
