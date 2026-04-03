from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class CrawlTaskBase(BaseModel):
    actress_id: int
    task_type: str = "full"
    status: str = "pending"
    total_works: int = 0
    done_works: int = 0
    total_magnets: int = 0
    done_magnets: int = 0
    error_msg: Optional[str] = None

class CrawlTaskCreate(CrawlTaskBase):
    pass

class CrawlTaskUpdate(BaseModel):
    status: Optional[str] = None
    total_works: Optional[int] = None
    done_works: Optional[int] = None
    total_magnets: Optional[int] = None
    done_magnets: Optional[int] = None
    error_msg: Optional[str] = None
    finished_at: Optional[datetime] = None

class CrawlTask(CrawlTaskBase):
    id: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
