"""
HTTP 客户端 - 异步版本
"""
import asyncio
import random
import logging
from typing import Optional, Dict, Any
import httpx
from config import settings, USER_AGENTS, DEFAULT_HEADERS

logger = logging.getLogger("app.core.http")

class AsyncHttpClient:
    """
    异步 HTTP 客户端
    支持随机 UA、自动重试、限速和年龄验证
    """
    def __init__(self):
        self._last_request_time: float = 0
        self._client: Optional[httpx.AsyncClient] = None
        # 使用锁确保初始化单例时的并发安全（虽然通常在启动时初始化）
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None or self._client.is_closed:
                proxy = settings.HTTP_PROXY if settings.HTTP_PROXY else None
                self._client = httpx.AsyncClient(
                    timeout=settings.REQUEST_TIMEOUT,
                    follow_redirects=True,
                    proxy=proxy,
                    verify=False,
                    headers=DEFAULT_HEADERS
                )
                self._client.cookies.set("existmag", "mag", domain="www.javbus.com")
                await self._verify_age()
            return self._client

    async def _verify_age(self):
        """通过 JavBus 年龄验证"""
        try:
            headers = self._get_headers()
            # 1. 尝试访问首页
            resp = await self._client.get(settings.JAVBUS_BASE, headers=headers)
            if "driver-verify" not in str(resp.url):
                return

            # 2. POST 确认
            logger.info("正在通过年龄验证...")
            await self._client.post(
                f"{settings.JAVBUS_BASE}/doc/driver-verify",
                data={"Submit": "確認"},
                headers=headers
            )
            logger.info("✅ 年龄验证通过")
        except Exception as e:
            logger.warning(f"年龄验证过程出错: {e}")

    def _get_headers(self, extra: Optional[Dict] = None) -> Dict[str, str]:
        headers = {
            **DEFAULT_HEADERS,
            "User-Agent": random.choice(USER_AGENTS),
        }
        if extra:
            headers.update(extra)
        return headers

    async def _wait_for_delay(self):
        """请求限速"""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        delay = random.uniform(settings.REQUEST_DELAY_MIN, settings.REQUEST_DELAY_MAX)
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def get(
        self,
        url: str,
        extra_headers: Optional[Dict] = None,
        is_ajax: bool = False,
    ) -> Optional[httpx.Response]:
        client = await self._get_client()
        headers = self._get_headers(extra_headers)

        if is_ajax:
            headers["Accept"] = "application/json, text/html, */*"
            headers["X-Requested-With"] = "XMLHttpRequest"

        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                await self._wait_for_delay()
                logger.info(f"GET [{attempt}/{settings.MAX_RETRIES}] {url}")
                resp = await client.get(url, headers=headers)

                if resp.status_code == 200:
                    return resp
                
                if resp.status_code in (429, 503):
                    wait = settings.RATE_LIMIT_BACKOFF * attempt
                    logger.warning(f"触发限速 {resp.status_code}，等待 {wait:.0f}s 后重试")
                    await asyncio.sleep(wait)
                elif resp.status_code in (403, 404):
                    logger.warning(f"HTTP {resp.status_code}: {url}")
                    return None
                else:
                    await asyncio.sleep(2 * attempt)
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                logger.warning(f"请求异常 [{attempt}/{settings.MAX_RETRIES}]: {url} - {e}")
                await asyncio.sleep(5 * attempt)
        
        return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

# 单例
http_client = AsyncHttpClient()
