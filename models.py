from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, DateTime, Text, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from db import Base

class Actress(Base):
    __tablename__ = "actresses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), index=True, nullable=False)
    alias = Column(String(256), default="")
    source = Column(String(64), default="javbus_index")
    rank = Column(Integer, default=0)
    avatar = Column(String(512), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("name","source", name="uq_actress_name_source"),
        Index("ix_actress_name_source", "name", "source"),
        Index("ix_actress_rank", "rank"),
    )

    works = relationship("Work", back_populates="actress", cascade="all, delete-orphan")

class Work(Base):
    __tablename__ = "works"
    id = Column(Integer, primary_key=True, index=True)
    actress_id = Column(Integer, ForeignKey("actresses.id", ondelete="CASCADE"), index=True)
    code = Column(String(64), index=True)   # 番号
    title = Column(String(512), default="")
    date = Column(String(32), default="")
    site = Column(String(64), default="javbus")
    page_url = Column(String(512), default="")
    cover = Column(String(512), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("code","site", name="uq_work_code_site"),
        Index("ix_work_actress_date", "actress_id", "date"),
        Index("ix_work_code_site", "code", "site"),
    )

    actress = relationship("Actress", back_populates="works")
    magnets = relationship("Magnet", back_populates="work", cascade="all, delete-orphan")

class Magnet(Base):
    __tablename__ = "magnets"
    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, ForeignKey("works.id", ondelete="CASCADE"), index=True)
    url = Column(Text, nullable=False)
    size_mb = Column(Float, default=0.0)
    resolution = Column(String(64), default="")
    codec = Column(String(64), default="")
    subtitle = Column(Boolean, default=False)
    seeder = Column(Integer, default=0)
    leecher = Column(Integer, default=0)
    quality_score = Column(Integer, default=0)
    source = Column(String(64), default="javbus")
    title = Column(String(512), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("work_id","url", name="uq_magnet_work_url"),
        Index("ix_magnet_work_quality", "work_id", "quality_score"),
    )

    work = relationship("Work", back_populates="magnets")
