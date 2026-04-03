"""
全局配置 - 使用 Pydantic Settings 管理环境变量
"""
from pathlib import Path
from typing import List, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict

# ===== 路径 =====
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server Config
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = DATA_DIR
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8088
    API_KEY: str = ""  # 如果为空则不启用鉴权

    # Database Config
    # 默认使用 aiosqlite 支持异步
    DB_URL: str = f"sqlite+aiosqlite:///{DATA_DIR}/javbus.db"

    # JavBus Config
    JAVBUS_BASE: str = "https://www.javbus.com"
    
    @property
    def JAVBUS_ACTRESSES_URL(self) -> str:
        return f"{self.JAVBUS_BASE}/actresses"

    # Scraper Security Config
    REQUEST_DELAY_MIN: float = 3.0
    REQUEST_DELAY_MAX: float = 8.0
    MAX_RETRIES: int = 5
    RATE_LIMIT_BACKOFF: float = 60.0
    REQUEST_TIMEOUT: int = 30

    # Proxy Config
    HTTP_PROXY: str = ""

    # Magnet Rules
    MAGNET_PRIORITY: List[str] = ["-UC", "-U", "-4K", "uncensored", "-C"]
    MAGNET_SIZE_DIFF_THRESHOLD: float = 0.10

settings = Settings()

# ===== 导出常用变量以便旧代码使用 =====
JAVBUS_BASE = settings.JAVBUS_BASE
JAVBUS_ACTRESSES_URL = settings.JAVBUS_ACTRESSES_URL
DB_URL = settings.DB_URL
BASE_DIR = settings.BASE_DIR
DATA_DIR = settings.DATA_DIR
REQUEST_DELAY_MIN = settings.REQUEST_DELAY_MIN
REQUEST_DELAY_MAX = settings.REQUEST_DELAY_MAX
MAX_RETRIES = settings.MAX_RETRIES
RATE_LIMIT_BACKOFF = settings.RATE_LIMIT_BACKOFF
REQUEST_TIMEOUT = settings.REQUEST_TIMEOUT
HTTP_PROXY = settings.HTTP_PROXY
MAGNET_PRIORITY = settings.MAGNET_PRIORITY
MAGNET_SIZE_DIFF_THRESHOLD = settings.MAGNET_SIZE_DIFF_THRESHOLD
SERVER_HOST = settings.SERVER_HOST
SERVER_PORT = settings.SERVER_PORT

# ===== User-Agent 池 =====
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.58 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
]

# ===== 默认请求头 =====
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,zh-TW;q=0.8,zh-CN;q=0.7,zh;q=0.6,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
    "Cookie": "existmag=mag",
    "Referer": "https://www.javbus.com/",
}
