"""Durable job state storage with an in-memory local fallback."""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


JobData = Dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Store job state in Upstash Redis or process memory during local development."""

    def __init__(self) -> None:
        self.redis_url = (
            os.getenv("UPSTASH_REDIS_REST_URL")
            or os.getenv("KV_REST_API_URL")
            # Vercel's Upstash integration adds the selected custom prefix
            # to its legacy KV-compatible variable names.
            or os.getenv("UPSTASH_REDIS_REST_KV_REST_API_URL")
            or ""
        ).rstrip("/")
        self.redis_token = (
            os.getenv("UPSTASH_REDIS_REST_TOKEN")
            or os.getenv("KV_REST_API_TOKEN")
            or os.getenv("UPSTASH_REDIS_REST_KV_REST_API_TOKEN")
            or ""
        )
        self.ttl_seconds = max(3600, int(os.getenv("JOB_TTL_SECONDS", "604800")))
        self._memory: Dict[str, JobData] = {}
        self._lock = threading.RLock()

    @property
    def backend(self) -> str:
        return "upstash" if self.is_durable else "memory"

    @property
    def is_durable(self) -> bool:
        return bool(self.redis_url and self.redis_token)

    def _key(self, job_id: str) -> str:
        return f"lecture-agent:job:{job_id}"

    def _redis_command(self, *parts: Any) -> Any:
        payload = json.dumps(list(parts), ensure_ascii=False).encode("utf-8")
        request = Request(
            self.redis_url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.redis_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Upstash 작업 상태 저장소 요청 실패: {exc}") from exc
        if "error" in body:
            raise RuntimeError(f"Upstash 작업 상태 저장소 오류: {body['error']}")
        return body.get("result")

    def create(self, job_id: str, value: JobData) -> JobData:
        job = deepcopy(value)
        now = _utc_now()
        job.setdefault("created_at", now)
        job["updated_at"] = now
        self._write(job_id, job)
        return deepcopy(job)

    def get(self, job_id: str) -> Optional[JobData]:
        if self.is_durable:
            raw = self._redis_command("GET", self._key(job_id))
            if raw is None:
                return None
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
        with self._lock:
            value = self._memory.get(job_id)
            return deepcopy(value) if value is not None else None

    def update(self, job_id: str, **changes: Any) -> JobData:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        job.update(changes)
        job["updated_at"] = _utc_now()
        self._write(job_id, job)
        return deepcopy(job)

    def _write(self, job_id: str, value: JobData) -> None:
        if self.is_durable:
            serialized = json.dumps(value, ensure_ascii=False, default=str)
            self._redis_command(
                "SET", self._key(job_id), serialized, "EX", self.ttl_seconds
            )
            return
        with self._lock:
            self._memory[job_id] = deepcopy(value)


def create_job_store() -> JobStore:
    return JobStore()
