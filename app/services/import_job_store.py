from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from app.observability.logging.logger import get_logger

logger = get_logger("import_job_store")

JobStatus = Literal["pending", "running", "succeeded", "failed"]


@dataclass
class ImportJob:
    job_id: uuid.UUID
    status: JobStatus = "pending"
    total_files: int = 0
    processed_files: int = 0
    total_chunks: int = 0
    processed_chunks: int = 0
    document_ids: list[uuid.UUID] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "job_id": str(self.job_id),
            "status": self.status,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "total_chunks": self.total_chunks,
            "processed_chunks": self.processed_chunks,
            "document_ids": [str(d) for d in self.document_ids],
            "error": self.error,
        }


class ImportJobStore:
    """导入任务状态存储。进程内 dict + lock。
    单 worker 部署足够；多 worker 需迁移到 Redis（与 preview_store 同模式）。
    """

    def __init__(self) -> None:
        self._jobs: dict[uuid.UUID, ImportJob] = {}
        self._lock = asyncio.Lock()

    async def create(self, total_files: int, total_chunks: int) -> ImportJob:
        job = ImportJob(job_id=uuid.uuid4(), total_files=total_files, total_chunks=total_chunks)
        async with self._lock:
            self._jobs[job.job_id] = job
        return job

    async def get(self, job_id: uuid.UUID) -> ImportJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: uuid.UUID, **fields) -> ImportJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for k, v in fields.items():
                if hasattr(job, k):
                    setattr(job, k, v)
            job.updated_at = time.time()
            return job

    async def remove(self, job_id: uuid.UUID) -> None:
        async with self._lock:
            self._jobs.pop(job_id, None)


import_job_store = ImportJobStore()

__all__ = ["ImportJob", "ImportJobStore", "import_job_store", "JobStatus"]
