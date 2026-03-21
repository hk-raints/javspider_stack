"""
防屏蔽机制
借鉴自 jav-scrapy 的防屏蔽实现
"""
import random
import json
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """代理配置"""
    proxy: str  # 代理地址,格式: http://user:pass@host:port
    protocol: str = "http"  # http, https, socks4, socks5
    username: Optional[str] = None
    password: Optional[str] = None
    success_count: int = 0
    fail_count: int = 0
    last_used: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.success_count + self.fail_count
        if total == 0:
            return 1.0
        return self.success_count / total
    
    def mark_success(self):
        """标记成功"""
        self.success_count += 1
        self.last_used = datetime.now()
    
    def mark_fail(self):
        """标记失败"""
        self.fail_count += 1
        self.last_used = datetime.now()


class UserAgentRotator:
    """User-Agent轮换器"""
    
    # 常用User-Agent列表 (来自jav-scrapy)
    DEFAULT_USER_AGENTS = [
        # Chrome
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        # Firefox
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
        # Safari
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
        # Edge
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    ]
    
    def __init__(self, user_agents: Optional[List[str]] = None):
        self.user_agents = user_agents or self.DEFAULT_USER_AGENTS.copy()
        self.current_index = 0
        self.rotation_enabled = True
    
    def get_random(self) -> str:
        """获取随机User-Agent"""
        if not self.rotation_enabled:
            return self.user_agents[0]
        return random.choice(self.user_agents)
    
    def get_next(self) -> str:
        """获取下一个User-Agent"""
        if not self.rotation_enabled:
            return self.user_agents[0]
        
        ua = self.user_agents[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.user_agents)
        return ua
    
    def get_current(self) -> str:
        """获取当前User-Agent"""
        return self.user_agents[self.current_index]
    
    def enable_rotation(self):
        """启用轮换"""
        self.rotation_enabled = True
    
    def disable_rotation(self):
        """禁用轮换"""
        self.rotation_enabled = False


class ProxyRotator:
    """代理轮换器"""
    
    def __init__(self, proxies: Optional[List[str]] = None):
        self.proxies: List[ProxyConfig] = []
        
        if proxies:
            for proxy in proxies:
                self.add_proxy(proxy)
    
    def add_proxy(self, proxy: str) -> ProxyConfig:
        """添加代理"""
        config = self._parse_proxy(proxy)
        self.proxies.append(config)
        return config
    
    def _parse_proxy(self, proxy: str) -> ProxyConfig:
        """解析代理字符串"""
        # 支持格式:
        # http://user:pass@host:port
        # socks5://user:pass@host:port
        # http://host:port
        # host:port
        
        # 检测协议
        protocol = "http"
        if "://" in proxy:
            protocol_part, rest = proxy.split("://", 1)
            if protocol_part in ["http", "https", "socks4", "socks5"]:
                protocol = protocol_part
            proxy = rest
        
        # 解析认证信息
        username = None
        password = None
        if "@" in proxy:
            auth_part, rest = proxy.rsplit("@", 1)
            if ":" in auth_part:
                username, password = auth_part.split(":", 1)
            proxy = rest
        
        return ProxyConfig(
            proxy=f"{protocol}://{proxy}",
            protocol=protocol,
            username=username,
            password=password
        )
    
    def get_proxy(self, min_success_rate: float = 0.5) -> Optional[str]:
        """获取代理 (优先使用成功率高的)"""
        if not self.proxies:
            return None
        
        # 过滤可用代理
        available = [
            p for p in self.proxies
            if p.success_rate >= min_success_rate
        ]
        
        if not available:
            # 所有代理都不够好,随机选择
            available = self.proxies.copy()
        
        # 按成功率加权随机选择
        weights = [p.success_rate for p in available]
        proxy = random.choices(available, weights=weights, k=1)[0]
        
        logger.debug(f"Selected proxy: {proxy.proxy} (success rate: {proxy.success_rate:.2%})")
        return proxy.proxy
    
    def mark_success(self, proxy: str):
        """标记代理成功"""
        for p in self.proxies:
            if p.proxy == proxy:
                p.mark_success()
                logger.debug(f"Proxy {proxy} marked as success")
                break
    
    def mark_fail(self, proxy: str):
        """标记代理失败"""
        for p in self.proxies:
            if p.proxy == proxy:
                p.mark_fail()
                logger.debug(f"Proxy {proxy} marked as failed")
                break
    
    def get_stats(self) -> List[Dict]:
        """获取代理统计"""
        return [
            {
                "proxy": p.proxy,
                "protocol": p.protocol,
                "success_rate": p.success_rate,
                "success_count": p.success_count,
                "fail_count": p.fail_count,
                "last_used": p.last_used.isoformat() if p.last_used else None
            }
            for p in self.proxies
        ]


