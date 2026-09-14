"""Start the worker health service and queue consumer."""

from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "worker.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
        workers=1,
    )
