from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class WorkBase(BaseModel):
    code: str
    title: str
    work_url: Optional[str] = None
    cover: Optional[str] = None
    release_date: Optional[str] = None
    director: Optional[str] = None
    studio: Optional[str] = None
    label: Optional[str] = None
    series: Optional[str] = None

class WorkCreate(WorkBase):
    pass

class WorkUpdate(BaseModel):
    title: Optional[str] = None
    cover: Optional[str] = None
    detail_crawled: Optional[bool] = None
    magnets_crawled: Optional[bool] = None

class Work(WorkBase):
    id: int
    detail_crawled: bool
    magnets_crawled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
