"""Generated media storage for local development and Vercel Blob."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


class ObjectStorage:
    """Upload generated videos to Vercel Blob when a store is connected."""

    def __init__(self) -> None:
        self.token = os.getenv("BLOB_READ_WRITE_TOKEN", "").strip()

    @property
    def backend(self) -> str:
        return "vercel_blob" if self.is_remote else "local"

    @property
    def is_remote(self) -> bool:
        return bool(self.token)

    @staticmethod
    def _value(result: Any, *names: str) -> str:
        for name in names:
            if isinstance(result, dict) and result.get(name):
                return str(result[name])
            value = getattr(result, name, None)
            if value:
                return str(value)
        return ""

    def publish_video(self, source: Path, job_id: str) -> Dict[str, str]:
        if not source.exists() or source.stat().st_size == 0:
            raise FileNotFoundError(f"업로드할 영상 파일이 없습니다: {source}")
        if not self.is_remote:
            return {
                "url": str(source.resolve()),
                "download_url": str(source.resolve()),
                "storage": "local",
            }

        try:
            from vercel.blob import BlobClient
        except ImportError as exc:
            raise RuntimeError(
                "Vercel Blob 사용을 위해 Python 'vercel' 패키지가 필요합니다."
            ) from exc

        client = BlobClient()
        result = client.put(
            f"lecture-agent/jobs/{job_id}/final_lecture.mp4",
            source.read_bytes(),
            access="public",
            content_type="video/mp4",
            add_random_suffix=False,
            overwrite=True,
            multipart=source.stat().st_size >= 5 * 1024 * 1024,
            token=self.token,
        )
        url = self._value(result, "url")
        download_url = self._value(result, "download_url", "downloadUrl") or url
        if not url:
            raise RuntimeError("Vercel Blob이 영상 URL을 반환하지 않았습니다.")
        return {
            "url": url,
            "download_url": download_url,
            "storage": "vercel_blob",
        }


def create_object_storage() -> ObjectStorage:
    return ObjectStorage()
