"""Persistent worker that consumes lecture jobs from Upstash Redis."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Response

from src.core.config import FFMPEG_CMD, PDFTOPPM_CMD, SOFFICE_CMD
from src.core.utils import command_available
from src.infrastructure import create_job_store, create_object_storage
from src.service import process_lecture_job


class QueueProcessor:
    def __init__(self) -> None:
        self.job_store = create_job_store()
        self.object_storage = create_object_storage()
        self.poll_seconds = max(0.5, float(os.getenv("WORKER_POLL_SECONDS", "2")))
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.current_job: Optional[str] = None
        self.last_error: Optional[str] = None

    @property
    def configured(self) -> bool:
        return self.job_store.is_durable and self.object_storage.is_remote

    @property
    def binaries(self) -> Dict[str, bool]:
        return {
            "soffice": command_available(SOFFICE_CMD),
            "pdftoppm": command_available(PDFTOPPM_CMD),
            "ffmpeg": command_available(FFMPEG_CMD),
        }

    @property
    def ready(self) -> bool:
        return self.configured and all(self.binaries.values())

    def start(self) -> None:
        if self.thread is not None or not self.configured:
            return
        try:
            recovered = self.job_store.recover_inflight()
            if recovered:
                print(f"Recovered {recovered} interrupted job(s).", flush=True)
        except Exception as exc:
            self.last_error = f"recovery: {exc}"
        self.thread = threading.Thread(
            target=self._run,
            name="lecture-job-worker",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=10)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                job_id = self.job_store.dequeue()
            except Exception as exc:
                self.last_error = f"queue: {exc}"
                self.stop_event.wait(self.poll_seconds)
                continue

            if not job_id:
                self.stop_event.wait(self.poll_seconds)
                continue

            self.current_job = job_id
            self.last_error = None
            try:
                process_lecture_job(
                    job_id,
                    self.job_store,
                    self.object_storage,
                    cleanup=True,
                )
            except Exception as exc:
                self.last_error = f"job {job_id}: {exc}"
                print(f"Worker job failed ({job_id}): {exc}", flush=True)
            finally:
                try:
                    self.job_store.acknowledge(job_id)
                except Exception as exc:
                    self.last_error = f"ack {job_id}: {exc}"
                self.current_job = None


processor = QueueProcessor()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    processor.start()
    yield
    processor.stop()


app = FastAPI(title="Lecture Agent Studio Worker", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health(response: Response) -> Dict[str, Any]:
    if not processor.ready:
        response.status_code = 503
    try:
        queue_depth = processor.job_store.queue_depth() if processor.configured else None
        inflight_depth = (
            processor.job_store.inflight_depth() if processor.configured else None
        )
    except Exception as exc:
        queue_depth = None
        inflight_depth = None
        processor.last_error = f"health: {exc}"
        response.status_code = 503
    return {
        "status": "ok" if response.status_code < 400 else "needs_configuration",
        "job_store": processor.job_store.backend,
        "object_storage": processor.object_storage.backend,
        "binaries": processor.binaries,
        "queue_depth": queue_depth,
        "inflight_depth": inflight_depth,
        "current_job": processor.current_job,
        "last_error": processor.last_error,
        "ready": processor.ready,
    }
