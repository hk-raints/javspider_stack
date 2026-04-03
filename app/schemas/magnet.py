from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class MagnetBase(BaseModel):
    name: str
    magnet_url: str
    size_str: Optional[str] = None
    size_mb: float = 0.0
    share_date: Optional[str] = None
    is_uc: bool = False
    is_u: bool = False
    is_4k: bool = False
    is_uncensored: bool = False
    is_c: bool = False
    priority_level: int = 99

class MagnetCreate(MagnetBase):
    work_id: int

class Magnet(MagnetBase):
    id: int
    work_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MagnetPick(BaseModel):
    id: int
    work_id: int
    magnet_id: Optional[int] = None
    name: str = ""
    magnet_url: str = ""
    size_str: str = ""
    size_mb: float = 0.0
    share_date: str = ""
    priority_level: int = 99
    pick_reason: str = ""
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
