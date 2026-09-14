"""Generated media storage for local development and Vercel Blob."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict
from urllib.request import urlopen


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

        return self.publish_bytes(
            source.read_bytes(),
            f"lecture-agent/jobs/{job_id}/final_lecture.mp4",
            content_type="video/mp4",
            multipart=source.stat().st_size >= 5 * 1024 * 1024,
        )

    def publish_source(self, content: bytes, job_id: str, filename: str) -> Dict[str, str]:
        """Persist the uploaded PPTX so a separate worker can download it."""
        if not content:
            raise ValueError("업로드할 PPTX 파일이 비어 있습니다.")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
        if not safe_name.lower().endswith(".pptx"):
            safe_name = f"{safe_name or 'lecture'}.pptx"
        return self.publish_bytes(
            content,
            f"lecture-agent/jobs/{job_id}/input/{safe_name}",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            multipart=len(content) >= 5 * 1024 * 1024,
        )

    def publish_bytes(
        self,
        content: bytes,
        blob_path: str,
        *,
        content_type: str,
        multipart: bool = False,
    ) -> Dict[str, str]:
        if not self.is_remote:
            raise RuntimeError("원격 파일 업로드에는 Vercel Blob 연결이 필요합니다.")
        try:
            from vercel.blob import BlobClient
        except ImportError as exc:
            raise RuntimeError(
                "Vercel Blob 사용을 위해 Python 'vercel' 패키지가 필요합니다."
            ) from exc

        client = BlobClient()
        result = client.put(
            blob_path,
            content,
            access="public",
            content_type=content_type,
            add_random_suffix=False,
            overwrite=True,
            multipart=multipart,
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

    @staticmethod
    def download(source_url: str, destination: Path) -> Path:
        """Download a public Blob object (or copy a local path) to the worker."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source_url.startswith(("http://", "https://")):
            with urlopen(source_url, timeout=120) as response:
                destination.write_bytes(response.read())
        else:
            source = Path(source_url).expanduser().resolve()
            if not source.exists():
                raise FileNotFoundError(f"원본 PPTX 파일을 찾을 수 없습니다: {source}")
            destination.write_bytes(source.read_bytes())
        if not destination.exists() or destination.stat().st_size == 0:
            raise RuntimeError("PPTX 다운로드 결과가 비어 있습니다.")
        return destination


def create_object_storage() -> ObjectStorage:
    return ObjectStorage()