class URLRotator:
    """URL轮换器"""
    
    def __init__(self, base_urls: Optional[List[str]] = None, cache_file: Optional[Path] = None):
        self.base_urls: List[str] = []
        self.current_index = 0
        self.cache_file = cache_file or Path.home() / ".jav-spider-urls.json"
        self.enabled = True
        
        if base_urls:
            self.base_urls = base_urls.copy()
        
        self._load_cache()
    
    def _load_cache(self):
        """加载缓存的URL"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.base_urls = data.get('urls', [])
                    logger.info(f"Loaded {len(self.base_urls)} URLs from cache")
            except Exception as e:
                logger.warning(f"Failed to load URL cache: {e}")
    
    def _save_cache(self):
        """保存URL到缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'urls': self.base_urls,
                    'updated_at': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save URL cache: {e}")
    
    def add_url(self, url: str):
        """添加URL"""
        if url not in self.base_urls:
            self.base_urls.append(url)
            self._save_cache()
    
    def remove_url(self, url: str):
        """移除URL"""
        if url in self.base_urls:
            self.base_urls.remove(url)
            self._save_cache()
    
    def get_random_url(self) -> Optional[str]:
        """获取随机URL"""
        if not self.enabled or not self.base_urls:
            return None
        return random.choice(self.base_urls)
    
    def get_next_url(self) -> Optional[str]:
        """获取下一个URL (轮换)"""
        if not self.enabled or not self.base_urls:
            return None
        
        url = self.base_urls[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.base_urls)
        return url
    
    def get_current_url(self) -> Optional[str]:
        """获取当前URL"""
        if not self.enabled or not self.base_urls:
            return None
        return self.base_urls[self.current_index]
    
    def enable(self):
        """启用URL轮换"""
        self.enabled = True
    
    def disable(self):
        """禁用URL轮换"""
        self.enabled = False


class CookieManager:
    """Cookie管理器"""
    
    def __init__(self, cache_file: Optional[Path] = None):
        self.cookies: Dict[str, Dict] = {}  # domain -> cookies
        self.cache_file = cache_file or Path.home() / ".jav-spider-cookies.json"
        self._load_cache()
    
    def _load_cache(self):
        """加载缓存的cookies"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cookies = json.load(f)
                logger.info(f"Loaded cookies for {len(self.cookies)} domains")
            except Exception as e:
                logger.warning(f"Failed to load cookie cache: {e}")
    
    def _save_cache(self):
        """保存cookies"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cookies, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cookie cache: {e}")
    
    def set_cookies(self, domain: str, cookies: Dict[str, str]):
        """设置域名的cookies"""
        self.cookies[domain] = cookies
        self._save_cache()
    
    def get_cookies(self, domain: str) -> Optional[Dict[str, str]]:
        """获取域名的cookies"""
        return self.cookies.get(domain)
    
    def clear_cookies(self, domain: str):
        """清除域名的cookies"""
        if domain in self.cookies:
            del self.cookies[domain]
            self._save_cache()
    
    def update_cookie(self, domain: str, name: str, value: str):
        """更新单个cookie"""
        if domain not in self.cookies:
            self.cookies[domain] = {}
        self.cookies[domain][name] = value
        self._save_cache()


class DelayManager:
    """延迟管理器"""
    
    def __init__(self):
        self.delays: Dict[str, float] = {
            "request": 2.0,      # 请求间延迟 (秒)
            "index": 3.0,       # 索引页延迟
            "detail": 2.0,      # 详情页延迟
            "download": 5.0,    # 下载延迟
        }
        self.min_delay = 0.5
        self.max_delay = 30.0
    
    def set_delay(self, delay_type: str, delay: float):
        """设置延迟"""
        delay = max(self.min_delay, min(delay, self.max_delay))
        self.delays[delay_type] = delay
    
    def get_delay(self, delay_type: str) -> float:
        """获取延迟"""
        return self.delays.get(delay_type, self.delays["request"])
    
    async def create_delay(self, delay_type: str = "request", randomize: bool = True):
        """创建延迟"""
        base_delay = self.get_delay(delay_type)
        
        if randomize:
            # 随机化延迟,避免模式识别
            delay = base_delay * random.uniform(0.8, 1.2)
        else:
            delay = base_delay
        
        logger.debug(f"Waiting {delay:.2f}s ({delay_type})")
        await asyncio.sleep(delay)
    
    def increase_delay(self, delay_type: str, factor: float = 1.5):
        """增加延迟 (指数退避)"""
        current = self.get_delay(delay_type)
        new_delay = current * factor
        self.set_delay(delay_type, new_delay)
        logger.info(f"Increased {delay_type} delay: {current:.2f}s -> {new_delay:.2f}s")
    
    def reset_delay(self, delay_type: str):
        """重置延迟到默认值"""
        defaults = {
            "request": 2.0,
            "index": 3.0,
            "detail": 2.0,
            "download": 5.0,
        }
        self.set_delay(delay_type, defaults.get(delay_type, 2.0))
        logger.info(f"Reset {delay_type} delay")


