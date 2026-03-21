from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path
import tempfile
import os

# 使用系统临时目录确保可写权限
data_dir = Path(tempfile.gettempdir()) / "javspider_stack_data"
data_dir.mkdir(parents=True, exist_ok=True)

# 使用绝对路径
db_path = data_dir / "javspider.db"
DATABASE_URL = f"sqlite:///{db_path}"

# 打印数据库路径用于调试
print(f"[DB] Using database at: {db_path}")

# 优化 SQLite 性能
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # 设为 True 可查看 SQL 日志
    pool_pre_ping=True,  # 连接池健康检查
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
