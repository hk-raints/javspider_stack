"""
数据模型 - 户部设计并维护

核心实体：
- Actress：女优完整信息
- Work：作品详情
- Tag：作品类别标签（全局）
- WorkTag：作品-标签关联（多对多）
- WorkCast：作品-演员关联（多对多，含作品内的演员角色）
- Magnet：磁力候选（一个作品可有多个）
- MagnetPick：每个作品的最终筛选结果
- CrawlTask：爬取任务记录（用于进度追踪）
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, Float,
    DateTime, Text, UniqueConstraint, Index, Table
)
from sqlalchemy.orm import relationship
from datetime import datetime
from db.session import Base


# ─────────────────────────────────────────────
# 女优表
# ─────────────────────────────────────────────
class Actress(Base):
    __tablename__ = "actresses"

    id = Column(Integer, primary_key=True, index=True)

    # 基本标识
    name = Column(String(128), nullable=False, index=True, comment="爬取的原始名字")
    javbus_id = Column(String(32), unique=True, index=True, comment="javbus star ID，如 okq")
    profile_url = Column(String(512), default="", comment="女优详情页URL")
    avatar = Column(String(512), default="", comment="头像图片URL")

    # 个人信息（直接爬取，不翻译）
    birthday = Column(String(32), default="", comment="生日")
    age = Column(String(16), default="", comment="年龄（爬取时的值）")
    height = Column(String(16), default="", comment="身高，如 159cm")
    cup = Column(String(8), default="", comment="罩杯，如 F")
    bust = Column(String(16), default="", comment="胸围，如 84cm")
    waist = Column(String(16), default="", comment="腰围，如 58cm")
    hip = Column(String(16), default="", comment="臀围，如 88cm")
    hobby = Column(Text, default="", comment="爱好（日文原文）")

    # 爬取元数据
    profile_crawled = Column(Boolean, default=False, comment="个人信息是否已爬取")
    works_crawled = Column(Boolean, default=False, comment="作品列表是否已爬取")
    popularity_score = Column(Float, default=0.0, index=True, comment="热度分：按作品数+时间衰减计算，值越大越热门")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    works = relationship("Work", secondary="work_cast", back_populates="actresses")
    tasks = relationship("CrawlTask", back_populates="actress", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_actress_name", "name"),
        Index("ix_actress_javbus_id", "javbus_id"),
    )

    def __repr__(self):
        return f"<Actress {self.name} ({self.javbus_id})>"


# ─────────────────────────────────────────────
# 作品表
# ─────────────────────────────────────────────
class Work(Base):
    __tablename__ = "works"

    id = Column(Integer, primary_key=True, index=True)

    # 作品标识
    code = Column(String(64), unique=True, index=True, comment="识别码/番号，如 SSIS-956")
    title = Column(String(512), default="", comment="作品标题")
    work_url = Column(String(512), default="", comment="作品详情页URL")
    cover = Column(String(512), default="", comment="封面图URL")

    # 作品详情
    release_date = Column(String(32), default="", comment="发行日期")
    director = Column(String(128), default="", comment="导演")
    studio = Column(String(128), default="", comment="制作商")
    label = Column(String(128), default="", comment="发行商")
    series = Column(String(128), default="", comment="系列")

    # 爬取元数据
    detail_crawled = Column(Boolean, default=False, comment="作品详情是否已爬取")
    magnets_crawled = Column(Boolean, default=False, comment="磁力是否已爬取")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    actresses = relationship("Actress", secondary="work_cast", back_populates="works")
    tags = relationship("Tag", secondary="work_tag", back_populates="works")
    magnets = relationship("Magnet", back_populates="work", cascade="all, delete-orphan")
    picked_magnet = relationship("MagnetPick", back_populates="work", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_work_code", "code"),
        Index("ix_work_release_date", "release_date"),
    )

    def __repr__(self):
        return f"<Work {self.code}>"


# ─────────────────────────────────────────────
# 作品-演员 关联表（多对多）
# ─────────────────────────────────────────────
class WorkCast(Base):
    __tablename__ = "work_cast"

    work_id = Column(Integer, ForeignKey("works.id", ondelete="CASCADE"), primary_key=True)
    actress_id = Column(Integer, ForeignKey("actresses.id", ondelete="CASCADE"), primary_key=True)


# ─────────────────────────────────────────────
# 标签表（全局，供数据分析使用）
# ─────────────────────────────────────────────
class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False, index=True, comment="标签名（原文，如 高畫質）")
    javbus_genre_id = Column(String(32), default="", comment="javbus genre ID，如 4o")

    works = relationship("Work", secondary="work_tag", back_populates="tags")


# ─────────────────────────────────────────────
# 作品-标签 关联表（多对多）
# ─────────────────────────────────────────────
class WorkTag(Base):
    __tablename__ = "work_tag"

    work_id = Column(Integer, ForeignKey("works.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


# ─────────────────────────────────────────────
# 磁力候选表（原始数据，全量保留）
# ─────────────────────────────────────────────
class Magnet(Base):
    __tablename__ = "magnets"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, ForeignKey("works.id", ondelete="CASCADE"), index=True)

    name = Column(String(512), default="", comment="磁力名称（显示名）")
    magnet_url = Column(Text, nullable=False, comment="magnet:?xt=urn:btih:... 完整地址")
    size_str = Column(String(64), default="", comment="原始大小字符串，如 9.31GB")
    size_mb = Column(Float, default=0.0, comment="转换后的大小（MB）")
    share_date = Column(String(32), default="", comment="分享日期")

    # 类型标记（用于筛选）
    is_uc = Column(Boolean, default=False, comment="包含 -UC 标记")
    is_u = Column(Boolean, default=False, comment="包含 -U 标记（非UC）")
    is_4k = Column(Boolean, default=False, comment="包含 -4K 标记")
    is_uncensored = Column(Boolean, default=False, comment="包含 uncensored 标记")
    is_c = Column(Boolean, default=False, comment="包含 -C 标记")
    priority_level = Column(Integer, default=99, comment="优先级数字（越小越优先）：1=UC,2=U,3=4K,4=uncensored,5=C,99=普通")

    created_at = Column(DateTime, default=datetime.utcnow)

    work = relationship("Work", back_populates="magnets")

    __table_args__ = (
        UniqueConstraint("work_id", "magnet_url", name="uq_magnet_work_url"),
        Index("ix_magnet_work_priority", "work_id", "priority_level", "size_mb"),
    )


# ─────────────────────────────────────────────
# 磁力筛选结果表（每个作品保留一条最优磁力）
# ─────────────────────────────────────────────
class MagnetPick(Base):
    __tablename__ = "magnet_picks"

    id = Column(Integer, primary_key=True, index=True)
    work_id = Column(Integer, ForeignKey("works.id", ondelete="CASCADE"), unique=True, index=True)
    magnet_id = Column(Integer, ForeignKey("magnets.id", ondelete="SET NULL"), nullable=True)

    # 冗余存储，方便快速查询
    name = Column(String(512), default="")
    magnet_url = Column(Text, default="")
    size_str = Column(String(64), default="")
    size_mb = Column(Float, default=0.0)
    share_date = Column(String(32), default="")
    priority_level = Column(Integer, default=99)
    pick_reason = Column(String(128), default="", comment="筛选原因说明")

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    work = relationship("Work", back_populates="picked_magnet")
    magnet = relationship("Magnet")


# ─────────────────────────────────────────────
# 爬取任务表（尚书省调度记录）
# ─────────────────────────────────────────────
class CrawlTask(Base):
    __tablename__ = "crawl_tasks"

    id = Column(Integer, primary_key=True, index=True)
    actress_id = Column(Integer, ForeignKey("actresses.id", ondelete="CASCADE"), index=True)

    # 任务阶段：profile | works | magnets | full
    task_type = Column(String(32), default="full")
    status = Column(String(32), default="pending", comment="pending|running|completed|failed")

    # 进度
    total_works = Column(Integer, default=0)
    done_works = Column(Integer, default=0)
    total_magnets = Column(Integer, default=0)
    done_magnets = Column(Integer, default=0)

    error_msg = Column(Text, default="")
    log = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    actress = relationship("Actress", back_populates="tasks")

    __table_args__ = (
        Index("ix_crawl_task_status", "status"),
        Index("ix_crawl_task_actress", "actress_id"),
    )
