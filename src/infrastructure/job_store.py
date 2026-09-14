"""Durable job state storage with an in-memory local fallback."""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional
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
        self.queue_key = os.getenv("JOB_QUEUE_KEY", "lecture-agent:jobs:pending").strip()
        self.processing_queue_key = f"{self.queue_key}:processing"
        self._memory: Dict[str, JobData] = {}
        self._queue: Deque[str] = deque()
        self._processing_queue: Deque[str] = deque()
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

    def enqueue(self, job_id: str) -> None:
        """Add a job to the durable worker queue."""
        if self.is_durable:
            self._redis_command("LPUSH", self.queue_key, job_id)
            return
        with self._lock:
            self._queue.append(job_id)

    def dequeue(self) -> Optional[str]:
        """Claim the oldest job and keep it recoverable until acknowledged."""
        if self.is_durable:
            value = self._redis_command(
                "RPOPLPUSH", self.queue_key, self.processing_queue_key
            )
            return str(value) if value is not None else None
        with self._lock:
            if not self._queue:
                return None
            value = self._queue.popleft()
            self._processing_queue.append(value)
            return value

    def acknowledge(self, job_id: str) -> None:
        if self.is_durable:
            self._redis_command("LREM", self.processing_queue_key, 1, job_id)
            return
        with self._lock:
            try:
                self._processing_queue.remove(job_id)
            except ValueError:
                pass

    def recover_inflight(self) -> int:
        """Return jobs left by an interrupted single worker to the pending queue."""
        recovered = 0
        if self.is_durable:
            while True:
                value = self._redis_command(
                    "RPOPLPUSH", self.processing_queue_key, self.queue_key
                )
                if value is None:
                    return recovered
                recovered += 1
        with self._lock:
            while self._processing_queue:
                self._queue.appendleft(self._processing_queue.pop())
                recovered += 1
        return recovered

    def queue_depth(self) -> int:
        if self.is_durable:
            return int(self._redis_command("LLEN", self.queue_key) or 0)
        with self._lock:
            return len(self._queue)

    def inflight_depth(self) -> int:
        if self.is_durable:
            return int(self._redis_command("LLEN", self.processing_queue_key) or 0)
        with self._lock:
            return len(self._processing_queue)

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