class RetryStrategy(ABC):
    """重试策略 (抽象基类)"""
    
    @abstractmethod
    async def should_retry(self, attempt: int, error: Exception) -> bool:
        """判断是否应该重试"""
        pass
    
    @abstractmethod
    def get_delay(self, attempt: int) -> float:
        """获取重试延迟"""
        pass


class ExponentialBackoffRetry(RetryStrategy):
    """指数退避重试策略"""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponent: float = 1.5
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponent = exponent
    
    async def should_retry(self, attempt: int, error: Exception) -> bool:
        """判断是否应该重试"""
        return attempt < self.max_attempts
    
    def get_delay(self, attempt: int) -> float:
        """获取重试延迟 (指数增长)"""
        delay = self.base_delay * (self.exponent ** attempt)
        return min(delay, self.max_delay)


class AntiBlockManager:
    """防屏蔽管理器 (整合所有防屏蔽组件)"""
    
    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        base_urls: Optional[List[str]] = None,
        use_cloudflare_bypass: bool = False
    ):
        self.ua_rotator = UserAgentRotator()
        self.proxy_rotator = ProxyRotator(proxies)
        self.url_rotator = URLRotator(base_urls)
        self.cookie_manager = CookieManager()
        self.delay_manager = DelayManager()
        self.retry_strategy = ExponentialBackoffRetry()
        self.use_cloudflare_bypass = use_cloudflare_bypass
        
        logger.info("AntiBlockManager initialized")
        if proxies:
            logger.info(f"Loaded {len(proxies)} proxies")
        if base_urls:
            logger.info(f"Loaded {len(base_urls)} base URLs")
    
    def get_request_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "User-Agent": self.ua_rotator.get_random(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    
    def get_request_config(self) -> Dict:
        """获取请求配置"""
        config = {
            "headers": self.get_request_headers(),
            "timeout": 30,
        }
        
        # 添加代理
        proxy = self.proxy_rotator.get_proxy()
        if proxy:
            config["proxy"] = proxy
        
        # 添加cookies
        base_url = self.url_rotator.get_current_url()
        if base_url:
            from urllib.parse import urlparse
            domain = urlparse(base_url).netloc
            cookies = self.cookie_manager.get_cookies(domain)
            if cookies:
                config["cookies"] = cookies
        
        return config
    
    async def execute_with_retry(
        self,
        func: callable,
        *args,
        **kwargs
    ):
        """带重试和防屏蔽的执行"""
        attempt = 0
        last_error = None
        
        while True:
            attempt += 1
            
            try:
                # 添加延迟
                if attempt > 1:
                    delay = self.retry_strategy.get_delay(attempt - 1)
                    logger.info(f"Retry attempt {attempt}/{self.retry_strategy.max_attempts} after {delay:.2f}s")
                    await asyncio.sleep(delay)
                
                # 执行函数
                result = await func(*args, **kwargs)
                
                # 成功,重置延迟
                self.delay_manager.reset_delay("request")
                
                return result
                
            except Exception as e:
                last_error = e
                
                # 检查是否应该重试
                if not await self.retry_strategy.should_retry(attempt, e):
                    logger.error(f"Max retries exceeded for attempt {attempt}")
                    break
                
                # 标记代理失败
                config = kwargs.get('config', {})
                proxy = config.get('proxy')
                if proxy:
                    self.proxy_rotator.mark_fail(proxy)
                
                # 增加延迟
                self.delay_manager.increase_delay("request")
        
        # 所有重试都失败
        raise last_error
    
    def get_stats(self) -> Dict:
        """获取防屏蔽统计信息"""
        return {
            "user_agent_rotation": self.ua_rotator.rotation_enabled,
            "proxies_count": len(self.proxy_rotator.proxies),
            "base_urls_count": len(self.url_rotator.base_urls),
            "url_rotation_enabled": self.url_rotator.enabled,
            "cookies_domains": len(self.cookie_manager.cookies),
            "current_delays": self.delay_manager.delays,
            "proxy_stats": self.proxy_rotator.get_stats(),
            "cloudflare_bypass": self.use_cloudflare_bypass
        }


# 使用示例
async def example_usage():
    """使用示例"""
    
    # 创建防屏蔽管理器
    anti_block = AntiBlockManager(
        proxies=[
            "http://proxy1.example.com:8080",
            "http://proxy2.example.com:8080",
        ],
        base_urls=[
            "https://www.javbus.com",
            "https://www.javlibrary.com",
        ],
        use_cloudflare_bypass=False
    )
    
    # 获取请求配置
    config = anti_block.get_request_config()
    print(f"Request config: {config}")
    
    # 获取统计信息
    stats = anti_block.get_stats()
    print(f"Anti-block stats: {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    asyncio.run(example_usage())
