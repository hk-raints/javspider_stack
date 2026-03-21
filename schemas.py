from pydantic import BaseModel
from typing import Optional, List

class ActressOut(BaseModel):
    id: int
    name: str
    rank: int = 0
    avatar: str = ""
    class Config:
        from_attributes = True

class WorkOut(BaseModel):
    id: int
    code: str
    title: str
    date: str = ""
    cover: str = ""
    class Config:
        from_attributes = True

class MagnetOut(BaseModel):
    id: int
    url: str
    size_mb: float = 0
    resolution: str = ""
    codec: str = ""
    subtitle: bool = False
    seeder: int = 0
    quality_score: int = 0
    title: str = ""
    class Config:
        from_attributes = True
