from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class ActressBase(BaseModel):
    name: str
    javbus_id: Optional[str] = None
    profile_url: Optional[str] = None
    avatar: Optional[str] = None
    birthday: Optional[str] = None
    age: Optional[str] = None
    height: Optional[str] = None
    cup: Optional[str] = None
    bust: Optional[str] = None
    waist: Optional[str] = None
    hip: Optional[str] = None
    hobby: Optional[str] = None
    popularity_score: float = 0.0

class ActressCreate(ActressBase):
    pass

class ActressUpdate(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    popularity_score: Optional[float] = None
    profile_crawled: Optional[bool] = None
    works_crawled: Optional[bool] = None

class Actress(ActressBase):
    id: int
    profile_crawled: bool
    works_crawled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
