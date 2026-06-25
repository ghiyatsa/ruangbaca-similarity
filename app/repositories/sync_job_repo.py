"""
In-memory job tracker untuk bulk sync jobs.
FastAPI ini tidak lagi menyimpan database SQLite, membuatnya stateless dan cloud-ready.
"""
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel

class JobState(BaseModel):
    id: str
    status: str
    total_received: int
    total_processed: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

# Global in-memory storage for jobs
_jobs: Dict[str, JobState] = {}

class SyncJobRepository:
    """Mock repository yang beroperasi in-memory untuk tracking status bulk job."""
    
    @staticmethod
    async def create(*, job_id: str, payload_json: str, total_received: int) -> JobState:
        # payload_json disimpan in-memory (di-attach atau diabaikan jika tidak diperlukan lagi)
        job = JobState(
            id=job_id,
            status="pending",
            total_received=total_received,
            total_processed=0,
            created_at=datetime.utcnow()
        )
        _jobs[job_id] = job
        # Kita simpan payload di storage lokal global jika task perlu deserialisasi
        job.__dict__["_payload_json"] = payload_json
        return job

    @staticmethod
    async def find_by_id(job_id: str) -> Optional[JobState]:
        return _jobs.get(job_id)

    @staticmethod
    async def list_unfinished() -> List[JobState]:
        return [job for job in _jobs.values() if job.status in ("pending", "processing")]

    @staticmethod
    async def mark_processing(job: JobState) -> None:
        job.status = "processing"
        job.total_processed = 0
        job.error_message = None
        job.started_at = datetime.utcnow()
        job.completed_at = None

    @staticmethod
    async def update_progress(job: JobState, total_processed: int) -> None:
        job.total_processed = total_processed

    @staticmethod
    async def mark_completed(job: JobState) -> None:
        job.status = "completed"
        job.total_processed = job.total_received
        job.error_message = None
        job.completed_at = datetime.utcnow()

    @staticmethod
    async def mark_failed(job: JobState, error_message: str) -> None:
        job.status = "failed"
        job.error_message = error_message[:2000]
        job.completed_at = datetime.utcnow()
