# Lecture Agent Studio

PPTX를 분석해 슬라이드별 강의 스크립트, 음성, 영상을 만들고 하나의 MP4로 합치는 LangGraph 기반 프로젝트입니다.

## 처리 흐름

```text
PPT 파싱 → 슬라이드 분석 → 선택적 웹 검색 → 스크립트 생성/검증
         → TTS → 슬라이드 영상 생성 → 전체 영상 병합 → 최종 QA
```

`src/graph.py`의 기존 Agent 노드와 프롬프트는 로컬 실행과 배포 환경에서 동일하게 사용합니다.

## 배포 구조

Vercel Function 안에서 전체 영상을 만들지 않습니다. PPT 렌더링과 영상 생성은 5분을 넘길 수 있고, Vercel 런타임에는 LibreOffice와 Poppler가 없기 때문입니다.

```text
Next.js Web (Vercel)
        │ 업로드/상태 조회
        ▼
FastAPI Control API (Vercel)
        ├─ 원본 PPTX → Vercel Blob
        └─ 작업 ID   → Upstash Redis Queue
                         │
                         ▼
Docker Worker (Render/Railway 등)
  LibreOffice + Poppler + FFmpeg + Noto/Nanum fonts
        ├─ 기존 LangGraph 실행
        ├─ 진행 상태 → Upstash Redis
        └─ 최종 MP4  → Vercel Blob
```

프런트엔드는 기존처럼 `/api/status/{job_id}`를 폴링하므로 별도 변경 없이 Worker 진행률을 표시합니다.

## 로컬 실행

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

프런트엔드:

```powershell
cd frontend
npm install
npm run dev
```

`.env` 기본값:

```dotenv
OPENAI_API_KEY=...
TAVILY_API_KEY=...
LLM_MODEL=gpt-4o-mini
TTS_MODEL=tts-1
FRONTEND_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

로컬 API는 기존처럼 백그라운드 작업으로 실행합니다. 원본 디자인 그대로 PPT를 렌더링하려면 로컬에도 LibreOffice와 Poppler가 필요합니다.

## Vercel API 설정

API 프로젝트는 저장소 루트를 Root Directory로 사용합니다. 다음 저장소 연결이 필요합니다.

- Upstash Redis: 작업 상태와 대기열
- Public Vercel Blob: 원본 PPTX와 최종 MP4

필수 환경 변수:

```dotenv
OPENAI_API_KEY=...
TAVILY_API_KEY=...
LLM_MODEL=gpt-4o-mini
TTS_MODEL=tts-1
BLOB_READ_WRITE_TOKEN=...
FRONTEND_ORIGINS=https://lecture-agent-web.vercel.app
MAX_SLIDES=100
JOB_TTL_SECONDS=604800
JOB_QUEUE_KEY=lecture-agent:jobs:pending
WORKER_URL=https://YOUR-WORKER-SERVICE.example.com
```

Upstash 연결이 만드는 변수명은 연결 방식에 따라 다음 둘 중 하나입니다.

```dotenv
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
```

또는 현재 프로젝트처럼 custom prefix가 붙은 경우:

```dotenv
UPSTASH_REDIS_REST_KV_REST_API_URL=...
UPSTASH_REDIS_REST_KV_REST_API_TOKEN=...
```

환경 변수를 저장한 뒤 API를 Redeploy하고 `/api/health`에서 아래 항목을 확인합니다.

```json
{
  "status": "ok",
  "job_store": "upstash",
  "object_storage": "vercel_blob",
  "execution": "redis_queue",
  "ready": true
}
```

## Docker Worker 배포

Render 또는 Railway에서 이 저장소를 새 서비스로 연결합니다.

- Dockerfile Path: `worker/Dockerfile`
- Docker build context: 저장소 루트 `.`
- Health Check Path: `/health`
- 인스턴스 수: `1`부터 시작

Worker에는 API 프로젝트와 동일한 아래 환경 변수를 복사합니다.

```dotenv
OPENAI_API_KEY=...
TAVILY_API_KEY=...
LLM_MODEL=gpt-4o-mini
TTS_MODEL=tts-1
BLOB_READ_WRITE_TOKEN=...
UPSTASH_REDIS_REST_KV_REST_API_URL=...
UPSTASH_REDIS_REST_KV_REST_API_TOKEN=...
JOB_TTL_SECONDS=604800
JOB_QUEUE_KEY=lecture-agent:jobs:pending
WORKER_POLL_SECONDS=2
WORKER_WORK_ROOT=/tmp/lecture-agent-worker
```

`WORKER_URL`은 Vercel API에만 넣습니다. Render 무료 Web Service처럼 유휴 시 잠드는 환경을 새 업로드가 깨우는 데 사용하며, Worker 자체에는 필요하지 않습니다. 작업 전달의 기준은 HTTP 요청이 아니라 Redis 큐이므로 깨우기 요청이 잠시 실패해도 작업은 유실되지 않습니다.

표준 Upstash 변수명이 발급된 경우 custom-prefix 변수 대신 표준 변수 두 개를 사용합니다. `LANGSMITH_*`를 사용하는 경우 Worker에도 같은 값을 넣습니다.

Docker 이미지에는 다음 항목이 설치됩니다.

- LibreOffice Impress: PPTX → PDF
- Poppler `pdftoppm`: PDF → 슬라이드 PNG
- FFmpeg/ffprobe: 음성 배속, 슬라이드 영상, 최종 병합
- Noto CJK/Nanum 폰트: 한글 렌더링

Worker 배포 후 `/health`에서 `ready: true`와 `soffice`, `pdftoppm`, `ffmpeg`가 모두 `true`인지 확인합니다. 그다음 새 PPT 작업을 생성하면 됩니다. 과거에 87%에서 멈춘 작업은 다시 시작되지 않으므로 새 강의를 생성해야 합니다.

> 현재 Blob Store가 Public이므로 업로드한 PPTX와 결과 MP4는 URL을 아는 사람이 접근할 수 있습니다. 민감한 강의 자료에는 Private Blob 또는 별도 인증 다운로드 구성을 사용하세요.

## 프런트엔드 배포

- Root Directory: `frontend`
- Framework Preset: Next.js
- Output Directory: override를 끄고 Next.js default 사용
- 환경 변수:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://lecture-agent-api.vercel.app
```

## 검증

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m unittest discover -s evals\tests -v
cd frontend
npm run lint
npm run build
```

Worker 이미지는 저장소 루트에서 확인합니다.

```powershell
docker build -f worker/Dockerfile -t lecture-agent-worker .
docker run --rm -p 10000:10000 --env-file .env lecture-agent-worker
```
