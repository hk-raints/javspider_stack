"""
全局配置 - 工部负责维护
"""
import os
from pathlib import Path

# ===== 路径 =====
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "javbus.db"
DB_URL = f"sqlite:///{DB_PATH}"

# ===== JavBus 站点 =====
JAVBUS_BASE = "https://www.javbus.com"
JAVBUS_ACTRESSES_URL = f"{JAVBUS_BASE}/actresses"

# ===== 爬虫安全配置（工部 - 稳定优先）=====
# 请求间隔：随机 3~8 秒
REQUEST_DELAY_MIN = 3.0
REQUEST_DELAY_MAX = 8.0

# 最大重试次数
MAX_RETRIES = 5

# 遇到 429/503 时额外等待（秒）
RATE_LIMIT_BACKOFF = 60.0

# 请求超时
REQUEST_TIMEOUT = 30

# ===== User-Agent 池（工部维护）=====
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
    # existmag=mag 让 javbus 返回磁力链接版本
    "Cookie": "existmag=mag",
    "Referer": "https://www.javbus.com/",
}

# ===== 代理配置（默认不使用）=====
PROXY = os.environ.get("HTTP_PROXY", "")  # 如需代理，设置环境变量 HTTP_PROXY

# ===== 磁力筛选规则（户部维护）=====
# 优先级顺序（越靠前优先级越高）
MAGNET_PRIORITY = ["-UC", "-U", "-4K", "uncensored", "-C"]

# 大小差异阈值（10%以内视为相同）
MAGNET_SIZE_DIFF_THRESHOLD = 0.10

# ===== 前端配置 =====
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8088
