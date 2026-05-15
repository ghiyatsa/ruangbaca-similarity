from datetime import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_job import SyncJob


class SyncJobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, *, job_id: str, payload_json: str, total_received: int) -> SyncJob:
        job = SyncJob(
            id=job_id,
            status="pending",
            payload_json=payload_json,
            total_received=total_received,
            total_processed=0,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def find_by_id(self, job_id: str) -> SyncJob | None:
        result = await self.db.execute(select(SyncJob).where(SyncJob.id == job_id))
        return result.scalar_one_or_none()

    async def list_unfinished(self) -> List[SyncJob]:
        result = await self.db.execute(
            select(SyncJob).where(SyncJob.status.in_(["pending", "processing"]))
        )
        return list(result.scalars().all())

    async def mark_processing(self, job: SyncJob) -> None:
        job.status = "processing"
        job.total_processed = 0
        job.error_message = None
        job.started_at = datetime.utcnow()
        job.completed_at = None

    async def update_progress(self, job: SyncJob, total_processed: int) -> None:
        job.total_processed = total_processed

    async def mark_completed(self, job: SyncJob) -> None:
        job.status = "completed"
        job.total_processed = job.total_received
        job.error_message = None
        job.completed_at = datetime.utcnow()

    async def mark_failed(self, job: SyncJob, error_message: str) -> None:
        job.status = "failed"
        job.error_message = error_message[:2000]
        job.completed_at = datetime.utcnow()
