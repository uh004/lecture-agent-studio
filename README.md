# Lecture Agent Studio

PPTX를 파싱하고, 슬라이드를 멀티모달로 분석한 뒤 근거 기반 강의 Script·음성·영상을 생성하는 LangGraph 프로젝트입니다.

현재 v4 엔진은 `notebooks/lecture_agent_final.ipynb`에서 검증한 흐름을 `src/` 모듈로 분리한 상태입니다. 기존 `main.py`와 `app.py`는 v3 FastAPI·Streamlit 코드이므로, 다음 단계에서 v4 서비스 계층에 맞춰 교체할 예정입니다.

## v4 처리 흐름

```text
PPT 파싱
  → 멀티모달 슬라이드 분석
  → 조건부 Web Search
  → Script Draft 생성
  → Script Validation
      ├─ PASS: Script 승인 → TTS → 슬라이드 영상
      ├─ FAIL: 제한 횟수 내 Script 재생성
      └─ 한도 초과: 실패 기록 후 다음 슬라이드
  → 슬라이드 영상 병합
  → Final QA
```

발표자 노트와 링크는 파싱 결과에는 보존하지만 멀티모달 분석·Script 생성·Validation의 근거로 사용하지 않습니다.

## 디렉터리

```text
src/
  core/
    config.py       환경변수, 모델, 실행 도구 설정
    prompts.py      분석·검색·Script·Validation 프롬프트
    runtime.py      실행별 폴더와 초기 State 생성
    schemas.py      Pydantic Structured Output Schema
    state.py        AgentState
    utils.py        공통 텍스트·상태·미디어 유틸리티
  nodes/
    parser.py       PPT 파싱
    analyze.py      멀티모달 분석 및 검색 계획
    search.py       Tavily 검색과 Evidence 선별
    script.py       Script Draft 생성
    validation.py   Script 검증·승인·실패 처리
    media.py        TTS·영상·병합·Final QA
  graph.py          LangGraph 조립
  service.py        Notebook/API 공용 실행 함수
  cli.py            명령행 실행기

evals/              로컬·LangSmith 평가 도구
notebooks/          설계 설명과 E2E 검증 Notebook
```

## 환경 설정

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`.env`에 필요한 값을 설정합니다.

```dotenv
OPENAI_API_KEY=...
TAVILY_API_KEY=...
LLM_MODEL=gpt-4o-mini
TTS_MODEL=tts-1
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=lecture-agent-studio
```

PPT 렌더링과 영상 생성에는 LibreOffice, Poppler의 `pdftoppm`, FFmpeg·FFprobe가 필요합니다. 자동 탐색되지 않으면 `.env`에 `SOFFICE_CMD`, `PDFTOPPM_CMD`, `FFMPEG_CMD`, `FFPROBE_CMD` 경로를 지정합니다.

## 실행

Notebook에서는 `notebooks/lecture_agent_final.ipynb`의 Cell 19에서 `src.graph`를 불러오고, Cell 21에서 E2E를 실행합니다.

모듈만으로 실행하려면 프로젝트 루트에서 다음 명령을 사용합니다.

```powershell
.\venv\Scripts\python.exe -m src.cli --pptx .\data\sample.pptx
```

결과는 기본적으로 `notebooks/runs/{PPT이름}_{날짜시간}/`에 저장되며 `eval_predictions.jsonl`도 함께 생성됩니다.

## 검증

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m unittest discover -s evals\tests -v
```

최신 실행 결과를 평가하려면:

```powershell
$run = Get-ChildItem .\notebooks\runs -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

$predictions = Join-Path $run.FullName "eval_predictions.jsonl"

.\venv\Scripts\python.exe -m evals.run_code_evals `
  --dataset .\evals\datasets\lecture_agent_v1.jsonl `
  --predictions $predictions
```

LangSmith 평가:

```powershell
.\venv\Scripts\python.exe -m evals.run_langsmith_evals `
  --dataset-name lecture-agent-v1 `
  --predictions $predictions `
  --experiment-prefix lecture-agent-v4-modular `
  --with-llm-judge `
  --judge-model gpt-4o-mini
```
