"""
HTTP 客户端 - 工部提供基础设施

特性：
- User-Agent 随机轮换
- 请求间隔随机化（3~8秒）
- 自动重试（指数退避）
- 遇到 429/503 时延长等待
- Cookie 持久化（维持 existmag=mag）
- 统一错误日志
"""
import asyncio
import random
import time
import logging
from typing import Optional, Dict, Any
import httpx
from config import (
    REQUEST_DELAY_MIN, REQUEST_DELAY_MAX,
    MAX_RETRIES, RATE_LIMIT_BACKOFF,
    REQUEST_TIMEOUT, PROXY, JAVBUS_BASE
)

# 完整的浏览器 headers（解决 JavBus 年龄验证）
BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# 常用浏览器 User-Agent 列表
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

logger = logging.getLogger("gongbu.http")

# 默认 headers（用于首次访问）
DEFAULT_HEADERS = {
    **BROWSER_HEADERS,
    "User-Agent": USER_AGENTS[0],
}


class HttpClient:
    """
    工部标准 HTTP 客户端
    同步阻塞版（httpx sync），配合 asyncio 的 run_in_executor 使用
    """

    def __init__(self):
        self._last_request_time: float = 0
        self._session: Optional[httpx.Client] = None
        self._init_session()

    def _init_session(self):
        # httpx 0.27+ 使用 proxy (单数)，不接受字典
        proxy = PROXY if PROXY else None

        self._session = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            proxy=proxy,
            verify=False,  # javbus SSL 有时不稳定
        )
        # 设置基础 cookie
        self._session.cookies.set("existmag", "mag", domain="www.javbus.com")

        # 首次访问时通过年龄验证
        self._verify_age()

    def _verify_age(self):
        """通过 JavBus 年龄验证"""
        try:
            # 1. 先访问首页触发验证
            headers = self._get_headers()
            resp = self._session.get(JAVBUS_BASE, headers=headers)
            if not resp or "driver-verify" not in str(resp.url):
                logger.info("无需年龄验证")
                return

            # 2. POST 确认表单
            logger.info("正在通过年龄验证...")
            resp = self._session.post(
                f"{JAVBUS_BASE}/doc/driver-verify",
                data={"Submit": "確認"},
                headers=self._get_headers()
            )

            # 3. 再次访问首页确认
            resp = self._session.get(JAVBUS_BASE, headers=self._get_headers())
            if "driver-verify" not in str(resp.url):
                logger.info("✅ 年龄验证通过")
            else:
                logger.warning("⚠️ 年龄验证可能未通过")
        except Exception as e:
            logger.warning(f"年龄验证过程出错: {e}")

    def _get_headers(self, extra: Optional[Dict] = None) -> Dict[str, str]:
        """生成随机 UA + 完整浏览器头（解决年龄验证）"""
        headers = {
            **BROWSER_HEADERS,
            "User-Agent": random.choice(USER_AGENTS),
        }
        if extra:
            headers.update(extra)
        return headers

    def _wait_for_delay(self):
        """请求限速：确保两次请求之间有随机间隔"""
        now = time.time()
        elapsed = now - self._last_request_time
        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        if elapsed < delay:
            sleep_time = delay - elapsed
            logger.debug(f"限速等待 {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def get(
        self,
        url: str,
        extra_headers: Optional[Dict] = None,
        is_ajax: bool = False,
    ) -> Optional[httpx.Response]:
        """
        发起 GET 请求，含自动重试和限速

        Args:
            url: 目标 URL
            extra_headers: 额外请求头（会覆盖默认头）
            is_ajax: 是否为 AJAX 请求（调整 Accept/Referer 头）

        Returns:
            httpx.Response 或 None（失败）
        """
        headers = self._get_headers(extra_headers)

        if is_ajax:
            headers["Accept"] = "application/json, text/html, */*"
            headers["X-Requested-With"] = "XMLHttpRequest"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._wait_for_delay()
                logger.info(f"GET [{attempt}/{MAX_RETRIES}] {url}")
                resp = self._session.get(url, headers=headers)

                if resp.status_code == 200:
                    return resp

                elif resp.status_code in (429, 503):
                    wait = RATE_LIMIT_BACKOFF * attempt
                    logger.warning(f"触发限速 {resp.status_code}，等待 {wait:.0f}s 后重试")
                    time.sleep(wait)

                elif resp.status_code in (403, 404):
                    logger.warning(f"HTTP {resp.status_code}: {url}")
                    return None

                else:
                    logger.warning(f"HTTP {resp.status_code}: {url}，重试中...")
                    time.sleep(5 * attempt)

            except httpx.TimeoutException:
                logger.warning(f"请求超时 [{attempt}/{MAX_RETRIES}]: {url}")
                time.sleep(5 * attempt)

            except httpx.ConnectError as e:
                logger.warning(f"连接失败 [{attempt}/{MAX_RETRIES}]: {url} - {e}")
                time.sleep(10 * attempt)

            except Exception as e:
                logger.error(f"未知错误 [{attempt}/{MAX_RETRIES}]: {url} - {e}")
                time.sleep(5 * attempt)

        logger.error(f"请求失败，已达最大重试次数: {url}")
        return None

    def close(self):
        if self._session:
            self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# 模块级全局客户端（单例，避免重复初始化）
_global_client: Optional[HttpClient] = None


def get_client() -> HttpClient:
    """获取全局 HTTP 客户端（工部单例）"""
    global _global_client
    if _global_client is None:
        _global_client = HttpClient()
    return _global_client
