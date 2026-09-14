# Lecture Agent Studio

PPTX를 파싱하고, 슬라이드를 멀티모달로 분석한 뒤 근거 기반 강의 Script·음성·영상을 생성하는 LangGraph 프로젝트입니다.

현재 v4 엔진은 `notebooks/lecture_agent_final.ipynb`에서 검증한 흐름을 `src/` 모듈로 분리했으며, `main.py` FastAPI와 `frontend/` Next.js가 같은 엔진을 사용합니다.

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
  infrastructure/
    job_store.py       로컬 메모리·Upstash 작업 상태 저장
    object_storage.py  로컬 파일·Vercel Blob 영상 저장
  graph.py          LangGraph 조립
  service.py        Notebook/API 공용 실행 함수
  cli.py            명령행 실행기

evals/              로컬·LangSmith 평가 도구
notebooks/          설계 설명과 E2E 검증 Notebook
frontend/           Next.js 사용자 화면
main.py             FastAPI API 진입점
pyproject.toml       Vercel Python 런타임 의존성·진입점
vercel.json          Vercel Function 실행 시간·번들 설정
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

로컬에서 원본 PPT 디자인 그대로 렌더링하려면 LibreOffice와 Poppler의 `pdftoppm`이 필요합니다. 없는 환경에서는 텍스트·표·내장 이미지를 이용한 호환 렌더러로 자동 전환됩니다. FFmpeg는 시스템 설치본을 우선 사용하고, 없으면 `imageio-ffmpeg` 실행 파일을 사용합니다.

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

## Vercel 배포

Vercel에서 같은 GitHub 저장소를 두 프로젝트로 연결합니다. Vercel Services Private Beta 권한이 없어도 사용할 수 있는 구성입니다.

### 1. API 프로젝트

- 저장소: `lecture-agent-studio`
- Root Directory: 저장소 루트(비워 둠)
- Framework: FastAPI 자동 감지
- 진입점: `pyproject.toml`의 `main:app`
- Function 최대 실행 시간: `vercel.json`에서 300초

환경변수:

```dotenv
OPENAI_API_KEY=...
TAVILY_API_KEY=...
LLM_MODEL=gpt-4o-mini
TTS_MODEL=tts-1
VERCEL_MAX_SLIDES=5
FRONTEND_ORIGINS=https://프론트엔드프로젝트.vercel.app
FRONTEND_ORIGIN_REGEX=https://.*\.vercel\.app
```

API 프로젝트의 Storage/Marketplace에서 다음 두 저장소를 연결합니다.

- Upstash Redis: 작업 상태 저장. `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`이 자동 등록됩니다.
- Vercel Blob(Public): 완성 MP4 저장. `BLOB_READ_WRITE_TOKEN`이 자동 등록됩니다.

배포 후 `https://API주소.vercel.app/api/health`의 `ready`가 `true`인지 확인합니다.

### 2. 웹 프로젝트

- 같은 저장소를 다시 Import
- Root Directory: `frontend`
- Framework: Next.js
- 환경변수:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://API주소.vercel.app
```

환경변수를 저장한 뒤 배포합니다. API와 웹은 같은 Vercel 계정에서 각각 Git push 자동 배포됩니다.

Vercel Hobby의 함수 최대 실행 시간은 300초입니다. 포트폴리오 시연은 먼저 1~3장 PPT로 검증하고, 300초를 넘는 대형 강의는 슬라이드 단위 작업 분리 또는 Pro 플랜이 필요합니다.
