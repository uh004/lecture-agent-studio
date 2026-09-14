# Lecture Agent Frontend

PPTX 업로드부터 생성 진행 상태, 완성 영상 재생 및 다운로드까지 제공하는 Next.js App Router 프론트엔드입니다.

## 로컬 실행

프로젝트 루트에서 FastAPI를 먼저 실행합니다.

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

다른 터미널에서 프론트엔드를 실행합니다.

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm.cmd install
npm.cmd run dev
```

브라우저에서 `http://localhost:3000`을 엽니다.
